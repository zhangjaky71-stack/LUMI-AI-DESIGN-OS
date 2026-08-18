from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lumi_api.approvals import (
    ApprovalDecisionKind,
    ApprovalEffectStatus,
    ApprovalEffectType,
    ApprovalPolicyMode,
    ApprovalStatus,
    ApprovalType,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateArtifactApprovalRequest(ApiModel):
    artifact_version_id: UUID
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4_000)
    expires_at: datetime | None = None


class ApprovalDecisionRequest(ApiModel):
    decision: ApprovalDecisionKind
    reason: str | None = Field(default=None, max_length=4_000)
    comment: str | None = Field(default=None, max_length=4_000)
    node_ids: tuple[UUID, ...] = Field(default=(), max_length=256)
    requested_changes: tuple[str, ...] = Field(default=(), max_length=128)

    @model_validator(mode="after")
    def validate_feedback(self) -> "ApprovalDecisionRequest":
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("node_ids must be unique")
        if self.decision != ApprovalDecisionKind.APPROVED and not (
            self.reason or self.comment or self.requested_changes
        ):
            raise ValueError("rejection/changes decision requires feedback")
        return self


class ApprovalResponse(ApiModel):
    id: UUID
    project_id: UUID
    agent_run_id: UUID | None = None
    task_id: UUID | None = None
    approval_type: ApprovalType
    subject_type: str
    subject_id: UUID
    subject_version_ref: str
    artifact_version_id: UUID | None = None
    status: ApprovalStatus
    requested_by: str
    required_permission: str
    policy_mode: ApprovalPolicyMode
    policy_version: int
    min_approvals: int
    title: str
    summary: str
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    interrupt_id: str | None = None
    created_at: datetime
    updated_at: datetime
    version: int


class ApprovalEffectResponse(ApiModel):
    id: UUID
    effect_type: ApprovalEffectType
    status: ApprovalEffectStatus
    attempt_count: int = Field(ge=0)
    last_error: str | None = None
    completed_at: datetime | None = None


class ApprovalDecisionResponse(ApiModel):
    approval: ApprovalResponse
    decision_id: UUID
    effects: tuple[ApprovalEffectResponse, ...] = ()


class ApprovalAuditResponse(ApiModel):
    id: UUID
    action: str
    actor_id: str | None = None
    status_from: ApprovalStatus | None = None
    status_to: ApprovalStatus | None = None
    created_at: datetime
