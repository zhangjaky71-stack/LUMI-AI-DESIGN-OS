from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import asyncpg
from lumi_domain.job_dispatch import (
    IMAGE_TRANSFORM_QUEUE,
    IMAGE_TRANSFORM_ROUTING_KEY,
    IMAGE_TRANSFORM_TASK_NAME,
    JOB_DISPATCH_EVENT_NAME,
    JOB_DISPATCH_SCHEMA_VERSION,
    VIDEO_RENDER_QUEUE,
    VIDEO_RENDER_ROUTING_KEY,
    VIDEO_RENDER_TASK_NAME,
    JobDispatch,
)

from .topology import JOBS_EXCHANGE


class JobPublisher(Protocol):
    def publish(self, dispatch: JobDispatch) -> None: ...


_ROUTE_BY_TASK: dict[str, tuple[str, str]] = {
    IMAGE_TRANSFORM_TASK_NAME: (IMAGE_TRANSFORM_QUEUE, IMAGE_TRANSFORM_ROUTING_KEY),
    VIDEO_RENDER_TASK_NAME: (VIDEO_RENDER_QUEUE, VIDEO_RENDER_ROUTING_KEY),
}


class CeleryJobPublisher:
    """Publish a validated canonical media dispatch through the configured Celery app."""

    def publish(self, dispatch: JobDispatch) -> None:
        routing_key = _validate_media_dispatch(dispatch)
        from .app import celery_app

        celery_app.send_task(
            dispatch.task_name,
            args=[dispatch.message.as_dict()],
            kwargs={},
            queue=dispatch.queue,
            exchange=JOBS_EXCHANGE.name,
            routing_key=routing_key,
            serializer="json",
            retry=True,
            retry_policy={
                "max_retries": 3,
                "interval_start": 0,
                "interval_step": 1,
                "interval_max": 3,
            },
        )


@dataclass(frozen=True, slots=True)
class MediaJobOutboxRecord:
    event_id: UUID
    organization_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    schema_version: int
    payload: dict[str, object]

    def dispatch(self) -> JobDispatch:
        if self.aggregate_type != "task":
            raise ValueError("MEDIA_JOB_OUTBOX_AGGREGATE_TYPE_MISMATCH")
        if self.schema_version != JOB_DISPATCH_SCHEMA_VERSION:
            raise ValueError("MEDIA_JOB_OUTBOX_SCHEMA_UNSUPPORTED")
        dispatch = JobDispatch.from_outbox_payload(self.payload)
        _validate_media_dispatch(dispatch)
        if dispatch.message.job_id != self.aggregate_id:
            raise ValueError("MEDIA_JOB_OUTBOX_AGGREGATE_ID_MISMATCH")
        if dispatch.message.organization_id != self.organization_id:
            raise ValueError("MEDIA_JOB_OUTBOX_ORGANIZATION_MISMATCH")
        return dispatch


@dataclass(frozen=True, slots=True)
class MediaJobOutboxHealth:
    """Bounded queue-head health used by the always-on dispatcher telemetry loop."""

    oldest_unpublished_age_seconds: int
    oldest_publish_attempts: int

    def __post_init__(self) -> None:
        if self.oldest_unpublished_age_seconds < 0:
            raise ValueError("MEDIA_JOB_OUTBOX_HEALTH_AGE_INVALID")
        if self.oldest_publish_attempts < 0:
            raise ValueError("MEDIA_JOB_OUTBOX_HEALTH_ATTEMPTS_INVALID")


class MediaJobOutboxDispatcher:
    """Dispatch only canonical job outbox rows; domain events are handled elsewhere.

    The row lock is held across the broker publish so concurrent dispatchers cannot
    publish the same pending row simultaneously. Publish attempts are committed even
    when validation or broker publication fails; published_at is set only after the
    broker call returns successfully. A crash after broker acceptance and before the
    database commit can still redeliver, so Worker execution remains idempotent.
    """

    def __init__(self, dsn: str, publisher: JobPublisher) -> None:
        self.dsn = dsn
        self.publisher = publisher

    async def dispatch_batch(self, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("MEDIA_JOB_OUTBOX_BATCH_LIMIT_INVALID")
        connection = await asyncpg.connect(self.dsn)
        published = 0
        failure: Exception | None = None
        try:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT id, organization_id, aggregate_type, aggregate_id,
                           schema_version, payload_json
                    FROM outbox_events
                    WHERE published_at IS NULL
                      AND event_name = $2
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                    """,
                    limit,
                    JOB_DISPATCH_EVENT_NAME,
                )
                for row in rows:
                    record = MediaJobOutboxRecord(
                        event_id=row["id"],
                        organization_id=row["organization_id"],
                        aggregate_type=str(row["aggregate_type"]),
                        aggregate_id=row["aggregate_id"],
                        schema_version=int(row["schema_version"]),
                        payload=dict(row["payload_json"]),
                    )
                    await connection.execute(
                        """
                        UPDATE outbox_events
                        SET publish_attempts = publish_attempts + 1
                        WHERE id = $1 AND published_at IS NULL
                        """,
                        record.event_id,
                    )
                    try:
                        dispatch = record.dispatch()
                        await asyncio.to_thread(self.publisher.publish, dispatch)
                    except Exception as exc:
                        failure = exc
                        break
                    await connection.execute(
                        """
                        UPDATE outbox_events
                        SET published_at = now()
                        WHERE id = $1 AND published_at IS NULL
                        """,
                        record.event_id,
                    )
                    published += 1
            if failure is not None:
                raise failure
            return published
        finally:
            await connection.close()

    async def health_snapshot(self) -> MediaJobOutboxHealth:
        """Read only the oldest pending job row; never count or scan the full outbox."""

        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                SELECT
                    GREATEST(
                        FLOOR(EXTRACT(EPOCH FROM (now() - created_at))),
                        0
                    )::bigint AS oldest_unpublished_age_seconds,
                    publish_attempts AS oldest_publish_attempts
                FROM outbox_events
                WHERE published_at IS NULL
                  AND event_name = $1
                ORDER BY created_at, id
                LIMIT 1
                """,
                JOB_DISPATCH_EVENT_NAME,
            )
            if row is None:
                return MediaJobOutboxHealth(
                    oldest_unpublished_age_seconds=0,
                    oldest_publish_attempts=0,
                )
            return MediaJobOutboxHealth(
                oldest_unpublished_age_seconds=int(
                    row["oldest_unpublished_age_seconds"]
                ),
                oldest_publish_attempts=int(row["oldest_publish_attempts"]),
            )
        finally:
            await connection.close()


def _validate_media_dispatch(dispatch: JobDispatch) -> str:
    expected = _ROUTE_BY_TASK.get(dispatch.task_name)
    if expected is None:
        raise ValueError("MEDIA_JOB_DISPATCH_TASK_NAME_MISMATCH")
    expected_queue, routing_key = expected
    if dispatch.queue != expected_queue:
        raise ValueError("MEDIA_JOB_DISPATCH_QUEUE_MISMATCH")
    if dispatch.message.operation_id is None:
        raise ValueError("MEDIA_JOB_DISPATCH_OPERATION_REQUIRED")
    dispatch.as_outbox_payload()
    return routing_key
