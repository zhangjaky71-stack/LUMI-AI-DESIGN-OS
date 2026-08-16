from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .models import (
    ApiToken,
    AuditCategory,
    AuthAuditEvent,
    BrowserSession,
    OrganizationMembership,
    OrganizationRole,
    OneTimeToken,
    PasswordCredential,
    Principal,
    User,
    WorkspaceMembership,
    WorkspaceRole,
)
from .passwords import PasswordHasher, validate_password_policy
from .policy import AccessPolicyService, Permission, enforce_last_owner_invariant
from .security import MemoryRateLimiter, hash_secret, issue_secret, verify_hashed_secret
from .store import MemoryAuthStore


class InvalidCredentials(ValueError):
    pass


class AuthFlowError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SessionGrant:
    session_secret: str
    csrf_token: str
    session: BrowserSession


@dataclass(frozen=True, slots=True)
class IssuedOneTimeSecret:
    secret: str
    token: OneTimeToken


@dataclass(frozen=True, slots=True)
class IssuedApiToken:
    secret: str
    token: ApiToken


class AuthService:
    def __init__(
        self,
        *,
        store: MemoryAuthStore,
        password_hasher: PasswordHasher,
        rate_limiter: MemoryRateLimiter | None = None,
        session_ttl: timedelta = timedelta(days=14),
    ) -> None:
        self.store = store
        self.password_hasher = password_hasher
        self.rate_limiter = rate_limiter or MemoryRateLimiter()
        self.session_ttl = session_ttl
        self.policy = AccessPolicyService()
        self._dummy_hash = password_hasher.hash(
            "lumi-dummy-password-never-associated-with-a-user"
        )

    def _audit(
        self,
        category: AuditCategory,
        *,
        now: datetime,
        organization_id: UUID | None = None,
        actor_id: str | None = None,
        subject_user_id: UUID | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.store.append_audit(
            AuthAuditEvent(
                id=new_uuid7(),
                category=category,
                occurred_at=now,
                organization_id=organization_id,
                actor_id=actor_id,
                subject_user_id=subject_user_id,
                metadata=metadata,
            )
        )

    def register(
        self,
        *,
        email: str,
        display_name: str,
        password: str,
        now: datetime,
    ) -> User:
        validate_password_policy(password)
        normalized_email = email.strip().casefold()
        if self.store.get_user_by_email(normalized_email) is not None:
            raise AuthFlowError("EMAIL_UNAVAILABLE")
        user = User(
            id=new_uuid7(),
            email=normalized_email,
            display_name=display_name,
            created_at=now,
        )
        credential = PasswordCredential(
            user_id=user.id,
            password_hash=self.password_hasher.hash(password),
            changed_at=now,
        )
        self.store.save_user(user)
        self.store.save_credential(credential)
        return user

    def login(
        self,
        *,
        email: str,
        password: str,
        now: datetime,
        user_agent_hash: str | None = None,
    ) -> SessionGrant:
        normalized_email = email.strip().casefold()
        self.rate_limiter.hit(
            action="login",
            subject_key=hash_secret(normalized_email),
            now=now,
            limit=10,
            window=timedelta(minutes=15),
        )
        user = self.store.get_user_by_email(normalized_email)
        credential = self.store.credentials.get(user.id) if user is not None else None
        encoded = credential.password_hash if credential is not None else self._dummy_hash
        verified = self.password_hasher.verify(encoded, password)
        if user is None or credential is None or user.disabled_at is not None or not verified:
            self._audit(
                AuditCategory.LOGIN_FAILURE,
                now=now,
                metadata=(("category", "invalid_credentials"),),
            )
            raise InvalidCredentials("INVALID_CREDENTIALS")

        raw_session = issue_secret(48)
        session_key = hash_secret(raw_session)
        session = BrowserSession(
            id=session_key,
            user_id=user.id,
            created_at=now,
            expires_at=now + self.session_ttl,
            last_seen_at=now,
            recent_auth_at=now,
            user_agent_hash=user_agent_hash,
        )
        self.store.save_session(session)
        csrf_token = issue_secret(32)
        self._audit(
            AuditCategory.LOGIN_SUCCESS,
            now=now,
            actor_id=str(user.id),
            subject_user_id=user.id,
        )
        return SessionGrant(
            session_secret=raw_session,
            csrf_token=csrf_token,
            session=session,
        )

    def authenticate_session(self, session_secret: str, *, now: datetime) -> BrowserSession:
        key = hash_secret(session_secret)
        session = self.store.sessions.get(key)
        if session is None or not session.is_active(now):
            raise InvalidCredentials("SESSION_INVALID")
        refreshed = session.model_copy(update={"last_seen_at": now})
        self.store.save_session(refreshed)
        return refreshed

    def logout(self, session_secret: str, *, now: datetime) -> None:
        key = hash_secret(session_secret)
        session = self.store.sessions.get(key)
        if session is None:
            return
        if session.revoked_at is None:
            revoked = session.model_copy(update={"revoked_at": now})
            self.store.save_session(revoked)
            self._audit(
                AuditCategory.LOGOUT,
                now=now,
                actor_id=str(session.user_id),
                subject_user_id=session.user_id,
            )

    def revoke_all_sessions(self, user_id: UUID, *, now: datetime) -> int:
        count = 0
        for key, session in tuple(self.store.sessions.items()):
            if session.user_id != user_id or session.revoked_at is not None:
                continue
            self.store.sessions[key] = session.model_copy(update={"revoked_at": now})
            count += 1
        if count:
            self._audit(
                AuditCategory.SESSION_REVOKED,
                now=now,
                actor_id=str(user_id),
                subject_user_id=user_id,
                metadata=(("count", str(count)),),
            )
        return count

    def add_organization_membership(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationRole,
        now: datetime,
    ) -> OrganizationMembership:
        membership = OrganizationMembership(
            id=new_uuid7(),
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )
        self.store.save_membership(membership)
        return membership

    def add_workspace_membership(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        role: WorkspaceRole,
        now: datetime,
    ) -> WorkspaceMembership:
        if not any(
            membership.organization_id == organization_id
            and membership.user_id == user_id
            for membership in self.store.organization_memberships.values()
        ):
            raise AuthFlowError("ORGANIZATION_MEMBERSHIP_REQUIRED")
        membership = WorkspaceMembership(
            id=new_uuid7(),
            organization_id=organization_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )
        self.store.save_workspace_membership(membership)
        return membership

    def change_membership_role(
        self,
        membership_id: UUID,
        *,
        new_role: OrganizationRole,
        actor_id: str,
        now: datetime,
    ) -> OrganizationMembership:
        memberships = tuple(self.store.organization_memberships.values())
        enforce_last_owner_invariant(
            memberships,
            target_membership_id=membership_id,
            new_role=new_role,
        )
        current = self.store.organization_memberships.get(membership_id)
        if current is None:
            raise AuthFlowError("MEMBERSHIP_NOT_FOUND")
        updated = current.model_copy(update={"role": new_role})
        self.store.organization_memberships[membership_id] = updated
        self._audit(
            AuditCategory.MEMBERSHIP_ROLE_CHANGED,
            now=now,
            organization_id=current.organization_id,
            actor_id=actor_id,
            subject_user_id=current.user_id,
            metadata=(("new_role", new_role.value),),
        )
        return updated

    def principal_for_session(
        self,
        session_secret: str,
        *,
        organization_id: UUID,
        now: datetime,
    ) -> Principal:
        session = self.authenticate_session(session_secret, now=now)
        principal = self.policy.principal_for_memberships(
            actor_id=str(session.user_id),
            user_id=session.user_id,
            organization_id=organization_id,
            memberships=self.store.memberships_for_user(session.user_id),
        )
        if principal is None:
            raise InvalidCredentials("TENANT_RESOURCE_NOT_FOUND")
        return principal

    def create_invite(
        self,
        *,
        principal: Principal,
        email: str,
        role: OrganizationRole,
        now: datetime,
        ttl: timedelta = timedelta(days=7),
    ) -> IssuedOneTimeSecret:
        decision = self.policy.authorize(
            principal,
            organization_id=principal.organization_id,
            permission=Permission.MEMBER_INVITE,
        )
        if not decision.allowed:
            raise AuthFlowError(decision.reason_code)
        raw = issue_secret(32)
        token = OneTimeToken(
            id=new_uuid7(),
            purpose="invite",
            token_hash=hash_secret(raw),
            email=email.strip().casefold(),
            organization_id=principal.organization_id,
            role=role,
            created_at=now,
            expires_at=now + ttl,
        )
        self.store.save_one_time_token(token)
        self._audit(
            AuditCategory.INVITE_CREATED,
            now=now,
            organization_id=principal.organization_id,
            actor_id=principal.actor_id,
            metadata=(("role", role.value),),
        )
        return IssuedOneTimeSecret(secret=raw, token=token)

    def accept_invite(
        self,
        secret: str,
        *,
        user_id: UUID,
        email: str,
        now: datetime,
    ) -> OrganizationMembership:
        self.rate_limiter.hit(
            action="invite_accept",
            subject_key=hash_secret(secret)[:16],
            now=now,
            limit=8,
            window=timedelta(minutes=15),
        )
        token = self.store.one_time_tokens.get(hash_secret(secret))
        if token is None or token.purpose != "invite" or not token.is_usable(now):
            raise AuthFlowError("INVITE_INVALID")
        if token.email != email.strip().casefold():
            raise AuthFlowError("INVITE_INVALID")
        assert token.organization_id is not None and token.role is not None
        membership = self.add_organization_membership(
            organization_id=token.organization_id,
            user_id=user_id,
            role=token.role,
            now=now,
        )
        self.store.save_one_time_token(token.model_copy(update={"consumed_at": now}))
        self._audit(
            AuditCategory.INVITE_ACCEPTED,
            now=now,
            organization_id=token.organization_id,
            actor_id=str(user_id),
            subject_user_id=user_id,
        )
        return membership

    def create_password_reset(
        self,
        *,
        email: str,
        now: datetime,
        ttl: timedelta = timedelta(minutes=30),
    ) -> IssuedOneTimeSecret | None:
        normalized = email.strip().casefold()
        self.rate_limiter.hit(
            action="password_reset",
            subject_key=hash_secret(normalized),
            now=now,
            limit=5,
            window=timedelta(hours=1),
        )
        user = self.store.get_user_by_email(normalized)
        if user is None:
            return None
        raw = issue_secret(32)
        token = OneTimeToken(
            id=new_uuid7(),
            purpose="password_reset",
            token_hash=hash_secret(raw),
            user_id=user.id,
            created_at=now,
            expires_at=now + ttl,
        )
        self.store.save_one_time_token(token)
        return IssuedOneTimeSecret(secret=raw, token=token)

    def consume_password_reset(
        self,
        secret: str,
        *,
        new_password: str,
        now: datetime,
    ) -> None:
        validate_password_policy(new_password)
        token_hash = hash_secret(secret)
        token = self.store.one_time_tokens.get(token_hash)
        if (
            token is None
            or token.purpose != "password_reset"
            or token.user_id is None
            or not token.is_usable(now)
            or not verify_hashed_secret(secret, token.token_hash)
        ):
            raise AuthFlowError("RESET_INVALID")
        credential = PasswordCredential(
            user_id=token.user_id,
            password_hash=self.password_hasher.hash(new_password),
            changed_at=now,
        )
        self.store.save_credential(credential)
        self.store.save_one_time_token(token.model_copy(update={"consumed_at": now}))
        self.revoke_all_sessions(token.user_id, now=now)
        self._audit(
            AuditCategory.PASSWORD_RESET,
            now=now,
            actor_id=str(token.user_id),
            subject_user_id=token.user_id,
        )

    def create_api_token(
        self,
        *,
        principal: Principal,
        name: str,
        scopes: tuple[str, ...],
        now: datetime,
        expires_at: datetime | None = None,
    ) -> IssuedApiToken:
        decision = self.policy.authorize(
            principal,
            organization_id=principal.organization_id,
            permission=Permission.API_TOKEN_MANAGE,
        )
        if not decision.allowed:
            raise AuthFlowError(decision.reason_code)
        allowed_scopes = set(principal.permissions)
        if not set(scopes).issubset(allowed_scopes):
            raise AuthFlowError("TOKEN_SCOPE_ESCALATION")
        prefix = issue_secret(6).replace("-", "")[:8]
        secret_part = issue_secret(32)
        raw = f"lumi_{prefix}_{secret_part}"
        token = ApiToken(
            id=new_uuid7(),
            organization_id=principal.organization_id,
            name=name,
            prefix=prefix,
            secret_hash=hash_secret(raw),
            scopes=scopes,
            created_by_user_id=principal.user_id or UUID(int=0),
            created_at=now,
            expires_at=expires_at,
        )
        self.store.save_api_token(token)
        self._audit(
            AuditCategory.API_TOKEN_CREATED,
            now=now,
            organization_id=principal.organization_id,
            actor_id=principal.actor_id,
            metadata=(("token_id", str(token.id)),),
        )
        return IssuedApiToken(secret=raw, token=token)

    def authenticate_api_token(self, secret: str, *, now: datetime) -> Principal:
        token_hash = hash_secret(secret)
        token = self.store.api_tokens.get(token_hash)
        if token is None or not token.is_active(now):
            raise InvalidCredentials("API_TOKEN_INVALID")
        if not verify_hashed_secret(secret, token.secret_hash):
            raise InvalidCredentials("API_TOKEN_INVALID")
        self.store.api_tokens[token_hash] = token.model_copy(update={"last_used_at": now})
        return Principal(
            actor_type="API_TOKEN",
            actor_id=str(token.id),
            user_id=token.created_by_user_id,
            organization_id=token.organization_id,
            permissions=token.scopes,
            token_id=token.id,
        )

    def revoke_api_token(
        self,
        token_id: UUID,
        *,
        principal: Principal,
        now: datetime,
    ) -> None:
        decision = self.policy.authorize(
            principal,
            organization_id=principal.organization_id,
            permission=Permission.API_TOKEN_MANAGE,
        )
        if not decision.allowed:
            raise AuthFlowError(decision.reason_code)
        for key, token in tuple(self.store.api_tokens.items()):
            if token.id != token_id or token.organization_id != principal.organization_id:
                continue
            self.store.api_tokens[key] = token.model_copy(update={"revoked_at": now})
            self._audit(
                AuditCategory.API_TOKEN_REVOKED,
                now=now,
                organization_id=token.organization_id,
                actor_id=principal.actor_id,
                metadata=(("token_id", str(token.id)),),
            )
            return
        raise AuthFlowError("TOKEN_NOT_FOUND")
