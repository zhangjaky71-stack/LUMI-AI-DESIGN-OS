from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from .event_runtime import (
    CanonicalEvent,
    DeadLetterRecord,
    DeadLetterStore,
    DispatchResult,
    DomainPublisher,
    EventHandler,
    InboxStore,
    OutboxItem,
)
from .job_runtime import JobRecord, JobStore
from .queue_contracts import ErrorCategory, JobKind, JobMessage, JobState


def _asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "asyncpg is required for PostgreSQL queue runtime; install the runtime DB extra"
        ) from exc


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("DATABASE_JSON_OBJECT_REQUIRED")


async def _set_tenant(connection: Any, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)",
        str(organization_id),
    )


class PostgresJobStore(JobStore):
    """Synchronous Celery-facing adapter; each method owns a short asyncpg transaction."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def _run(self, awaitable: Any) -> Any:
        return asyncio.run(awaitable)

    def create(self, record: JobRecord) -> None:
        self._run(self._create(record))

    async def _create(self, record: JobRecord) -> None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, record.message.organization_id)
                await connection.execute(
                    """
                    INSERT INTO runtime_jobs(
                      id, organization_id, project_id, job_kind, operation_id, resource_id,
                      status, attempt_count, max_attempts, traceparent, input_json,
                      created_at, updated_at, version
                    ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$12,1)
                    """,
                    record.message.job_id,
                    record.message.organization_id,
                    record.message.project_id,
                    record.kind.value,
                    record.message.operation_id,
                    record.message.resource_id,
                    record.state.value,
                    record.attempt_count,
                    record.max_attempts,
                    record.message.traceparent,
                    json.dumps(record.message.as_dict(), separators=(",", ":")),
                    record.created_at or datetime.now(UTC),
                )
        finally:
            await connection.close()

    def get(self, message: JobMessage) -> JobRecord | None:
        return self._run(self._get(message))

    async def _get(self, message: JobMessage) -> JobRecord | None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    SELECT * FROM runtime_jobs
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                )
                return _job_record(row) if row else None
        finally:
            await connection.close()

    def claim(self, message: JobMessage, *, now: datetime) -> JobRecord | None:
        return self._run(self._claim(message, now))

    async def _claim(self, message: JobMessage, now: datetime) -> JobRecord | None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE runtime_jobs
                    SET status='running', attempt_count=attempt_count+1,
                        started_at=COALESCE(started_at,$4), next_retry_at=NULL,
                        updated_at=$4, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                      AND status IN ('pending','retrying')
                      AND cancellation_requested_at IS NULL
                      AND attempt_count < max_attempts
                      AND (next_retry_at IS NULL OR next_retry_at <= $4)
                    RETURNING *
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    now,
                )
                return _job_record(row) if row else None
        finally:
            await connection.close()

    def request_cancel(self, message: JobMessage, *, now: datetime) -> JobRecord | None:
        return self._run(self._request_cancel(message, now))

    async def _request_cancel(self, message: JobMessage, now: datetime) -> JobRecord | None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE runtime_jobs
                    SET cancellation_requested_at=COALESCE(cancellation_requested_at,$4),
                        updated_at=$4, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                      AND status IN ('pending','running','retrying')
                    RETURNING *
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    now,
                )
                if row:
                    return _job_record(row)
                row = await connection.fetchrow(
                    "SELECT * FROM runtime_jobs WHERE id=$1 AND organization_id=$2 AND project_id=$3",
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                )
                return _job_record(row) if row else None
        finally:
            await connection.close()

    def cancellation_requested(self, message: JobMessage) -> bool:
        return bool(self._run(self._cancellation_requested(message)))

    async def _cancellation_requested(self, message: JobMessage) -> bool:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                value = await connection.fetchval(
                    """
                    SELECT cancellation_requested_at IS NOT NULL
                    FROM runtime_jobs
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                )
                return bool(value)
        finally:
            await connection.close()

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
        return self._run(
            self._transition(
                message,
                status=JobState.RETRYING,
                now=now,
                category=category,
                code=code,
                error_message=error_message,
                next_retry_at=next_retry_at,
            )
        )

    def succeed(
        self,
        message: JobMessage,
        *,
        now: datetime,
        output: dict[str, Any],
    ) -> JobRecord:
        return self._run(self._succeed(message, now, output))

    async def _succeed(
        self,
        message: JobMessage,
        now: datetime,
        output: dict[str, Any],
    ) -> JobRecord:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE runtime_jobs
                    SET status='succeeded', output_json=$4::jsonb, finished_at=$5,
                        updated_at=$5, error_category=NULL, error_code=NULL,
                        error_message=NULL, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3 AND status='running'
                    RETURNING *
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    json.dumps(output, separators=(",", ":")),
                    now,
                )
                if not row:
                    raise ValueError("JOB_NOT_RUNNING")
                return _job_record(row)
        finally:
            await connection.close()

    def fail(
        self,
        message: JobMessage,
        *,
        now: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
    ) -> JobRecord:
        return self._run(
            self._transition(
                message,
                status=JobState.FAILED,
                now=now,
                category=category,
                code=code,
                error_message=error_message,
            )
        )

    def cancel(self, message: JobMessage, *, now: datetime) -> JobRecord:
        return self._run(self._cancel(message, now))

    async def _cancel(self, message: JobMessage, now: datetime) -> JobRecord:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE runtime_jobs
                    SET status='cancelled', finished_at=$4, updated_at=$4, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                      AND status IN ('pending','running','retrying')
                    RETURNING *
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    now,
                )
                if not row:
                    row = await connection.fetchrow(
                        "SELECT * FROM runtime_jobs WHERE id=$1 AND organization_id=$2 AND project_id=$3",
                        message.job_id,
                        message.organization_id,
                        message.project_id,
                    )
                if not row:
                    raise ValueError("JOB_NOT_FOUND")
                return _job_record(row)
        finally:
            await connection.close()

    async def _transition(
        self,
        message: JobMessage,
        *,
        status: JobState,
        now: datetime,
        category: ErrorCategory,
        code: str,
        error_message: str,
        next_retry_at: datetime | None = None,
    ) -> JobRecord:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, message.organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE runtime_jobs
                    SET status=$4, next_retry_at=$5,
                        finished_at=CASE WHEN $4='failed' THEN $6 ELSE NULL END,
                        error_category=$7, error_code=$8, error_message=$9,
                        updated_at=$6, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3 AND status='running'
                    RETURNING *
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    status.value,
                    next_retry_at,
                    now,
                    category.value,
                    code[:128],
                    error_message[:2000],
                )
                if not row:
                    raise ValueError("JOB_NOT_RUNNING")
                return _job_record(row)
        finally:
            await connection.close()


