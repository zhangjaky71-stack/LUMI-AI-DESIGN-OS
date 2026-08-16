from __future__ import annotations

import asyncio
import importlib
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from .job_runtime import JobRecord, MemoryJobStore
from .queue_contracts import ErrorCategory, JobKind, JobMessage, JobState


class JobPublisher(Protocol):
    def submit(self, kind: JobKind, message: JobMessage) -> None: ...


def recover_stale_memory_jobs(
    store: MemoryJobStore,
    *,
    now: datetime,
    stale_after: timedelta,
) -> tuple[JobRecord, ...]:
    if stale_after.total_seconds() <= 0:
        raise ValueError("stale_after must be positive")
    cutoff = now - stale_after
    recovered: list[JobRecord] = []
    for job_id, record in tuple(store.records.items()):
        heartbeat = record.updated_at or record.started_at or record.created_at
        if (
            record.state is JobState.RUNNING
            and heartbeat is not None
            and heartbeat <= cutoff
        ):
            updated = replace(
                record,
                state=JobState.RETRYING,
                updated_at=now,
                next_retry_at=now,
                error_category=ErrorCategory.TRANSIENT,
                error_code="WORKER_STALE_RECOVERY",
                error_message="worker lease expired before terminal job state",
            )
            store.records[job_id] = updated
            recovered.append(updated)
    return tuple(recovered)


class PostgresStaleJobRecovery:
    """Tenant-sharded crash recovery while NODE-19 keeps Celery acks_late disabled."""

    def __init__(self, dsn: str, publisher: JobPublisher) -> None:
        self.dsn = dsn
        self.publisher = publisher

    def recover_organization(
        self,
        organization_id: UUID,
        *,
        now: datetime,
        stale_after: timedelta = timedelta(minutes=5),
        limit: int = 100,
    ) -> int:
        return asyncio.run(
            self._recover_organization(
                organization_id,
                now=now,
                stale_after=stale_after,
                limit=limit,
            )
        )

    async def _recover_organization(
        self,
        organization_id: UUID,
        *,
        now: datetime,
        stale_after: timedelta,
        limit: int,
    ) -> int:
        if stale_after.total_seconds() <= 0:
            raise ValueError("stale_after must be positive")
        if not 1 <= limit <= 1000:
            raise ValueError("RECOVERY_BATCH_LIMIT_INVALID")
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        recovered = 0
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.current_organization_id', $1, true)",
                    str(organization_id),
                )
                rows = await connection.fetch(
                    """
                    SELECT id, organization_id, project_id, job_kind, operation_id,
                           resource_id, traceparent
                    FROM runtime_jobs
                    WHERE organization_id=$1 AND status='running'
                      AND updated_at <= $2
                    ORDER BY updated_at,id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $3
                    """,
                    organization_id,
                    now - stale_after,
                    limit,
                )
                for row in rows:
                    message = JobMessage(
                        job_id=row["id"],
                        organization_id=row["organization_id"],
                        project_id=row["project_id"],
                        operation_id=row["operation_id"],
                        resource_id=row["resource_id"],
                        traceparent=row["traceparent"],
                    )
                    kind = JobKind(row["job_kind"])
                    # Publish before committing the retry transition. A process crash after
                    # broker acceptance rolls the transaction back to RUNNING, so a later
                    # sweep will publish again. Duplicate delivery is safe because claim()
                    # only moves one PENDING/RETRYING row into RUNNING.
                    await asyncio.to_thread(self.publisher.submit, kind, message)
                    await connection.execute(
                        """
                        UPDATE runtime_jobs
                        SET status='retrying', next_retry_at=$2, updated_at=$2,
                            error_category='transient',
                            error_code='WORKER_STALE_RECOVERY',
                            error_message='worker lease expired before terminal job state',
                            version=version+1
                        WHERE id=$1 AND organization_id=$3 AND status='running'
                        """,
                        message.job_id,
                        now,
                        organization_id,
                    )
                    recovered += 1
            return recovered
        finally:
            await connection.close()


def _asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "asyncpg is required for PostgreSQL queue recovery; install the runtime DB extra"
        ) from exc
