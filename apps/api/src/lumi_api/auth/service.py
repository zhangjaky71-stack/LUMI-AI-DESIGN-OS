from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from lumi_auth import (
    InMemorySlidingWindowRateLimiter,
    Membership,
    RateLimiter,
    SessionRecord,
    SingleUseTokenRecord,
    build_request_context,
    consume_single_use_token,
    hash_token,
    issue_opaque_token,
    validate_csrf,
)
from lumi_domain import new_uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lumi_api.persistence.models import (
    ApiToken,
    AuditEvent,
    EmailVerificationToken,
    Organization,
    OrganizationInvite,
    OrganizationMember,
    PasswordCredential,
    PasswordResetToken,
    Session,
    User,
    Workspace,
)

from .errors import InvalidCredentials, PermissionDenied, RegistrationRejected, SessionInvalid, TokenInvalid
from .password import Argon2idPasswordService

_SLUG = re.compile(r"[^a-z0-9-]+")


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    user_id: UUID
    organization_id: UUID
    workspace_id: UUID
    email_verification_token: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user_id: UUID
    organization_id: UUID
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ApiTokenResult:
    token_id: UUID
    plaintext: str
    prefix: str


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        password_service: Argon2idPasswordService | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session
        self.passwords = password_service or Argon2idPasswordService()
        self.rate_limiter = rate_limiter or InMemorySlidingWindowRateLimiter()
        self._dummy_password_hash = self.passwords.hash_password("lumi-dummy-password-never-used")

    @staticmethod
    def normalize_email(value: str) -> str:
        email = value.strip().lower()
        if len(email) > 320 or "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError("invalid email")
        return email

    @staticmethod
    def normalize_slug(value: str) -> str:
        slug = _SLUG.sub("-", value.strip().lower()).strip("-")
        if not 2 <= len(slug) <= 100:
            raise ValueError("organization slug must be 2..100 characters")
        return slug

    @staticmethod
    def validate_password_input(password: str) -> None:
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        if len(password) > 1024:
            raise ValueError("password is too long")

    def _rate(self, action: str, key: str, now: datetime, *, limit: int, minutes: int) -> None:
        self.rate_limiter.consume(
            f"auth:{action}:{key}",
            now=now,
            limit=limit,
            window=timedelta(minutes=minutes),
        )

    def _audit(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        action: str,
        target_type: str,
        target_id: UUID | None,
        request_id: str | None,
        metadata: dict | None = None,
    ) -> None:
        self.session.add(
            AuditEvent(
                id=new_uuid7(),
                organization_id=organization_id,
                actor_type="USER" if actor_id is not None else "SYSTEM",
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                request_id=request_id,
                metadata_json=metadata or {},
            )
        )

    async def register_local(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        organization_name: str,
        organization_slug: str,
        client_key: str,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> RegistrationResult:
        now = now or datetime.now(UTC)
        normalized_email = self.normalize_email(email)
        slug = self.normalize_slug(organization_slug)
        self.validate_password_input(password)
        self._rate("register", client_key, now, limit=5, minutes=15)

        existing = await self.session.scalar(select(User).where(User.email == normalized_email))
        if existing is not None:
            raise RegistrationRejected("registration is not available")
        existing_org = await self.session.scalar(select(Organization).where(Organization.slug == slug))
        if existing_org is not None:
            raise RegistrationRejected("registration is not available")

        user_id = new_uuid7()
        organization_id = new_uuid7()
        workspace_id = new_uuid7()
        verification = issue_opaque_token(label="lumi_verify")
        password_hash = self.passwords.hash_password(password)

        async with self.session.begin_nested():
            self.session.add(
                User(
                    id=user_id,
                    email=normalized_email,
                    display_name=display_name.strip() or "LUMI User",
                    status="active",
                )
            )
            self.session.add(
                PasswordCredential(
                    id=new_uuid7(),
                    user_id=user_id,
                    password_hash=password_hash,
                    changed_at=now,
                )
            )
            self.session.add(
                Organization(
                    id=organization_id,
                    name=organization_name.strip() or "My Organization",
                    slug=slug,
                    status="active",
                    plan="free",
                    settings_json={},
                )
            )
            self.session.add(
                OrganizationMember(
                    id=new_uuid7(),
                    organization_id=organization_id,
                    user_id=user_id,
                    role="OWNER",
                    status="active",
                )
            )
            self.session.add(
                Workspace(
                    id=workspace_id,
                    organization_id=organization_id,
                    name="Default",
                    slug="default",
                    settings_json={},
                )
            )
            self.session.add(
                EmailVerificationToken(
                    id=new_uuid7(),
                    user_id=user_id,
                    token_hash=verification.token_hash,
                    expires_at=now + timedelta(hours=24),
                )
            )
            self._audit(
                organization_id=organization_id,
                actor_id=user_id,
                action="auth.user_registered",
                target_type="user",
                target_id=user_id,
                request_id=request_id,
            )
            await self.session.flush()

        return RegistrationResult(user_id, organization_id, workspace_id, verification.plaintext)

    async def verify_email(self, plaintext_token: str, *, now: datetime | None = None) -> UUID:
        now = now or datetime.now(UTC)
        token_hash = hash_token(plaintext_token)
        row = await self.session.scalar(
            select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        )
        if row is None:
            raise TokenInvalid("token invalid or expired")
        record = SingleUseTokenRecord(row.token_hash, row.expires_at, row.consumed_at, row.revoked_at)
        try:
            consumed = consume_single_use_token(record, plaintext_token, now=now)
        except PermissionError as exc:
            raise TokenInvalid("token invalid or expired") from exc
        user = await self.session.get(User, row.user_id)
        if user is None:
            raise TokenInvalid("token invalid or expired")
        row.consumed_at = consumed.consumed_at
        user.email_verified_at = now
        await self.session.flush()
        return user.id

    async def login_local(
        self,
        *,
        email: str,
        password: str,
        client_key: str,
        requested_organization_id: UUID | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        now: datetime | None = None,
        session_ttl: timedelta = timedelta(days=7),
    ) -> LoginResult:
        now = now or datetime.now(UTC)
        normalized_email = self.normalize_email(email)
        self._rate("login", f"{client_key}:{normalized_email}", now, limit=10, minutes=15)

        user = await self.session.scalar(select(User).where(User.email == normalized_email))
        credential = None
        if user is not None:
            credential = await self.session.scalar(
                select(PasswordCredential).where(PasswordCredential.user_id == user.id)
            )
        candidate_hash = credential.password_hash if credential is not None else self._dummy_password_hash
        password_ok = self.passwords.verify_password(candidate_hash, password)
        if user is None or credential is None or user.status != "active" or not password_ok:
            raise InvalidCredentials("invalid email or password")

        memberships = (
            await self.session.scalars(
                select(OrganizationMember)
                .where(OrganizationMember.user_id == user.id, OrganizationMember.status == "active")
                .order_by(OrganizationMember.created_at, OrganizationMember.id)
            )
        ).all()
        if requested_organization_id is not None:
            selected = next(
                (item for item in memberships if item.organization_id == requested_organization_id),
                None,
            )
        else:
            selected = memberships[0] if memberships else None
        if selected is None:
            raise InvalidCredentials("invalid email or password")

        if self.passwords.needs_rehash(credential.password_hash):
            credential.password_hash = self.passwords.hash_password(password)
            credential.version += 1

        session_token = issue_opaque_token(label="lumi_session")
        csrf_token = issue_opaque_token(label="lumi_csrf")
        expires_at = now + session_ttl
        user_agent_hash = (
            hashlib.sha256(user_agent.encode("utf-8")).hexdigest() if user_agent else None
        )
        self.session.add(
            Session(
                id=new_uuid7(),
                user_id=user.id,
                organization_id=selected.organization_id,
                token_hash=session_token.token_hash,
                csrf_token_hash=csrf_token.token_hash,
                expires_at=expires_at,
                last_seen_at=now,
                revoked=False,
                user_agent_hash=user_agent_hash,
                ip_risk_metadata={},
            )
        )
        self._audit(
            organization_id=selected.organization_id,
            actor_id=user.id,
            action="auth.login_succeeded",
            target_type="session",
            target_id=None,
            request_id=request_id,
        )
        await self.session.flush()
        return LoginResult(
            user.id,
            selected.organization_id,
            session_token.plaintext,
            csrf_token.plaintext,
            expires_at,
        )

    async def logout(
        self,
        *,
        session_token: str,
        csrf_token: str | None,
        origin: str | None,
        allowed_origins: frozenset[str],
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(UTC)
        token_hash = hash_token(session_token)
        row = await self.session.scalar(select(Session).where(Session.token_hash == token_hash))
        if row is None or row.revoked_at is not None or now >= row.expires_at:
            raise SessionInvalid("session invalid")
        if row.csrf_token_hash is None:
            raise SessionInvalid("legacy session requires reauthentication")
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
            validate_csrf(
                record,
                csrf_token=csrf_token,
                origin=origin,
                allowed_origins=allowed_origins,
            )
        except PermissionError as exc:
            raise SessionInvalid("session invalid") from exc
        row.revoked_at = now
        row.revoked = True
        if row.organization_id is not None:
            self._audit(
                organization_id=row.organization_id,
                actor_id=row.user_id,
                action="auth.logout",
                target_type="session",
                target_id=row.id,
                request_id=request_id,
            )
        await self.session.flush()

    async def request_password_reset(
        self,
        *,
        email: str,
        client_key: str,
        now: datetime | None = None,
    ) -> str | None:
        now = now or datetime.now(UTC)
        normalized_email = self.normalize_email(email)
        self._rate("password-reset", f"{client_key}:{normalized_email}", now, limit=5, minutes=30)
        user = await self.session.scalar(select(User).where(User.email == normalized_email))
        if user is None or user.status != "active":
            return None
        token = issue_opaque_token(label="lumi_reset")
        self.session.add(
            PasswordResetToken(
                id=new_uuid7(),
                user_id=user.id,
                token_hash=token.token_hash,
                expires_at=now + timedelta(minutes=30),
            )
        )
        await self.session.flush()
        return token.plaintext

    async def reset_password(
        self,
        *,
        plaintext_token: str,
        new_password: str,
        now: datetime | None = None,
    ) -> UUID:
        now = now or datetime.now(UTC)
        self.validate_password_input(new_password)
        token_hash = hash_token(plaintext_token)
        row = await self.session.scalar(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
        if row is None:
            raise TokenInvalid("token invalid or expired")
        record = SingleUseTokenRecord(row.token_hash, row.expires_at, row.consumed_at, row.revoked_at)
        try:
            consumed = consume_single_use_token(record, plaintext_token, now=now)
        except PermissionError as exc:
            raise TokenInvalid("token invalid or expired") from exc
        credential = await self.session.scalar(
            select(PasswordCredential).where(PasswordCredential.user_id == row.user_id)
        )
        if credential is None:
            raise TokenInvalid("token invalid or expired")
        row.consumed_at = consumed.consumed_at
        credential.password_hash = self.passwords.hash_password(new_password)
        credential.changed_at = now
        credential.version += 1
        active_sessions = (
            await self.session.scalars(
                select(Session).where(Session.user_id == row.user_id, Session.revoked_at.is_(None))
            )
        ).all()
        for session in active_sessions:
            session.revoked_at = now
            session.revoked = True
        await self.session.flush()
        return row.user_id

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
        now = now or datetime.now(UTC)
        normalized_email = self.normalize_email(email)
        self._rate("invite", f"{client_key}:{organization_id}", now, limit=30, minutes=60)
        if role not in {"OWNER", "ADMIN", "EDITOR", "VIEWER", "BILLING"}:
            raise ValueError("invalid invite role")
        membership = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == actor_id,
                OrganizationMember.status == "active",
            )
        )
        if membership is None or membership.role not in {"OWNER", "ADMIN"}:
            raise PermissionDenied("permission denied")
        token = issue_opaque_token(label="lumi_invite")
        self.session.add(
            OrganizationInvite(
                id=new_uuid7(),
                organization_id=organization_id,
                email=normalized_email,
                role=role,
                token_hash=token.token_hash,
                invited_by=actor_id,
                expires_at=now + timedelta(days=7),
            )
        )
        await self.session.flush()
        return token.plaintext

    async def accept_invite(
        self,
        *,
        actor_id: UUID,
        plaintext_token: str,
        now: datetime | None = None,
    ) -> UUID:
        now = now or datetime.now(UTC)
        token_hash = hash_token(plaintext_token)
        invite = await self.session.scalar(
            select(OrganizationInvite).where(OrganizationInvite.token_hash == token_hash)
        )
        user = await self.session.get(User, actor_id)
        if invite is None or user is None or self.normalize_email(user.email) != self.normalize_email(invite.email):
            raise TokenInvalid("token invalid or expired")
        record = SingleUseTokenRecord(
            invite.token_hash, invite.expires_at, invite.consumed_at, invite.revoked_at
        )
        try:
            consumed = consume_single_use_token(record, plaintext_token, now=now)
        except PermissionError as exc:
            raise TokenInvalid("token invalid or expired") from exc
        existing = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == invite.organization_id,
                OrganizationMember.user_id == actor_id,
            )
        )
        if existing is None:
            self.session.add(
                OrganizationMember(
                    id=new_uuid7(),
                    organization_id=invite.organization_id,
                    user_id=actor_id,
                    role=invite.role,
                    status="active",
                )
            )
        else:
            existing.role = invite.role
            existing.status = "active"
        invite.consumed_at = consumed.consumed_at
        await self.session.flush()
        return invite.organization_id

    async def create_api_token(
        self,
        *,
        actor_id: UUID,
        organization_id: UUID,
        name: str,
        scopes: frozenset[str],
        expires_at: datetime | None = None,
    ) -> ApiTokenResult:
        membership = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == actor_id,
                OrganizationMember.status == "active",
            )
        )
        if membership is None:
            raise PermissionDenied("permission denied")
        context = build_request_context(
            request_id="api-token-create",
            actor_id=str(actor_id),
            organization_id=str(organization_id),
            memberships=(Membership(str(actor_id), str(organization_id), membership.role),),  # type: ignore[arg-type]
            trace_id="api-token-create",
        )
        if "api_token.manage" not in context.permissions:
            raise PermissionDenied("permission denied")
        if not scopes or any(len(scope) > 120 for scope in scopes):
            raise ValueError("API token requires bounded non-empty scopes")
        issued = issue_opaque_token(label="lumi")
        token_id = new_uuid7()
        self.session.add(
            ApiToken(
                id=token_id,
                organization_id=organization_id,
                created_by=actor_id,
                name=name.strip() or "API token",
                prefix=issued.prefix,
                secret_hash=issued.token_hash,
                scopes=sorted(scopes),
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return ApiTokenResult(token_id, issued.plaintext, issued.prefix)
