from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApprovalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ApprovalType(StrEnum):
    CREATIVE_DIRECTION = "CREATIVE_DIRECTION"
    ARTIFACT_VERSION = "ARTIFACT_VERSION"
    BRAND_RULE_SET = "BRAND_RULE_SET"
    BUDGET_INCREASE = "BUDGET_INCREASE"
    EXTERNAL_PUBLISH = "EXTERNAL_PUBLISH"
    DESTRUCTIVE_ACTION = "DESTRUCTIVE_ACTION"
    CUSTOM_REVIEW = "CUSTOM_REVIEW"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class ApprovalDecisionKind(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


class ApprovalPolicyMode(StrEnum):
    ANY_ONE = "ANY_ONE"
    ALL = "ALL"
    MIN_N = "MIN_N"
    ROLE_BASED_SEQUENCE = "ROLE_BASED_SEQUENCE"


class ApprovalEffectType(StrEnum):
    ARTIFACT_VERSION_APPROVE = "ARTIFACT_VERSION_APPROVE"
    AGENT_RUN_RESUME = "AGENT_RUN_RESUME"


class ApprovalEffectStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalRecord(ApprovalModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    approval_type: ApprovalType
    subject_type: str = Field(min_length=1, max_length=80)
    subject_id: UUID
    subject_version_ref: str = Field(min_length=1, max_length=160)
    subject_snapshot_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    artifact_version_id: UUID | None = None
    status: ApprovalStatus
    requested_by: str = Field(min_length=1, max_length=200)
    required_permission: str = Field(min_length=1, max_length=120)
    policy_mode: ApprovalPolicyMode
    policy_version: int = Field(ge=1)
    min_approvals: int = Field(ge=1)
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    changes_requested: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    superseded_by_id: UUID | None = None
    interrupt_id: str | None = Field(default=None, max_length=200)
    resume_version: int | None = Field(default=None, ge=0)
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_bridge_and_subject(self) -> "ApprovalRecord":
        if (self.interrupt_id is None) != (self.resume_version is None):
            raise ValueError("interrupt_id and resume_version must be paired")
        if self.approval_type == ApprovalType.ARTIFACT_VERSION:
            if self.artifact_version_id is None or self.subject_id != self.artifact_version_id:
                raise ValueError("artifact approval must bind exact artifact_version_id")
            if self.subject_snapshot_hash is None:
                raise ValueError("artifact approval requires subject snapshot hash")
        return self


class ApprovalDecision(ApprovalModel):
    id: UUID
    organization_id: UUID
    approval_id: UUID
    operation_id: UUID
    decision: ApprovalDecisionKind
    actor_id: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4_000)
    feedback: dict[str, Any] = Field(default_factory=dict)
    approval_version: int = Field(ge=1)
    created_at: datetime

    @model_validator(mode="after")
    def feedback_required_for_non_approval(self) -> "ApprovalDecision":
        if self.decision != ApprovalDecisionKind.APPROVED and not (self.reason or self.feedback):
            raise ValueError("rejection/changes decision requires reason or feedback")
        return self


class ApprovalAuditEntry(ApprovalModel):
    id: UUID
    organization_id: UUID
    approval_id: UUID
    action: str = Field(min_length=1, max_length=100)
    actor_id: str | None = Field(default=None, max_length=200)
    status_from: ApprovalStatus | None = None
    status_to: ApprovalStatus | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ApprovalEffect(ApprovalModel):
    id: UUID
    organization_id: UUID
    approval_id: UUID
    effect_type: ApprovalEffectType
    status: ApprovalEffectStatus
    operation_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
    attempt_count: int = Field(ge=0)
    last_error: str | None = Field(default=None, max_length=2_000)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ArtifactApprovalRequest(ApprovalModel):
    organization_id: UUID
    project_id: UUID
    artifact_version_id: UUID
    requested_by: str = Field(min_length=1, max_length=200)
    payload_summary: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    interrupt_id: str | None = Field(default=None, max_length=200)
    resume_version: int | None = Field(default=None, ge=0)
    requested_at: datetime

    @model_validator(mode="after")
    def validate_bridge_pair(self) -> "ArtifactApprovalRequest":
        if (self.interrupt_id is None) != (self.resume_version is None):
            raise ValueError("interrupt_id and resume_version must be paired")
        return self


class ApprovalDecisionCommand(ApprovalModel):
    organization_id: UUID
    approval_id: UUID
    operation_id: UUID
    decision: ApprovalDecisionKind
    actor_id: str = Field(min_length=1, max_length=200)
    actor_permissions: tuple[str, ...] = ()
    reason: str | None = Field(default=None, max_length=4_000)
    feedback: dict[str, Any] = Field(default_factory=dict)
    decided_at: datetime

    @field_validator("actor_permissions")
    @classmethod
    def canonicalize_permissions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))
