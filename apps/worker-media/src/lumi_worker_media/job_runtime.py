from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from .queue_contracts import (
    ErrorCategory,
    JobKind,
    JobMessage,
    JobState,
    classify_error,
    retry_policy_for,
    validate_job_payload,
)


@dataclass(frozen=True, slots=True)
class JobRecord:
    message: JobMessage
    kind: JobKind
    state: JobState = JobState.PENDING
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    next_retry_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    output: dict[str, Any] | None = None
    error_category: ErrorCategory | None = None
    error_code: str | None = None
    error_message: str | None = None


class JobStore(Protocol):
    def create(self, record: JobRecord) -> None: ...

    def get(self, message: JobMessage) -> JobRecord | None: ...

    def claim(self, message: JobMessage, *, now: datetime) -> JobRecord | None: ...

    def request_cancel(self, message: JobMessage, *, now: datetime) -> JobRecord | None: ...

    def cancellation_requested(self, message: JobMessage) -> bool: ...

    def retry(
        self,
        message: JobMessage,
        *,
        now: datetime,
        next_retry_at: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
    ) -> JobRecord: ...

    def succeed(
        self,
        message: JobMessage,
        *,
        now: datetime,
        output: dict[str, Any],
    ) -> JobRecord: ...

    def fail(
        self,
        message: JobMessage,
        *,
        now: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
    ) -> JobRecord: ...

    def cancel(self, message: JobMessage, *, now: datetime) -> JobRecord: ...


class MemoryJobStore(JobStore):
    def __init__(self) -> None:
        self.records: dict[object, JobRecord] = {}

    def create(self, record: JobRecord) -> None:
        key = record.message.job_id
        if key in self.records:
            raise ValueError("JOB_ALREADY_EXISTS")
        self.records[key] = record

    def get(self, message: JobMessage) -> JobRecord | None:
        record = self.records.get(message.job_id)
        if record is None:
            return None
        if (
            record.message.organization_id != message.organization_id
            or record.message.project_id != message.project_id
        ):
            return None
        return record

    def claim(self, message: JobMessage, *, now: datetime) -> JobRecord | None:
        record = self.get(message)
        if record is None:
            return None
        if record.cancellation_requested_at is not None:
            return None
        if record.state not in {JobState.PENDING, JobState.RETRYING}:
            return None
        if record.next_retry_at is not None and record.next_retry_at > now:
            return None
        if record.attempt_count >= record.max_attempts:
            return None
        claimed = replace(
            record,
            state=JobState.RUNNING,
            attempt_count=record.attempt_count + 1,
            started_at=record.started_at or now,
            updated_at=now,
            next_retry_at=None,
        )
        self.records[message.job_id] = claimed
        return claimed

    def request_cancel(self, message: JobMessage, *, now: datetime) -> JobRecord | None:
        record = self.get(message)
        if record is None or record.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
            return record
        updated = replace(record, cancellation_requested_at=now, updated_at=now)
        self.records[message.job_id] = updated
        return updated

    def cancellation_requested(self, message: JobMessage) -> bool:
        record = self.get(message)
        return bool(record and record.cancellation_requested_at is not None)

    def retry(
        self,
        message: JobMessage,
        *,
        now: datetime,
        next_retry_at: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
    ) -> JobRecord:
        record = self._required_running(message)
        updated = replace(
            record,
            state=JobState.RETRYING,
            updated_at=now,
            next_retry_at=next_retry_at,
            error_category=category,
            error_code=code[:128],
            error_message=error_message[:2000],
        )
        self.records[message.job_id] = updated
        return updated

    def succeed(
        self,
        message: JobMessage,
        *,
        now: datetime,
        output: dict[str, Any],
    ) -> JobRecord:
        validate_job_payload(output)
        record = self._required_running(message)
        updated = replace(
            record,
            state=JobState.SUCCEEDED,
            updated_at=now,
            finished_at=now,
            output=dict(output),
            error_category=None,
            error_code=None,
            error_message=None,
        )
        self.records[message.job_id] = updated
        return updated

    def fail(
        self,
        message: JobMessage,
        *,
        now: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
    ) -> JobRecord:
        record = self._required_running(message)
        updated = replace(
            record,
            state=JobState.FAILED,
            updated_at=now,
            finished_at=now,
            error_category=category,
            error_code=code[:128],
            error_message=error_message[:2000],
        )
        self.records[message.job_id] = updated
        return updated

    def cancel(self, message: JobMessage, *, now: datetime) -> JobRecord:
        record = self.get(message)
        if record is None:
            raise ValueError("JOB_NOT_FOUND")
        updated = replace(
            record,
            state=JobState.CANCELLED,
            updated_at=now,
            finished_at=now,
        )
        self.records[message.job_id] = updated
        return updated

    def _required_running(self, message: JobMessage) -> JobRecord:
        record = self.get(message)
        if record is None:
            raise ValueError("JOB_NOT_FOUND")
        if record.state is not JobState.RUNNING:
            raise ValueError("JOB_NOT_RUNNING")
        return record


