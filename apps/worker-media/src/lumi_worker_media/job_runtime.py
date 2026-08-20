from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

import asyncpg
from lumi_domain.performance_events import (
    PerformanceStage,
    PerformanceTelemetryContext,
    emit_performance_interval,
)

from .queue_contracts import ErrorCategory, JobMessage, JobState, classify_error


class JobCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalWait:
    """Normal non-terminal wait for an external asynchronous system.

    This is not an exception and must never consume the task's error-retry budget.
    A durable wake scheduler will redispatch the same canonical JobDispatch after
    retry_not_before. The external_ref is an opaque provider-neutral correlation id.
    """

    wait_reason: str
    external_ref: str
    retry_not_before: datetime
    output: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            not self.wait_reason
            or self.wait_reason != self.wait_reason.strip()
            or len(self.wait_reason) > 255
            or any(char in self.wait_reason for char in ("\x00", "\n", "\r"))
        ):
            raise ValueError("EXTERNAL_WAIT_REASON_INVALID")
        if (
            not self.external_ref
            or self.external_ref != self.external_ref.strip()
            or len(self.external_ref) > 1024
            or any(char in self.external_ref for char in ("\x00", "\n", "\r"))
        ):
            raise ValueError("EXTERNAL_WAIT_REF_INVALID")
        if self.retry_not_before.tzinfo is None:
            raise ValueError("EXTERNAL_WAIT_RETRY_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        _json(self.output)


class JobHandler(Protocol):
    async def __call__(self, message: JobMessage) -> dict[str, Any] | ExternalWait: ...


@dataclass(frozen=True, slots=True)
class JobOutcome:
    state: JobState
    attempt_count: int
    output: dict[str, Any]


class TaskJobStore:
    """Uses canonical `tasks` rows for claim/terminal/external-wait lifecycle."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def claim(self, message: JobMessage) -> int | None:
        telemetry = PerformanceTelemetryContext.from_environ()
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                WITH candidate AS (
                    SELECT id, status AS prior_status
                    FROM tasks
                    WHERE id = $1
                      AND organization_id = $2
                      AND project_id = $3
                      AND (
                        (
                          status IN ('pending', 'retrying')
                          AND attempt_count < max_attempts
                          AND (retry_not_before IS NULL OR retry_not_before <= now())
                        )
                        OR (
                          status = 'waiting_external'
                          AND retry_not_before IS NULL
                        )
                      )
                    FOR UPDATE
                )
                UPDATE tasks AS task
                SET status = 'running',
                    attempt_count = task.attempt_count +
                        CASE WHEN candidate.prior_status = 'waiting_external' THEN 0 ELSE 1 END,
                    started_at = COALESCE(task.started_at, now()),
                    updated_at = now(),
                    state_version = task.state_version + 1,
                    version = task.version + 1
                FROM candidate
                WHERE task.id = candidate.id
                RETURNING task.attempt_count, task.created_at, task.started_at,
                          candidate.prior_status
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
            if row is None:
                return None
            attempt_count = int(row["attempt_count"])
            if (
                telemetry is not None
                and attempt_count == 1
                and row["prior_status"] != JobState.WAITING_EXTERNAL.value
            ):
                emit_performance_interval(
                    telemetry,
                    stage=PerformanceStage.ENQUEUE,
                    service="worker-media",
                    operation_id=str(message.operation_id or message.job_id),
                    task_id=str(message.job_id),
                    started_at_unix_ns=_datetime_unix_ns(row["created_at"]),
                    completed_at_unix_ns=_datetime_unix_ns(row["started_at"]),
                    attempt=attempt_count,
                )
            return attempt_count
        finally:
            await connection.close()

    async def cancellation_requested(self, message: JobMessage) -> bool:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                SELECT status, cancellation_requested_at FROM tasks
                WHERE id = $1 AND organization_id = $2 AND project_id = $3
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
            return row is not None and (
                row["status"] == JobState.CANCELLED.value
                or row["cancellation_requested_at"] is not None
            )
        finally:
            await connection.close()

    async def cancel(self, message: JobMessage) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                UPDATE tasks
                SET status = 'cancelled', finished_at = now(),
                    wait_reason = NULL, external_ref = NULL, retry_not_before = NULL,
                    updated_at = now(), state_version = state_version + 1,
                    version = version + 1
                WHERE id = $1 AND organization_id = $2 AND project_id = $3
                  AND status IN ('pending', 'running', 'retrying', 'waiting_external')
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
        finally:
            await connection.close()

    async def wait_external(self, message: JobMessage, wait: ExternalWait) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT status, output_json
                    FROM tasks
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                    FOR UPDATE
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                )
                if row is None:
                    raise RuntimeError("JOB_NOT_FOUND")
                if row["status"] != JobState.RUNNING.value:
                    raise RuntimeError("JOB_EXTERNAL_WAIT_REQUIRES_RUNNING")
                output = dict(row["output_json"] or {})
                output.update(wait.output)
                output["external_wait"] = {
                    "reason": wait.wait_reason,
                    "external_ref": wait.external_ref,
                    "retry_not_before": wait.retry_not_before.astimezone(UTC).isoformat(),
                }
                await connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'waiting_external', output_json = $4::jsonb,
                        wait_reason = $5, external_ref = $6, retry_not_before = $7,
                        finished_at = NULL, updated_at = now(),
                        state_version = state_version + 1, version = version + 1
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                      AND status = 'running'
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    _json(output),
                    wait.wait_reason,
                    wait.external_ref,
                    wait.retry_not_before.astimezone(UTC),
                )
        finally:
            await connection.close()

    async def succeed(self, message: JobMessage, output: dict[str, Any]) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'succeeded', output_json = $4::jsonb,
                        finished_at = now(), wait_reason = NULL,
                        external_ref = NULL, retry_not_before = NULL,
                        updated_at = now(), state_version = state_version + 1,
                        version = version + 1
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                      AND status = 'running'
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    _json(output),
                )
        finally:
            await connection.close()

    async def fail(
        self,
        message: JobMessage,
        *,
        category: ErrorCategory,
        error_code: str,
        error_message: str,
    ) -> JobState:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT attempt_count, max_attempts, output_json
                    FROM tasks
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                    FOR UPDATE
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                )
                if row is None:
                    raise RuntimeError("JOB_NOT_FOUND")
                attempt_count = int(row["attempt_count"])
                max_attempts = int(row["max_attempts"])
                retry = category == ErrorCategory.TRANSIENT and attempt_count < max_attempts
                state = JobState.RETRYING if retry else JobState.FAILED
                output = dict(row["output_json"] or {})
                output["last_error"] = {
                    "category": category.value,
                    "code": error_code,
                    "message": error_message[:1000],
                    "recorded_at": datetime.now(UTC).isoformat(),
                }
                await connection.execute(
                    """
                    UPDATE tasks
                    SET status = $4, output_json = $5::jsonb,
                        finished_at = CASE WHEN $4 = 'failed' THEN now() ELSE NULL END,
                        wait_reason = NULL, external_ref = NULL, retry_not_before = NULL,
                        updated_at = now(), state_version = state_version + 1,
                        version = version + 1
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    state.value,
                    _json(output),
                )
                return state
        finally:
            await connection.close()


