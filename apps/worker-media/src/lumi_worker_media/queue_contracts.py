from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

MAX_JOB_MESSAGE_BYTES = 64 * 1024
MAX_JOB_JSON_DEPTH = 10


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

ROUTING_KEY_BY_JOB_KIND: dict[JobKind, str] = {
    JobKind.IMAGE_TRANSFORM: "image.transform",
    JobKind.VIDEO_RENDER: "video.render",
    JobKind.ASSET_PREVIEW: "asset.processing",
    JobKind.ASSET_VALIDATE: "asset.processing",
    JobKind.EXPORT_PACKAGE: "export.package",
}


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_delay_seconds: int
    max_delay_seconds: int
    jitter_ratio: float = 0.25
    provider_reconciliation_required: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 1 or self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("invalid retry delay bounds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

    def delay_seconds(self, *, attempt: int, jitter_seed: str = "") -> int:
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        exponential = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (attempt - 1)),
        )
        window = max(1, int(exponential * self.jitter_ratio))
        digest = hashlib.sha256(f"{jitter_seed}:{attempt}".encode()).digest()
        jitter = int.from_bytes(digest[:4], "big") % (window + 1)
        return min(self.max_delay_seconds, exponential + jitter)


RETRY_POLICY_BY_JOB_KIND: dict[JobKind, RetryPolicy] = {
    JobKind.IMAGE_TRANSFORM: RetryPolicy(4, 2, 60),
    JobKind.VIDEO_RENDER: RetryPolicy(
        3,
        10,
        180,
        provider_reconciliation_required=True,
    ),
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
    resource_id: UUID | None = None
    traceparent: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        payload = {
            "job_id": str(self.job_id),
            "organization_id": str(self.organization_id),
            "project_id": str(self.project_id),
            "operation_id": str(self.operation_id) if self.operation_id else None,
            "resource_id": str(self.resource_id) if self.resource_id else None,
            "traceparent": self.traceparent,
        }
        validate_job_payload(payload)
        return payload

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> JobMessage:
        allowed = {
            "job_id",
            "organization_id",
            "project_id",
            "operation_id",
            "resource_id",
            "traceparent",
        }
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"JOB_MESSAGE_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
        for required in ("job_id", "organization_id", "project_id"):
            if not value.get(required):
                raise ValueError(f"JOB_MESSAGE_REQUIRED:{required}")
        traceparent = str(value["traceparent"]) if value.get("traceparent") else None
        if traceparent is not None:
            _validate_traceparent(traceparent)
        message = cls(
            job_id=UUID(str(value["job_id"])),
            organization_id=UUID(str(value["organization_id"])),
            project_id=UUID(str(value["project_id"])),
            operation_id=UUID(str(value["operation_id"])) if value.get("operation_id") else None,
            resource_id=UUID(str(value["resource_id"])) if value.get("resource_id") else None,
            traceparent=traceparent,
        )
        validate_job_payload(message.as_dict())
        return message


class JobRuntimeError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def queue_for(job_kind: JobKind | str) -> str:
    return QUEUE_BY_JOB_KIND[JobKind(job_kind)]


def routing_key_for(job_kind: JobKind | str) -> str:
    return ROUTING_KEY_BY_JOB_KIND[JobKind(job_kind)]


def retry_policy_for(job_kind: JobKind | str) -> RetryPolicy:
    return RETRY_POLICY_BY_JOB_KIND[JobKind(job_kind)]


def classify_error(*, code: str | None, retryable: bool | None) -> ErrorCategory:
    normalized = (code or "").upper()
    if normalized in {"CANCELLED", "JOB_CANCELLED", "CANCEL_REQUESTED"}:
        return ErrorCategory.CANCELLED
    if retryable is True:
        return ErrorCategory.TRANSIENT
    if retryable is False:
        return ErrorCategory.PERMANENT
    if normalized in {
        "TIMEOUT",
        "TEMPORARY_FAILURE",
        "RATE_LIMITED",
        "PROVIDER_429",
        "PROVIDER_500",
        "PROVIDER_502",
        "PROVIDER_503",
        "PROVIDER_504",
        "STORAGE_TEMPORARY",
        "BROKER_UNAVAILABLE",
        "CONNECTION_ERROR",
    }:
        return ErrorCategory.TRANSIENT
    return ErrorCategory.PERMANENT


def validate_job_payload(payload: Any) -> None:
    _reject_binary_or_secret(payload, path="$", depth=0)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_JOB_MESSAGE_BYTES:
        raise ValueError("JOB_MESSAGE_TOO_LARGE")


def _reject_binary_or_secret(value: Any, *, path: str, depth: int) -> None:
    if depth > MAX_JOB_JSON_DEPTH:
        raise ValueError("JOB_MESSAGE_TOO_DEEP")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"JOB_MESSAGE_BINARY_FORBIDDEN:{path}")
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).casefold().replace("-", "_")
            forbidden = (
                "secret",
                "password",
                "api_key",
                "apikey",
                "access_token",
                "refresh_token",
                "authorization",
                "credential",
                "presigned_url",
                "signed_url",
            )
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


def _validate_traceparent(value: str) -> None:
    parts = value.split("-")
    if len(parts) != 4:
        raise ValueError("JOB_TRACEPARENT_INVALID")
    version, trace_id, parent_id, flags = parts
    if (
        len(version) != 2
        or len(trace_id) != 32
        or len(parent_id) != 16
        or len(flags) != 2
    ):
        raise ValueError("JOB_TRACEPARENT_INVALID")
    try:
        int(version + trace_id + parent_id + flags, 16)
    except ValueError as exc:
        raise ValueError("JOB_TRACEPARENT_INVALID") from exc
