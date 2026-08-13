from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from lumi_api.persistence.models import OrganizationMember

from .errors import PermissionDenied
from .service import AuthService


class SecureAuthService(AuthService):
    """Canonical application-facing auth service with privilege-escalation guards."""

    async def create_invite(
        self,
        *,
        actor_id: UUID,
        organization_id: UUID,
        email: str,
        role: str,
        client_key: str,
        now: datetime | None = None,
    ) -> str:
        actor = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == actor_id,
                OrganizationMember.status == "active",
            )
        )
        if actor is None or actor.role not in {"OWNER", "ADMIN"}:
            raise PermissionDenied("permission denied")
        if actor.role == "ADMIN" and role in {"OWNER", "ADMIN"}:
            raise PermissionDenied("permission denied")
        return await super().create_invite(
            actor_id=actor_id,
            organization_id=organization_id,
            email=email,
            role=role,
            client_key=client_key,
            now=now,
        )
