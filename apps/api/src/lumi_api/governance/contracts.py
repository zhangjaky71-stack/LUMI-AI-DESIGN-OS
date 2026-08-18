from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GovernanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AuditActorType(StrEnum):
    USER = "USER"
    API_TOKEN = "API_TOKEN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"


class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILED = "FAILED"


class RetentionClass(StrEnum):
    SECURITY_AUDIT = "SECURITY_AUDIT"
    BILLING = "BILLING"
    CONTENT = "CONTENT"
    AGENT_TRACE = "AGENT_TRACE"
    TEMP_SANDBOX = "TEMP_SANDBOX"
    EXPORT = "EXPORT"
    ANALYTICS = "ANALYTICS"


class AuditActor(GovernanceModel):
    actor_type: AuditActorType
    actor_id: str = Field(min_length=1, max_length=200)
    session_ref: str | None = Field(default=None, max_length=255)
    api_token_ref: UUID | None = None
    agent_run_ref: UUID | None = None
    task_ref: UUID | None = None
    agent_version: str | None = Field(default=None, max_length=160)
    human_initiator_user_id: UUID | None = None

    @model_validator(mode="after")
    def validate_actor(self) -> AuditActor:
        if self.actor_type is AuditActorType.AGENT:
            if self.agent_run_ref is None:
                raise ValueError("AGENT_AUDIT_REQUIRES_RUN")
            if self.agent_version is None:
                raise ValueError("AGENT_AUDIT_REQUIRES_VERSION")
            if self.human_initiator_user_id is None:
                raise ValueError("AGENT_AUDIT_REQUIRES_HUMAN_INITIATOR")
            if self.actor_id.casefold() == "system":
                raise ValueError("AGENT_AUDIT_SYSTEM_IDENTITY_FORBIDDEN")
        if self.actor_type is AuditActorType.API_TOKEN and self.api_token_ref is None:
            raise ValueError("API_TOKEN_AUDIT_REQUIRES_TOKEN_REF")
        return self


class SafeChangeSummary(GovernanceModel):
    changed_fields: tuple[str, ...] = ()
    version_refs: tuple[str, ...] = ()
    semantic_diff_ref: str | None = Field(default=None, max_length=512)

    @field_validator("changed_fields", "version_refs")
    @classmethod
    def canonicalize_strings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({item.strip() for item in value if item.strip()}))


class AuditWrite(GovernanceModel):
    organization_id: UUID
    actor: AuditActor
    action: str = Field(min_length=1, max_length=160)
    resource_type: str = Field(min_length=1, max_length=100)
    resource_id: str = Field(min_length=1, max_length=160)
    resource_version: int | None = Field(default=None, ge=0)
    result: AuditResult
    reason_code: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=128)
    security_metadata: dict[str, Any] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)
    change_summary: SafeChangeSummary = Field(default_factory=SafeChangeSummary)
    retention_class: RetentionClass = RetentionClass.SECURITY_AUDIT
    retention_policy_version: str = Field(min_length=1, max_length=64)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("AUDIT_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


class AuditRecord(GovernanceModel):
    id: UUID
    organization_id: UUID
    actor_type: AuditActorType
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    resource_version: int | None
    result: AuditResult
    reason_code: str | None
    request_id: str | None
    trace_id: str | None
    safe_change_summary: dict[str, Any]
    retention_class: RetentionClass
    retention_policy_version: str
    occurred_at: datetime
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class AuditSearch(GovernanceModel):
    organization_id: UUID
    from_time: datetime | None = None
    to_time: datetime | None = None
    actor_id: str | None = Field(default=None, max_length=200)
    action: str | None = Field(default=None, max_length=160)
    resource_type: str | None = Field(default=None, max_length=100)
    resource_id: str | None = Field(default=None, max_length=160)
    result: AuditResult | None = None
    trace_id: str | None = Field(default=None, max_length=128)
    cursor_occurred_at: datetime | None = None
    cursor_id: UUID | None = None
    limit: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_window(self) -> AuditSearch:
        for value in (self.from_time, self.to_time, self.cursor_occurred_at):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("AUDIT_SEARCH_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        if self.from_time and self.to_time and self.from_time >= self.to_time:
            raise ValueError("AUDIT_SEARCH_TIME_RANGE_INVALID")
        if (self.cursor_occurred_at is None) != (self.cursor_id is None):
            raise ValueError("AUDIT_SEARCH_CURSOR_PAIR_REQUIRED")
        return self


class AuditPage(GovernanceModel):
    items: tuple[AuditRecord, ...]
    next_cursor_occurred_at: datetime | None = None
    next_cursor_id: UUID | None = None


class RetentionPolicy(GovernanceModel):
    id: UUID
    retention_class: RetentionClass
    policy_version: str
    retain_days: int = Field(ge=1)
    active: bool
    description: str
    created_at: datetime


class RetentionCandidate(GovernanceModel):
    retention_class: RetentionClass
    resource_type: str
    resource_id: str
    expires_at: datetime
    held: bool
    hold_ids: tuple[UUID, ...] = ()


class LegalHold(GovernanceModel):
    id: UUID
    organization_id: UUID
    hold_key: str
    scope_type: str
    scope_id: str
    reason: str
    created_by_user_id: UUID
    created_at: datetime
    released_by_user_id: UUID | None = None
    released_at: datetime | None = None
    release_reason: str | None = None


class DeletionStatus(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    HOLD_BLOCKED = "HOLD_BLOCKED"
    DEACTIVATED = "DEACTIVATED"
    ERASING = "ERASING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DeletionRequest(GovernanceModel):
    id: UUID
    organization_id: UUID
    subject_type: str
    subject_id: str
    status: DeletionStatus
    requested_by_user_id: UUID
    reason: str
    scope: dict[str, Any]
    hold_blockers: tuple[UUID, ...] = ()
    object_gc_status: str
    search_gc_status: str
    requested_at: datetime
    completed_at: datetime | None = None
    updated_at: datetime
    version: int


class AuditExportRequest(GovernanceModel):
    export_format: str = Field(pattern=r"^(JSON|CSV)$")
    filters: dict[str, Any] = Field(default_factory=dict)


class GovernanceError(RuntimeError):
    code = "GOVERNANCE_ERROR"

    def __init__(self, code: str | None = None) -> None:
        super().__init__(code or self.code)
        self.code = code or self.code


class GovernanceForbidden(GovernanceError):
    code = "GOVERNANCE_PERMISSION_DENIED"


class GovernanceConflict(GovernanceError):
    code = "GOVERNANCE_CONFLICT"


class GovernanceNotFound(GovernanceError):
    code = "GOVERNANCE_NOT_FOUND"


class GovernanceUnavailable(GovernanceError):
    code = "GOVERNANCE_UNAVAILABLE"
