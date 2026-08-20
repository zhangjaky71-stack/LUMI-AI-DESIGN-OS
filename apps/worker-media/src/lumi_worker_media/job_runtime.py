from __future__ import annotations

import json
from dataclasses import dataclass
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


class JobHandler(Protocol):
    async def __call__(self, message: JobMessage) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class JobOutcome:
    state: JobState
    attempt_count: int
    output: dict[str, Any]


class TaskJobStore:
    """Uses the existing `tasks` table as the business source of truth for generic jobs."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def claim(self, message: JobMessage) -> int | None:
        telemetry = PerformanceTelemetryContext.from_environ()
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE tasks
                SET status = 'running',
                    attempt_count = attempt_count + 1,
                    started_at = COALESCE(started_at, now()),
                    updated_at = now(),
                    version = version + 1
                WHERE id = $1
                  AND organization_id = $2
                  AND project_id = $3
                  AND status IN ('pending', 'retrying')
                  AND attempt_count < max_attempts
                RETURNING attempt_count, created_at, started_at
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
            if row is None:
                return None
            attempt_count = int(row["attempt_count"])
            if telemetry is not None and attempt_count == 1:
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
            status = await connection.fetchval(
                """
                SELECT status FROM tasks
                WHERE id = $1 AND organization_id = $2 AND project_id = $3
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
            )
            return status == "cancelled"
        finally:
            await connection.close()

    async def cancel(self, message: JobMessage) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                UPDATE tasks
                SET status = 'cancelled', finished_at = now(),
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND organization_id = $2 AND project_id = $3
                  AND status IN ('pending', 'running', 'retrying')
                """,
                message.job_id,
                message.organization_id,
                message.project_id,
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
                        finished_at = now(), updated_at = now(), version = version + 1
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                      AND status = 'running'
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
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
                        updated_at = now(), version = version + 1
                    WHERE id = $1 AND organization_id = $2 AND project_id = $3
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    state.value,
                    json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                )
                return state
        finally:
            await connection.close()


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
        output = await handler(message)
        if await store.cancellation_requested(message):
            raise JobCancelled("CANCELLED")
        await store.succeed(message, output)
        return JobOutcome(JobState.SUCCEEDED, attempt_count, output)
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
