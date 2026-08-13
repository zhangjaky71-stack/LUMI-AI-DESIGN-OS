from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

MAX_JOB_MESSAGE_BYTES = 64 * 1024


class JobKind(StrEnum):
    IMAGE_TRANSFORM = "image.transform"
    VIDEO_RENDER = "video.render"
    ASSET_PREVIEW = "asset.preview"
    ASSET_VALIDATE = "asset.validate"
    EXPORT_PACKAGE = "export.package"


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCategory(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CANCELLED = "cancelled"


QUEUE_BY_JOB_KIND: dict[JobKind, str] = {
    JobKind.IMAGE_TRANSFORM: "lumi.media.image",
    JobKind.VIDEO_RENDER: "lumi.media.video",
    JobKind.ASSET_PREVIEW: "lumi.asset.processing",
    JobKind.ASSET_VALIDATE: "lumi.asset.processing",
    JobKind.EXPORT_PACKAGE: "lumi.media.export",
}


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int
    provider_reconciliation_required: bool = False

    def delay_seconds(self, *, attempt: int, jitter_seed: int = 0) -> int:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        exponential = self.base_delay_seconds * (2 ** (attempt - 1))
        bounded = min(exponential, self.max_delay_seconds)
        jitter_window = max(1, bounded // 4)
        return min(self.max_delay_seconds, bounded + (jitter_seed % jitter_window))


RETRY_POLICY_BY_JOB_KIND: dict[JobKind, RetryPolicy] = {
    JobKind.IMAGE_TRANSFORM: RetryPolicy(4, 2, 60),
    JobKind.VIDEO_RENDER: RetryPolicy(3, 10, 180, provider_reconciliation_required=True),
    JobKind.ASSET_PREVIEW: RetryPolicy(4, 2, 60),
    JobKind.ASSET_VALIDATE: RetryPolicy(4, 3, 90),
    JobKind.EXPORT_PACKAGE: RetryPolicy(3, 5, 120),
}


@dataclass(frozen=True, slots=True)
class JobMessage:
    job_id: UUID
    organization_id: UUID
    project_id: UUID
    operation_id: UUID | None = None
    trace_id: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "job_id": str(self.job_id),
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> JobMessage:
        allowed = {"job_id", "organization_id", "project_id", "operation_id", "trace_id"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"JOB_MESSAGE_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
        for required in ("job_id", "organization_id", "project_id"):
            if not value.get(required):
                raise ValueError(f"JOB_MESSAGE_REQUIRED:{required}")
        message = cls(
            job_id=UUID(str(value["job_id"])),
            organization_id=UUID(str(value["organization_id"])),
            project_id=UUID(str(value["project_id"])),
            operation_id=UUID(str(value["operation_id"])) if value.get("operation_id") else None,
            trace_id=str(value["trace_id"]) if value.get("trace_id") else None,
        )
        validate_job_payload(message.as_dict())
        return message


def queue_for(job_kind: JobKind | str) -> str:
    return QUEUE_BY_JOB_KIND[JobKind(job_kind)]


def retry_policy_for(job_kind: JobKind | str) -> RetryPolicy:
    return RETRY_POLICY_BY_JOB_KIND[JobKind(job_kind)]


def classify_error(*, code: str | None, retryable: bool | None) -> ErrorCategory:
    if code == "CANCELLED":
        return ErrorCategory.CANCELLED
    if retryable is True:
        return ErrorCategory.TRANSIENT
    if retryable is False:
        return ErrorCategory.PERMANENT
    normalized = (code or "").upper()
    if normalized in {
        "TIMEOUT",
        "RATE_LIMITED",
        "PROVIDER_429",
        "PROVIDER_500",
        "PROVIDER_502",
        "PROVIDER_503",
        "PROVIDER_504",
        "STORAGE_TEMPORARY",
        "BROKER_UNAVAILABLE",
    }:
        return ErrorCategory.TRANSIENT
    return ErrorCategory.PERMANENT


def validate_job_payload(payload: Any) -> None:
    _reject_binary_or_secret(payload, path="$", depth=0)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JOB_MESSAGE_BYTES:
        raise ValueError("JOB_MESSAGE_TOO_LARGE")


def _reject_binary_or_secret(value: Any, *, path: str, depth: int) -> None:
    if depth > 12:
        raise ValueError("JOB_MESSAGE_TOO_DEEP")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"JOB_MESSAGE_BINARY_FORBIDDEN:{path}")
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            forbidden = ("secret", "password", "api_key", "access_token")
            if any(token in key_text for token in forbidden):
                raise ValueError(f"JOB_MESSAGE_SECRET_FIELD_FORBIDDEN:{path}.{key}")
            _reject_binary_or_secret(child, path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_binary_or_secret(child, path=f"{path}[{index}]", depth=depth + 1)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise ValueError(f"JOB_MESSAGE_NON_JSON_VALUE:{path}")
