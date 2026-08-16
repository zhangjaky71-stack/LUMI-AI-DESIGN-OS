from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_worker_media.job_runtime import (
    JobRecord,
    MemoryJobStore,
    ProviderReconciliation,
    ProviderReconciliationStatus,
    execute_job,
)
from lumi_worker_media.queue_contracts import (
    ErrorCategory,
    JobKind,
    JobMessage,
    JobState,
    classify_error,
    queue_for,
    retry_policy_for,
    validate_job_payload,
)
from lumi_worker_media.recovery import recover_stale_memory_jobs

NOW = datetime(2026, 8, 16, 8, 45, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
JOB = UUID("01910000-0000-7000-8000-000000000601")


def message() -> JobMessage:
    return JobMessage(job_id=JOB, organization_id=ORG, project_id=PROJECT)


def store_for(kind: JobKind, *, max_attempts: int = 4) -> MemoryJobStore:
    store = MemoryJobStore()
    store.create(
        JobRecord(
            message=message(),
            kind=kind,
            max_attempts=max_attempts,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return store


def test_queue_separation_is_frozen() -> None:
    assert queue_for(JobKind.IMAGE_TRANSFORM) == "lumi.media.image"
    assert queue_for(JobKind.VIDEO_RENDER) == "lumi.media.video"
    assert queue_for(JobKind.EXPORT_PACKAGE) == "lumi.media.export"
    assert queue_for(JobKind.ASSET_VALIDATE) == "lumi.asset.processing"
    assert queue_for(JobKind.ASSET_PREVIEW) == "lumi.asset.processing"


def test_job_message_rejects_binary_secrets_and_oversize() -> None:
    with pytest.raises(ValueError, match="BINARY_FORBIDDEN"):
        validate_job_payload({"blob": b"binary"})
    with pytest.raises(ValueError, match="SECRET_FIELD_FORBIDDEN"):
        validate_job_payload({"provider_api_key": "secret"})
    with pytest.raises(ValueError, match="SECRET_FIELD_FORBIDDEN"):
        validate_job_payload({"signed_url": "https://storage.invalid/x"})
    with pytest.raises(ValueError, match="TOO_LARGE"):
        validate_job_payload({"text": "x" * (65 * 1024)})


def test_retry_is_exponential_bounded_and_deterministic() -> None:
    policy = retry_policy_for(JobKind.IMAGE_TRANSFORM)
    delays = [policy.delay_seconds(attempt=i, jitter_seed="job") for i in range(1, 5)]
    assert delays == sorted(delays)
    assert all(delay <= policy.max_delay_seconds for delay in delays)
    assert delays == [policy.delay_seconds(attempt=i, jitter_seed="job") for i in range(1, 5)]


def test_transient_failure_moves_job_to_retrying() -> None:
    store = store_for(JobKind.IMAGE_TRANSFORM)

    class Temporary(RuntimeError):
        code = "PROVIDER_503"
        retryable = True

    def handler(_message: JobMessage):
        raise Temporary("temporary")

    result = execute_job(
        store=store,
        message=message(),
        kind=JobKind.IMAGE_TRANSFORM,
        handler=handler,
        now=NOW,
    )
    assert result.record.state is JobState.RETRYING
    assert result.record.error_category is ErrorCategory.TRANSIENT
    assert result.retry_in_seconds is not None and result.retry_in_seconds > 0


def test_permanent_failure_does_not_retry() -> None:
    store = store_for(JobKind.IMAGE_TRANSFORM)

    class Invalid(RuntimeError):
        code = "INVALID_INPUT"
        retryable = False

    def handler(_message: JobMessage):
        raise Invalid("bad request")

    result = execute_job(
        store=store,
        message=message(),
        kind=JobKind.IMAGE_TRANSFORM,
        handler=handler,
        now=NOW,
    )
    assert result.record.state is JobState.FAILED
    assert result.record.error_category is ErrorCategory.PERMANENT
    assert result.retry_in_seconds is None


def test_video_retry_fails_safe_without_provider_reconciliation() -> None:
    store = store_for(JobKind.VIDEO_RENDER)

    class Timeout(RuntimeError):
        code = "TIMEOUT"
        retryable = True

    def handler(_message: JobMessage):
        raise Timeout("provider request timed out")

    result = execute_job(
        store=store,
        message=message(),
        kind=JobKind.VIDEO_RENDER,
        handler=handler,
        now=NOW,
    )
    assert result.record.state is JobState.FAILED
    assert result.record.error_code == "PROVIDER_RECONCILIATION_REQUIRED"


def test_video_reconciliation_uses_existing_success_instead_of_double_retry() -> None:
    store = store_for(JobKind.VIDEO_RENDER)

    class Timeout(RuntimeError):
        code = "TIMEOUT"
        retryable = True

    class Reconciler:
        def reconcile(self, _message: JobMessage) -> ProviderReconciliation:
            return ProviderReconciliation(
                ProviderReconciliationStatus.SUCCEEDED,
                {"provider_request": "already-completed"},
            )

    def handler(_message: JobMessage):
        raise Timeout("provider response lost")

    result = execute_job(
        store=store,
        message=message(),
        kind=JobKind.VIDEO_RENDER,
        handler=handler,
        now=NOW,
        reconciler=Reconciler(),
    )
    assert result.record.state is JobState.SUCCEEDED
    assert result.record.output == {"provider_request": "already-completed"}


def test_cancellation_is_db_state_not_process_kill() -> None:
    store = store_for(JobKind.IMAGE_TRANSFORM)
    store.request_cancel(message(), now=NOW)
    called = False

    def handler(_message: JobMessage):
        nonlocal called
        called = True
        return {"ok": True}

    result = execute_job(
        store=store,
        message=message(),
        kind=JobKind.IMAGE_TRANSFORM,
        handler=handler,
        now=NOW,
    )
    assert called is False
    assert result.record.state is JobState.CANCELLED


def test_stale_running_worker_is_recovered_without_acks_late() -> None:
    store = store_for(JobKind.IMAGE_TRANSFORM)
    claimed = store.claim(message(), now=NOW)
    assert claimed is not None and claimed.state is JobState.RUNNING
    recovered = recover_stale_memory_jobs(
        store,
        now=NOW + timedelta(minutes=6),
        stale_after=timedelta(minutes=5),
    )
    assert len(recovered) == 1
    assert recovered[0].state is JobState.RETRYING
    assert recovered[0].error_code == "WORKER_STALE_RECOVERY"


def test_error_classifier_is_fail_closed() -> None:
    assert classify_error(code="PROVIDER_503", retryable=None) is ErrorCategory.TRANSIENT
    assert classify_error(code="UNKNOWN_PROVIDER_EXCEPTION", retryable=None) is ErrorCategory.PERMANENT
