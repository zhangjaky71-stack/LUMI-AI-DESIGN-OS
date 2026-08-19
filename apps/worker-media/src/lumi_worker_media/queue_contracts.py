from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lumi_domain.job_dispatch import MAX_JOB_MESSAGE_BYTES, JobMessage, validate_job_payload


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


__all__ = [
    "MAX_JOB_MESSAGE_BYTES",
    "ErrorCategory",
    "JobKind",
    "JobMessage",
    "JobState",
    "RetryPolicy",
    "classify_error",
    "queue_for",
    "retry_policy_for",
    "validate_job_payload",
]
