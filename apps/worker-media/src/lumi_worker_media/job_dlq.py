from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from kombu import Connection, Producer

from .event_runtime import DeadLetterRecord, DeadLetterStore
from .job_runtime import MemoryJobStore
from .queue_contracts import ErrorCategory, JobKind, JobMessage, queue_for, routing_key_for
from .runtime_ids import new_uuid7
from .topology import DEAD_LETTER_EXCHANGE


class JobSubmitter(Protocol):
    def submit(self, kind: JobKind, message: JobMessage) -> None: ...


class JobReplayState(Protocol):
    async def prepare_replay(self, message: JobMessage, *, now: datetime) -> None: ...


@dataclass(frozen=True, slots=True)
class MemoryJobReplayState(JobReplayState):
    store: MemoryJobStore

    async def prepare_replay(self, message: JobMessage, *, now: datetime) -> None:
        self.store.requeue_failed(message, now=now)


@dataclass(frozen=True, slots=True)
class PostgresJobReplayState(JobReplayState):
    dsn: str

    async def prepare_replay(self, message: JobMessage, *, now: datetime) -> None:
        try:
            asyncpg = importlib.import_module("asyncpg")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "asyncpg is required for PostgreSQL Job replay state"
            ) from exc
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                await connection.execute(
                    "SELECT set_config('app.current_organization_id', $1, true)",
                    str(message.organization_id),
                )
                row = await connection.fetchval(
                    """
                    UPDATE runtime_jobs
                    SET status='pending', attempt_count=0,
                        started_at=NULL, finished_at=NULL, next_retry_at=NULL,
                        cancellation_requested_at=NULL, output_json='{}'::jsonb,
                        error_category=NULL, error_code=NULL, error_message=NULL,
                        updated_at=$4, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND project_id=$3
                      AND status IN ('failed','retrying','pending')
                    RETURNING id
                    """,
                    message.job_id,
                    message.organization_id,
                    message.project_id,
                    now,
                )
                if row is None:
                    raise ValueError("JOB_NOT_REPLAYABLE")
        finally:
            await connection.close()


class JobDeadLetterPublisher(Protocol):
    def publish(self, record: DeadLetterRecord) -> None: ...


class KombuJobDeadLetterPublisher(JobDeadLetterPublisher):
    def __init__(self, broker_url: str) -> None:
        self.broker_url = broker_url

    def publish(self, record: DeadLetterRecord) -> None:
        payload = {
            "dead_letter_id": str(record.id),
            "organization_id": str(record.organization_id),
            "message_id": str(record.message_id),
            "message_kind": record.message_kind,
            "error_category": record.error_category.value,
            "error_code": record.error_code,
            "attempts": record.attempts,
            "payload": record.payload,
        }
        with Connection(
            self.broker_url,
            transport_options={"confirm_publish": True},
        ) as connection:
            connection.ensure_connection(max_retries=3)
            with connection.channel() as channel:
                confirm_select = getattr(channel, "confirm_select", None)
                if callable(confirm_select):
                    confirm_select()
                Producer(channel, serializer="json").publish(
                    payload,
                    exchange=DEAD_LETTER_EXCHANGE,
                    routing_key=f"{record.source_queue}.dead",
                    serializer="json",
                    content_type="application/json",
                    delivery_mode=2,
                    retry=True,
                    retry_policy={
                        "max_retries": 3,
                        "interval_start": 0,
                        "interval_step": 1,
                        "interval_max": 3,
                    },
                    mandatory=True,
                    declare=[DEAD_LETTER_EXCHANGE],
                )


class MemoryJobDeadLetterPublisher(JobDeadLetterPublisher):
    def __init__(self) -> None:
        self.records: list[DeadLetterRecord] = []

    def publish(self, record: DeadLetterRecord) -> None:
        self.records.append(record)


@dataclass(frozen=True, slots=True)
class JobDeadLetterService:
    store: DeadLetterStore
    publisher: JobDeadLetterPublisher

    async def record_failure(
        self,
        *,
        kind: JobKind,
        message: JobMessage,
        category: ErrorCategory,
        error_code: str,
        error_message: str,
        attempts: int,
        now: datetime | None = None,
    ) -> DeadLetterRecord:
        failed_at = now or datetime.now(UTC)
        record = DeadLetterRecord(
            id=new_uuid7(),
            organization_id=message.organization_id,
            message_id=message.job_id,
            message_kind="job",
            source_queue=queue_for(kind),
            exchange_name="lumi.jobs",
            routing_key=routing_key_for(kind),
            error_category=category,
            error_code=error_code[:128],
            error_message=error_message[:2000],
            attempts=max(1, attempts),
            traceparent=message.traceparent,
            payload={
                "job_kind": kind.value,
                "message": message.as_dict(),
            },
            first_failed_at=failed_at,
            last_failed_at=failed_at,
        )
        await self.store.record(record)
        self.publisher.publish(record)
        return record


@dataclass(frozen=True, slots=True)
class JobDeadLetterReplayService:
    store: DeadLetterStore
    state: JobReplayState
    submitter: JobSubmitter

    async def replay(
        self,
        organization_id: UUID,
        record_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DeadLetterRecord:
        record = await self.store.get(organization_id, record_id)
        if record is None:
            raise ValueError("DEAD_LETTER_NOT_FOUND")
        if record.message_kind != "job":
            raise ValueError("DEAD_LETTER_NOT_JOB")
        if record.replayed_at is not None:
            raise ValueError("DEAD_LETTER_ALREADY_REPLAYED")
        kind_raw = record.payload.get("job_kind")
        message_raw = record.payload.get("message")
        if not isinstance(kind_raw, str) or not isinstance(message_raw, dict):
            raise ValueError("JOB_DEAD_LETTER_PAYLOAD_INVALID")
        kind = JobKind(kind_raw)
        message = JobMessage.from_mapping(dict(message_raw))
        if message.organization_id != organization_id or message.job_id != record.message_id:
            raise ValueError("JOB_DEAD_LETTER_IDENTITY_MISMATCH")
        replayed_at = now or datetime.now(UTC)
        await self.state.prepare_replay(message, now=replayed_at)
        self.submitter.submit(kind, message)
        await self.store.mark_replayed(organization_id, record_id, now=replayed_at)
        updated = await self.store.get(organization_id, record_id)
        if updated is None:
            raise RuntimeError("DEAD_LETTER_REPLAY_STATE_LOST")
        return updated