class JobHandler(Protocol):
    def __call__(self, message: JobMessage) -> dict[str, Any]: ...


class ProviderReconciliationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RUNNING = "running"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderReconciliation:
    status: ProviderReconciliationStatus
    output: dict[str, Any] | None = None


class ProviderReconciler(Protocol):
    def reconcile(self, message: JobMessage) -> ProviderReconciliation: ...


@dataclass(frozen=True, slots=True)
class JobExecutionResult:
    record: JobRecord
    retry_in_seconds: int | None = None


class JobCancelled(RuntimeError):
    code = "JOB_CANCELLED"
    retryable = False


def execute_job(
    *,
    store: JobStore,
    message: JobMessage,
    kind: JobKind,
    handler: JobHandler,
    now: datetime | None = None,
    reconciler: ProviderReconciler | None = None,
) -> JobExecutionResult:
    current_time = now or datetime.now(UTC)
    if store.cancellation_requested(message):
        return JobExecutionResult(store.cancel(message, now=current_time))
    claimed = store.claim(message, now=current_time)
    if claimed is None:
        record = store.get(message)
        if record is None:
            raise ValueError("JOB_NOT_FOUND_OR_TENANT_MISMATCH")
        return JobExecutionResult(record)
    policy = retry_policy_for(kind)
    try:
        output = handler(message)
        validate_job_payload(output)
        if store.cancellation_requested(message):
            raise JobCancelled("JOB_CANCELLED")
        return JobExecutionResult(store.succeed(message, now=current_time, output=output))
    except JobCancelled:
        return JobExecutionResult(store.cancel(message, now=current_time))
    except Exception as exc:
        code = str(getattr(exc, "code", type(exc).__name__))
        category = classify_error(code=code, retryable=getattr(exc, "retryable", None))
        if category is ErrorCategory.CANCELLED:
            return JobExecutionResult(store.cancel(message, now=current_time))
        retry_allowed = (
            category is ErrorCategory.TRANSIENT
            and claimed.attempt_count < min(claimed.max_attempts, policy.max_attempts)
        )
        if retry_allowed and policy.provider_reconciliation_required:
            if reconciler is None:
                retry_allowed = False
                category = ErrorCategory.PERMANENT
                code = "PROVIDER_RECONCILIATION_REQUIRED"
            else:
                reconciliation = reconciler.reconcile(message)
                if reconciliation.status is ProviderReconciliationStatus.SUCCEEDED:
                    output = reconciliation.output or {"reconciled": True}
                    validate_job_payload(output)
                    return JobExecutionResult(
                        store.succeed(message, now=current_time, output=output)
                    )
                if reconciliation.status is ProviderReconciliationStatus.RUNNING:
                    code = "PROVIDER_STILL_RUNNING"
        if retry_allowed:
            delay = policy.delay_seconds(
                attempt=claimed.attempt_count,
                jitter_seed=str(message.job_id),
            )
            record = store.retry(
                message,
                now=current_time,
                next_retry_at=current_time + timedelta(seconds=delay),
                category=category,
                code=code,
                error_message=str(exc),
            )
            return JobExecutionResult(record, retry_in_seconds=delay)
        return JobExecutionResult(
            store.fail(
                message,
                now=current_time,
                category=category,
                code=code,
                error_message=str(exc),
            )
        )