class PostgresInboxStore(InboxStore):
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def apply_once(
        self,
        event: CanonicalEvent,
        *,
        consumer: str,
        handler: EventHandler,
    ) -> bool:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, event.organization_id)
                inserted = await connection.fetchval(
                    """
                    INSERT INTO inbox_events(event_id,consumer,organization_id,processed_at,created_at)
                    VALUES($1,$2,$3,now(),now())
                    ON CONFLICT (event_id,consumer) DO NOTHING
                    RETURNING event_id
                    """,
                    event.event_id,
                    consumer,
                    event.organization_id,
                )
                if inserted is None:
                    return False
                result = handler(event, connection)
                if inspect.isawaitable(result):
                    await result
                return True
        finally:
            await connection.close()


class PostgresDeadLetterStore(DeadLetterStore):
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def record(self, record: DeadLetterRecord) -> None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, record.organization_id)
                await connection.execute(
                    """
                    INSERT INTO dead_letter_records(
                      id,organization_id,message_id,message_kind,source_queue,consumer,
                      exchange_name,routing_key,error_category,error_code,error_message,
                      attempts,traceparent,payload_json,first_failed_at,last_failed_at,
                      status,created_at,updated_at,version
                    ) VALUES(
                      $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,
                      $15,$16,'open',$16,$16,1
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    record.id,
                    record.organization_id,
                    record.message_id,
                    record.message_kind,
                    record.source_queue,
                    record.consumer,
                    record.exchange_name,
                    record.routing_key,
                    record.error_category.value,
                    record.error_code[:128],
                    record.error_message[:2000],
                    record.attempts,
                    record.traceparent,
                    json.dumps(record.payload, separators=(",", ":")),
                    record.first_failed_at or record.last_failed_at or datetime.now(UTC),
                    record.last_failed_at or datetime.now(UTC),
                )
        finally:
            await connection.close()

    async def get(self, organization_id: UUID, record_id: UUID) -> DeadLetterRecord | None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    "SELECT * FROM dead_letter_records WHERE id=$1 AND organization_id=$2",
                    record_id,
                    organization_id,
                )
                return _dead_letter_record(row) if row else None
        finally:
            await connection.close()

    async def mark_replayed(
        self,
        organization_id: UUID,
        record_id: UUID,
        *,
        now: datetime,
    ) -> None:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                result = await connection.execute(
                    """
                    UPDATE dead_letter_records
                    SET status='replayed', replayed_at=$3, updated_at=$3, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND status='open'
                    """,
                    record_id,
                    organization_id,
                    now,
                )
                if not result.endswith(" 1"):
                    raise ValueError("DEAD_LETTER_NOT_OPEN")
        finally:
            await connection.close()


class PostgresOutboxDispatcher:
    """Tenant-sharded dispatcher: never bypasses NODE-16 RLS to scan outbox rows."""

    def __init__(self, dsn: str, publisher: DomainPublisher) -> None:
        self.dsn = dsn
        self.publisher = publisher

    def dispatch_organization(
        self,
        organization_id: UUID,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> DispatchResult:
        return asyncio.run(
            self._dispatch_organization(
                organization_id,
                limit=limit,
                now=now or datetime.now(UTC),
            )
        )

    async def _dispatch_organization(
        self,
        organization_id: UUID,
        *,
        limit: int,
        now: datetime,
    ) -> DispatchResult:
        if not 1 <= limit <= 1000:
            raise ValueError("OUTBOX_BATCH_LIMIT_INVALID")
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        claimed = published = failed = 0
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                rows = await connection.fetch(
                    """
                    SELECT id,organization_id,event_type,aggregate_type,aggregate_id,
                           payload_json,occurred_at,created_at,publish_attempts
                    FROM outbox_events
                    WHERE published_at IS NULL
                      AND (next_publish_at IS NULL OR next_publish_at <= $2)
                    ORDER BY created_at,id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                    """,
                    limit,
                    now,
                )
                claimed = len(rows)
                for row in rows:
                    attempts = int(row["publish_attempts"]) + 1
                    item = OutboxItem(
                        event_id=row["id"],
                        organization_id=row["organization_id"],
                        event_type=row["event_type"],
                        aggregate_type=row["aggregate_type"],
                        aggregate_id=row["aggregate_id"],
                        envelope_json=_json_object(row["payload_json"]),
                        occurred_at=row["occurred_at"],
                        created_at=row["created_at"],
                        publish_attempts=attempts,
                    )
                    await connection.execute(
                        """
                        UPDATE outbox_events
                        SET publish_attempts=$2,last_publish_attempt_at=$3
                        WHERE id=$1
                        """,
                        item.event_id,
                        attempts,
                        now,
                    )
                    try:
                        event = item.canonical_event()
                        await asyncio.to_thread(self.publisher.publish, event)
                    except Exception as exc:
                        failed += 1
                        delay = min(300, 2 ** max(0, min(attempts, 8) - 1))
                        await connection.execute(
                            """
                            UPDATE outbox_events
                            SET last_publish_error=$2,next_publish_at=$3
                            WHERE id=$1
                            """,
                            item.event_id,
                            f"{type(exc).__name__}:{exc}"[:2000],
                            now + timedelta(seconds=delay),
                        )
                    else:
                        published += 1
                        await connection.execute(
                            """
                            UPDATE outbox_events
                            SET published_at=$2,last_publish_error=NULL,next_publish_at=NULL
                            WHERE id=$1
                            """,
                            item.event_id,
                            now,
                        )
            return DispatchResult(claimed=claimed, published=published, failed=failed)
        finally:
            await connection.close()

    def dispatch_all(
        self,
        *,
        limit_per_organization: int = 100,
        now: datetime | None = None,
    ) -> dict[UUID, DispatchResult]:
        return asyncio.run(
            self._dispatch_all(
                limit_per_organization=limit_per_organization,
                now=now or datetime.now(UTC),
            )
        )

    async def _dispatch_all(
        self,
        *,
        limit_per_organization: int,
        now: datetime,
    ) -> dict[UUID, DispatchResult]:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            rows = await connection.fetch("SELECT id FROM organizations ORDER BY id")
        finally:
            await connection.close()
        results: dict[UUID, DispatchResult] = {}
        for row in rows:
            organization_id = row["id"]
            results[organization_id] = await self._dispatch_organization(
                organization_id,
                limit=limit_per_organization,
                now=now,
            )
        return results


def _job_record(row: Any) -> JobRecord:
    message = JobMessage(
        job_id=row["id"],
        organization_id=row["organization_id"],
        project_id=row["project_id"],
        operation_id=row["operation_id"],
        resource_id=row["resource_id"],
        traceparent=row["traceparent"],
    )
    output = _json_object(row["output_json"]) if row["output_json"] else None
    category = ErrorCategory(row["error_category"]) if row["error_category"] else None
    return JobRecord(
        message=message,
        kind=JobKind(row["job_kind"]),
        state=JobState(row["status"]),
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        next_retry_at=row["next_retry_at"],
        cancellation_requested_at=row["cancellation_requested_at"],
        output=output,
        error_category=category,
        error_code=row["error_code"],
        error_message=row["error_message"],
    )


def _dead_letter_record(row: Any) -> DeadLetterRecord:
    return DeadLetterRecord(
        id=row["id"],
        organization_id=row["organization_id"],
        message_id=row["message_id"],
        message_kind=row["message_kind"],
        source_queue=row["source_queue"],
        consumer=row["consumer"],
        exchange_name=row["exchange_name"],
        routing_key=row["routing_key"],
        error_category=ErrorCategory(row["error_category"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
        attempts=int(row["attempts"]),
        traceparent=row["traceparent"],
        payload=_json_object(row["payload_json"]),
        first_failed_at=row["first_failed_at"],
        last_failed_at=row["last_failed_at"],
        replayed_at=row["replayed_at"],
    )
