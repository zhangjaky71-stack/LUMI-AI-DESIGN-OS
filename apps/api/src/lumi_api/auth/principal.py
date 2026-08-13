from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from lumi_auth import (
    ApiTokenRecord,
    Membership,
    RequestContext,
    SessionRecord,
    build_request_context,
    hash_token,
    validate_api_token,
    validate_session,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import ApiToken, OrganizationMember, Session

from .errors import PermissionDenied, SessionInvalid


@dataclass(frozen=True, slots=True)
class SessionPrincipal:
    context: RequestContext
    session_id: UUID
    csrf_token_hash: str


@dataclass(frozen=True, slots=True)
class ApiTokenPrincipal:
    token_id: UUID
    organization_id: UUID
    created_by: UUID
    scopes: frozenset[str]


class PrincipalResolver:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def from_session(
        self,
        *,
        plaintext_session_token: str,
        request_id: str,
        trace_id: str,
        now: datetime,
        requested_organization_id: UUID | None = None,
    ) -> SessionPrincipal:
        row = await self.session.scalar(
            select(Session).where(Session.token_hash == hash_token(plaintext_session_token))
        )
        if row is None or row.csrf_token_hash is None:
            raise SessionInvalid("session invalid")
        record = SessionRecord(
            session_token_hash=row.token_hash,
            csrf_token_hash=row.csrf_token_hash,
            user_id=str(row.user_id),
            organization_id=str(row.organization_id) if row.organization_id else None,
            created_at=row.created_at,
            expires_at=row.expires_at,
            last_seen_at=row.last_seen_at,
            revoked_at=row.revoked_at,
            user_agent_hash=row.user_agent_hash,
        )
        try:
            validate_session(record, now=now)
        except PermissionError as exc:
            raise SessionInvalid("session invalid") from exc

        organization_id = requested_organization_id or row.organization_id
        if organization_id is None:
            raise SessionInvalid("session has no active organization")
        memberships = (
            await self.session.scalars(
                select(OrganizationMember).where(
                    OrganizationMember.user_id == row.user_id,
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.status == "active",
                )
            )
        ).all()
        if not memberships:
            raise SessionInvalid("session invalid")
        context = build_request_context(
            request_id=request_id,
            actor_id=str(row.user_id),
            organization_id=str(organization_id),
            memberships=tuple(
                Membership(
                    user_id=str(item.user_id),
                    organization_id=str(item.organization_id),
                    role=item.role,  # type: ignore[arg-type]
                )
                for item in memberships
            ),
            trace_id=trace_id,
        )
        row.last_seen_at = now
        row.organization_id = organization_id
        await self.session.flush()
        return SessionPrincipal(context=context, session_id=row.id, csrf_token_hash=row.csrf_token_hash)

    async def from_api_token(
        self,
        *,
        plaintext_token: str,
        required_scope: str,
        now: datetime,
    ) -> ApiTokenPrincipal:
        parts = plaintext_token.split("_", 2)
        if len(parts) != 3 or parts[0] != "lumi":
            raise PermissionDenied("permission denied")
        prefix = parts[1]
        row = await self.session.scalar(select(ApiToken).where(ApiToken.prefix == prefix))
        if row is None:
            raise PermissionDenied("permission denied")
        record = ApiTokenRecord(
            id=str(row.id),
            organization_id=str(row.organization_id),
            name=row.name,
            prefix=row.prefix,
            secret_hash=row.secret_hash,
            scopes=frozenset(row.scopes),
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            last_used_at=row.last_used_at,
        )
        try:
            validate_api_token(record, plaintext_token, required_scope=required_scope, now=now)
        except PermissionError as exc:
            raise PermissionDenied("permission denied") from exc
        row.last_used_at = now
        await self.session.flush()
        return ApiTokenPrincipal(
            token_id=row.id,
            organization_id=row.organization_id,
            created_by=row.created_by,
            scopes=frozenset(row.scopes),
        )

    async def revoke_api_token(
        self,
        *,
        actor_id: UUID,
        organization_id: UUID,
        token_id: UUID,
        now: datetime,
    ) -> None:
        membership = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == actor_id,
                OrganizationMember.status == "active",
            )
        )
        if membership is None or membership.role not in {"OWNER", "ADMIN"}:
            raise PermissionDenied("permission denied")
        token = await self.session.scalar(
            select(ApiToken).where(
                ApiToken.id == token_id,
                ApiToken.organization_id == organization_id,
            )
        )
        if token is None:
            raise PermissionDenied("permission denied")
        token.revoked_at = now
        await self.session.flush()
