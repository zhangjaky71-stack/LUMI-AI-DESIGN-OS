from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OrganizationRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"
    BILLING = "BILLING"


class WorkspaceRole(StrEnum):
    ADMIN = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class ActorType(StrEnum):
    USER = "USER"
    API_TOKEN = "API_TOKEN"
    SERVICE = "SERVICE"


class AuditCategory(StrEnum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET = "PASSWORD_RESET"
    SESSION_REVOKED = "SESSION_REVOKED"
    INVITE_CREATED = "INVITE_CREATED"
    INVITE_ACCEPTED = "INVITE_ACCEPTED"
    INVITE_REVOKED = "INVITE_REVOKED"
    MEMBERSHIP_ROLE_CHANGED = "MEMBERSHIP_ROLE_CHANGED"
    API_TOKEN_CREATED = "API_TOKEN_CREATED"
    API_TOKEN_REVOKED = "API_TOKEN_REVOKED"


class User(AuthModel):
    id: UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    email_verified_at: datetime | None = None
    disabled_at: datetime | None = None
    created_at: datetime

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if "@" not in normalized:
            raise ValueError("email must contain @")
        return normalized

    @field_validator("email_verified_at", "disabled_at", "created_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("auth timestamps must be timezone-aware")
        return value


class PasswordCredential(AuthModel):
    user_id: UUID
    password_hash: str = Field(min_length=20, max_length=2048)
    algorithm: str = Field(default="argon2id", pattern=r"^argon2id$")
    changed_at: datetime

    @field_validator("password_hash")
    @classmethod
    def require_argon2id_encoded_hash(cls, value: str) -> str:
        if not value.startswith("$argon2id$"):
            raise ValueError("password hash must use an encoded Argon2id format")
        return value

    @field_validator("changed_at")
    @classmethod
    def require_changed_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        return value


class OrganizationMembership(AuthModel):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: OrganizationRole
    created_at: datetime


class WorkspaceMembership(AuthModel):
    id: UUID
    organization_id: UUID
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    created_at: datetime


class BrowserSession(AuthModel):
    id: str = Field(min_length=32, max_length=256)
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    recent_auth_at: datetime
    revoked_at: datetime | None = None
    user_agent_hash: str | None = Field(default=None, max_length=128)
    ip_risk_metadata: tuple[tuple[str, str], ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def validate_times(self) -> BrowserSession:
        for value in (
            self.created_at,
            self.expires_at,
            self.last_seen_at,
            self.recent_auth_at,
            self.revoked_at,
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("session timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("session expires_at must be after created_at")
        if self.last_seen_at < self.created_at:
            raise ValueError("session last_seen_at cannot precede created_at")
        return self

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at


class OneTimeToken(AuthModel):
    id: UUID
    purpose: str = Field(min_length=1, max_length=80)
    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_id: UUID | None = None
    email: str | None = Field(default=None, max_length=320)
    organization_id: UUID | None = None
    role: OrganizationRole | None = None
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> OneTimeToken:
        for value in (self.created_at, self.expires_at, self.consumed_at, self.revoked_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("token timestamps must be timezone-aware")
        if self.expires_at <= self.created_at:
            raise ValueError("token expires_at must be after created_at")
        if self.purpose == "invite" and (
            self.email is None or self.organization_id is None or self.role is None
        ):
            raise ValueError("invite token requires email, organization_id and role")
        if self.purpose == "password_reset" and self.user_id is None:
            raise ValueError("password reset token requires user_id")
        return self

    def is_usable(self, now: datetime) -> bool:
        return self.consumed_at is None and self.revoked_at is None and now < self.expires_at


class ApiToken(AuthModel):
    id: UUID
    organization_id: UUID
    name: str = Field(min_length=1, max_length=120)
    prefix: str = Field(min_length=6, max_length=32)
    secret_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scopes: tuple[str, ...] = Field(min_length=1, max_length=128)
    created_by_user_id: UUID
    created_at: datetime
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def canonicalize_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({scope.strip() for scope in value if scope.strip()}))
        if not normalized:
            raise ValueError("api token must contain at least one scope")
        return normalized

    def is_active(self, now: datetime) -> bool:
        return self.revoked_at is None and (self.expires_at is None or now < self.expires_at)


class Principal(AuthModel):
    actor_type: ActorType
    actor_id: str
    user_id: UUID | None = None
    organization_id: UUID
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    token_id: UUID | None = None


class RequestContext(AuthModel):
    request_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=200)
    organization_id: UUID
    workspace_id: UUID | None = None
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()


class AuthAuditEvent(AuthModel):
    id: UUID
    category: AuditCategory
    occurred_at: datetime
    organization_id: UUID | None = None
    actor_id: str | None = Field(default=None, max_length=200)
    subject_user_id: UUID | None = None
    metadata: tuple[tuple[str, str], ...] = Field(default=(), max_length=64)

    @field_validator("occurred_at")
    @classmethod
    def require_audit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value
