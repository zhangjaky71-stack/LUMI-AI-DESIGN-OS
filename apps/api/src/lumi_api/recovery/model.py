from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecoveryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RecoveryDisposition(StrEnum):
    REQUEUE_SAFE = "REQUEUE_SAFE"
    RESUME_SAFE = "RESUME_SAFE"
    RECONCILE_EXTERNAL = "RECONCILE_EXTERNAL"
    VERIFY_OBJECT = "VERIFY_OBJECT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    TERMINAL = "TERMINAL"
    SKIP = "SKIP"


class RecoverySubjectType(StrEnum):
    RUNTIME_JOB = "RUNTIME_JOB"
    IDEMPOTENCY_OPERATION = "IDEMPOTENCY_OPERATION"
    AGENT_RUN = "AGENT_RUN"
    ARTIFACT_FILE = "ARTIFACT_FILE"


class RuntimeJobEvidence(RecoveryModel):
    job_id: UUID
    organization_id: UUID
    project_id: UUID
    operation_id: UUID | None = None
    job_kind: str = Field(min_length=1, max_length=100)
    status: str
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    started_at: datetime | None = None
    next_retry_at: datetime | None = None


class IdempotencyEvidence(RecoveryModel):
    operation_id: UUID
    organization_id: UUID
    operation_type: str = Field(min_length=1, max_length=100)
    status: str
    paid: bool
    side_effect_kind: str
    compensation_mode: str
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    provider_request_id: str | None = None
    result_ref: str | None = None
    recovery_state: str = "none"


class AgentControlEvidence(RecoveryModel):
    agent_run_id: UUID
    organization_id: UUID
    project_id: UUID
    graph_key: str
    graph_version: str
    graph_definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    control_status: str
    checkpoint_id: str | None = None
    checkpoint_namespace: str = ""
    resume_version: int = Field(ge=1)
    current_graph_definition_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    current_graph_enabled: bool = False


class ArtifactObjectEvidence(RecoveryModel):
    artifact_version_id: UUID
    file_id: UUID
    bucket: str = Field(min_length=1, max_length=128)
    storage_key: str = Field(min_length=1, max_length=2_000)
    expected_size_bytes: int = Field(ge=0)
    expected_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("storage_key")
    @classmethod
    def internal_storage_only(cls, value: str) -> str:
        if value.startswith("http") or "://" in value or "X-Amz-Signature" in value:
            raise ValueError("RECOVERY_OBJECT_REF_MUST_BE_INTERNAL")
        return value


class ObjectVerification(RecoveryModel):
    exists: bool
    measured_size_bytes: int | None = Field(default=None, ge=0)
    measured_checksum_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )


class RecoveryDecision(RecoveryModel):
    subject_type: RecoverySubjectType
    subject_id: str = Field(min_length=1, max_length=512)
    disposition: RecoveryDisposition
    reason_code: str = Field(min_length=1, max_length=160)
    preserve_operation_id: UUID | None = None
    preserve_provider_request_id: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecoveryPlan(RecoveryModel):
    organization_id: UUID
    generated_at: datetime
    decisions: tuple[RecoveryDecision, ...]


class RecoveryDrillMeasurement(RecoveryModel):
    scenario: str = Field(min_length=1, max_length=160)
    target_rpo_seconds: int = Field(ge=0)
    target_rto_seconds: int = Field(ge=0)
    measured_data_loss_seconds: int | None = Field(default=None, ge=0)
    measured_restore_seconds: int | None = Field(default=None, ge=0)

    @property
    def has_measured_evidence(self) -> bool:
        return (
            self.measured_data_loss_seconds is not None
            and self.measured_restore_seconds is not None
        )

    @property
    def target_met(self) -> bool:
        if not self.has_measured_evidence:
            return False
        assert self.measured_data_loss_seconds is not None
        assert self.measured_restore_seconds is not None
        return (
            self.measured_data_loss_seconds <= self.target_rpo_seconds
            and self.measured_restore_seconds <= self.target_rto_seconds
        )