def _json(value: dict[str, Any]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("JOB_OUTPUT_JSON_INVALID") from exc


def _datetime_unix_ns(value: datetime) -> int:
    if value.tzinfo is None:
        raise RuntimeError("PERFORMANCE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    utc = value.astimezone(UTC)
    seconds = int(utc.timestamp())
    return seconds * 1_000_000_000 + utc.microsecond * 1_000


async def execute_job(
    *,
    store: TaskJobStore,
    message: JobMessage,
    handler: JobHandler,
) -> JobOutcome:
    if await store.cancellation_requested(message):
        return JobOutcome(JobState.CANCELLED, 0, {"cancelled": True})
    attempt_count = await store.claim(message)
    if attempt_count is None:
        return JobOutcome(JobState.CANCELLED, 0, {"skipped": "not_claimable"})
    try:
        result = await handler(message)
        if await store.cancellation_requested(message):
            raise JobCancelled("CANCELLED")
        if isinstance(result, ExternalWait):
            await store.wait_external(message, result)
            return JobOutcome(JobState.WAITING_EXTERNAL, attempt_count, dict(result.output))
        await store.succeed(message, result)
        return JobOutcome(JobState.SUCCEEDED, attempt_count, result)
    except JobCancelled:
        await store.cancel(message)
        return JobOutcome(JobState.CANCELLED, attempt_count, {"cancelled": True})
    except Exception as exc:
        category = classify_error(
            code=getattr(exc, "code", type(exc).__name__),
            retryable=getattr(exc, "retryable", None),
        )
        state = await store.fail(
            message,
            category=category,
            error_code=str(getattr(exc, "code", type(exc).__name__)),
            error_message=str(exc),
        )
        return JobOutcome(state, attempt_count, {"error": str(exc)})
