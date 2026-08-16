from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lumi_api.domain.ids import new_uuid7

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_OPERATION_TYPE_PATTERN = r"^[a-z][a-z0-9_.:-]{0,99}$"


class OperationStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_FINAL = "failed_final"


class RecoveryState(StrEnum):
    NONE = "none"
    RECONCILING = "reconciling"
    AMBIGUOUS = "ambiguous"


class SideEffectKind(StrEnum):
    PAID_MODEL_INVOCATION = "paid_model_invocation"
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    EXTERNAL_TOOL_WRITE = "external_tool_write"
    OBJECT_FINALIZATION = "object_finalization"
    BILLING_CHARGE = "billing_charge"
    BILLING_CREDIT = "billing_credit"
    EMAIL_SEND = "email_send"
    EXPORT_CREATION = "export_creation"
    EXTERNAL_PUBLISH = "external_publish"
    GENERIC_WRITE = "generic_write"


class CompensationMode(StrEnum):
    COMPENSATABLE = "compensatable"
    NON_COMPENSATABLE = "non_compensatable"
    REVERSIBLE_BY_NEW_OPERATION = "reversible_by_new_operation"


class ErrorCategory(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AMBIGUOUS = "ambiguous"


class ProviderReconciliationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RUNNING = "running"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class AcquireAction(StrEnum):
    EXECUTE = "execute"
    REPLAY = "replay"
    WAIT = "wait"
    FINAL_FAILURE = "final_failure"
    RECOVER = "recover"
    CONFLICT = "conflict"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class OperationRequest(FrozenModel):
    organization_id: UUID
    operation_type: str = Field(pattern=_OPERATION_TYPE_PATTERN)
    idempotency_key: str = Field(min_length=8, max_length=255)
    request_hash: str = Field(pattern=_SHA256_PATTERN)
    business_scope_id: str | None = Field(default=None, max_length=255)
    side_effect_kind: SideEffectKind
    compensation_mode: CompensationMode
    paid: bool = False
    lease_seconds: int = Field(default=60, ge=5, le=3600)
    ttl_seconds: int = Field(default=86400, ge=300, le=2592000)


class IdempotencyOperation(FrozenModel):
    id: UUID = Field(default_factory=new_uuid7)
    organization_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=255)
    operation_type: str = Field(pattern=_OPERATION_TYPE_PATTERN)
    request_hash: str = Field(pattern=_SHA256_PATTERN)
    business_scope_id: str | None = Field(default=None, max_length=255)
    side_effect_kind: SideEffectKind
    compensation_mode: CompensationMode
    paid: bool = False
    status: OperationStatus = OperationStatus.NEW
    recovery_state: RecoveryState = RecoveryState.NONE
    lease_owner: str | None = Field(default=None, max_length=160)
    lease_expires_at: datetime | None = None
    provider_request_id: str | None = Field(default=None, max_length=255)
    result_ref: str | None = Field(default=None, max_length=2048)
    response_status: int | None = Field(default=None, ge=100, le=599)
    response_json: dict[str, Any] | None = None
    error_category: ErrorCategory | None = None
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=2000)
    recovery_detail: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    version: int = Field(default=1, ge=1)

    @field_validator(
        "lease_expires_at", "expires_at", "created_at", "updated_at", "completed_at"
    )
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("idempotency timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_state(self) -> "IdempotencyOperation":
        if (self.lease_owner is None) != (self.lease_expires_at is None):
            raise ValueError("lease owner and expiry must be present together")
        if self.status is OperationStatus.SUCCEEDED and self.completed_at is None:
            raise ValueError("succeeded operation requires completed_at")
        if self.status is OperationStatus.FAILED_FINAL and self.completed_at is None:
            raise ValueError("final failure requires completed_at")
        if self.recovery_state is RecoveryState.AMBIGUOUS:
            if self.error_category is not ErrorCategory.AMBIGUOUS:
                raise ValueError("ambiguous recovery requires ambiguous error category")
        return self


class AcquireResult(FrozenModel):
    action: AcquireAction
    operation: IdempotencyOperation


class ProviderReconciliation(FrozenModel):
    status: ProviderReconciliationStatus
    provider_request_id: str | None = Field(default=None, max_length=255)
    response_status: int | None = Field(default=None, ge=100, le=599)
    result_ref: str | None = Field(default=None, max_length=2048)
    result: dict[str, Any] | None = None
    detail: str | None = Field(default=None, max_length=2000)


class SideEffectOutcome(FrozenModel):
    result: dict[str, Any] = Field(default_factory=dict)
    result_ref: str | None = Field(default=None, max_length=2048)
    response_status: int = Field(default=200, ge=100, le=599)
    provider_request_id: str | None = Field(default=None, max_length=255)
    replayed: bool = False
    operation_id: UUID | None = None
