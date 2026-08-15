from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

import asyncpg
from kombu import Connection, Producer
from lumi_domain import new_uuid7

from .observability import bind_event_correlation, reset_event_correlation
from .queue_contracts import ErrorCategory, classify_error
from .topology import DOMAIN_EXCHANGE, domain_queue

EventHandler = Callable[[asyncpg.Connection, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    event_id: UUID
    organization_id: UUID
    event_name: str
    aggregate_type: str
    aggregate_id: UUID
    schema_version: int
    payload: dict[str, Any]
    created_at: datetime

    def envelope(self) -> dict[str, Any]:
        correlation_id = self.payload.get("correlation_id") or str(self.event_id)
        return {
            "specversion": "1.0",
            "id": str(self.event_id),
            "source": f"lumi://{self.aggregate_type}",
            "type": f"lumi.{self.event_name}",
            "subject": f"{self.aggregate_type}/{self.aggregate_id}",
            "time": self.created_at.astimezone(UTC).isoformat(),
            "datacontenttype": "application/json",
            "dataschema": f"urn:lumi:event:{self.event_name}:{self.schema_version}",
            "organizationid": str(self.organization_id),
            "correlationid": str(correlation_id),
            "causationid": self.payload.get("causation_id"),
            "traceid": self.payload.get("trace_id"),
            "partitionkey": str(self.aggregate_id),
            "schemaversion": self.schema_version,
            "data": _normalized_event_data(self),
        }


class DomainPublisher(Protocol):
    def publish(self, record: OutboxRecord) -> None: ...


class KombuDomainPublisher:
    def __init__(self, broker_url: str) -> None:
        self.broker_url = broker_url

    def publish(self, record: OutboxRecord) -> None:
        with Connection(self.broker_url) as connection:
            connection.ensure_connection(max_retries=3)
            with connection.channel() as channel:
                confirm_select = getattr(channel, "confirm_select", None)
                if callable(confirm_select):
                    confirm_select()
                producer = Producer(channel, serializer="json")
                producer.publish(
                    record.envelope(),
                    exchange=DOMAIN_EXCHANGE,
                    routing_key=record.event_name,
                    serializer="json",
                    content_type="application/json",
                    retry=True,
                    retry_policy={"max_retries": 3, "interval_start": 0, "interval_step": 1},
                    declare=[DOMAIN_EXCHANGE],
                    mandatory=True,
                )


class OutboxDispatcher:
    def __init__(self, dsn: str, publisher: DomainPublisher) -> None:
        self.dsn = dsn
        self.publisher = publisher

    async def dispatch_batch(self, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise ValueError("OUTBOX_BATCH_LIMIT_INVALID")
        connection = await asyncpg.connect(self.dsn)
        published = 0
        try:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT id, organization_id, event_name, aggregate_type, aggregate_id,
                           schema_version, payload_json, created_at
                    FROM outbox_events
                    WHERE published_at IS NULL
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1
                    """,
                    limit,
                )
                for row in rows:
                    record = OutboxRecord(
                        event_id=row["id"],
                        organization_id=row["organization_id"],
                        event_name=row["event_name"],
                        aggregate_type=row["aggregate_type"],
                        aggregate_id=row["aggregate_id"],
                        schema_version=int(row["schema_version"]),
                        payload=dict(row["payload_json"]),
                        created_at=row["created_at"],
                    )
                    await connection.execute(
                        (
                            "UPDATE outbox_events SET publish_attempts = "
                            "publish_attempts + 1 WHERE id = $1"
                        ),
                        record.event_id,
                    )
                    await asyncio.to_thread(self.publisher.publish, record)
                    await connection.execute(
                        "UPDATE outbox_events SET published_at = now() WHERE id = $1",
                        record.event_id,
                    )
                    published += 1
            return published
        finally:
            await connection.close()


class EventValidationError(ValueError):
    pass


class EventConsumerRuntime:
    def __init__(self, dsn: str, *, consumer: str) -> None:
        if not consumer or len(consumer) > 150:
            raise ValueError("CONSUMER_NAME_INVALID")
        self.dsn = dsn
        self.consumer = consumer

    async def process(self, envelope: dict[str, Any], handler: EventHandler) -> str:
        validate_event_envelope(envelope)
        correlation_token = bind_event_correlation(envelope)
        try:
            event_id = UUID(envelope["id"])
            organization_id = UUID(envelope["organizationid"])
            connection = await asyncpg.connect(self.dsn)
            try:
                async with connection.transaction():
                    inserted = await connection.fetchval(
                        """
                        INSERT INTO inbox_events (
                            id, organization_id, event_id, consumer, processed_at, created_at
                        ) VALUES ($1, $2, $3, $4, now(), now())
                        ON CONFLICT (consumer, event_id) DO NOTHING
                        RETURNING event_id
                        """,
                        new_uuid7(),
                        organization_id,
                        event_id,
                        self.consumer,
                    )
                    if inserted is None:
                        return "DUPLICATE"
                    await handler(connection, envelope)
                return "PROCESSED"
            finally:
                await connection.close()
        finally:
            reset_event_correlation(correlation_token)


class DeadLetterStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def record(
        self,
        *,
        envelope: dict[str, Any],
        source_queue: str,
        consumer: str,
        exchange_name: str,
        routing_key: str,
        category: ErrorCategory,
        error_code: str,
        error_message: str,
        attempts: int,
        message_kind: str = "domain_event",
    ) -> UUID:
        message_id = _safe_uuid(envelope.get("id")) or new_uuid7()
        organization_id = _safe_uuid(envelope.get("organizationid"))
        record_id = new_uuid7()
        connection = await asyncpg.connect(self.dsn)
        try:
            await connection.execute(
                """
                INSERT INTO dead_letter_records (
                    id, organization_id, message_id, message_kind, source_queue, consumer,
                    exchange_name, routing_key, error_category, error_code, error_message,
                    attempts, trace_id, payload_json, first_failed_at, last_failed_at,
                    created_at, updated_at, version
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,
                    now(),now(),now(),now(),1
                )
                """,
                record_id,
                organization_id,
                message_id,
                message_kind,
                source_queue,
                consumer,
                exchange_name,
                routing_key,
                category.value,
                error_code[:128],
                error_message[:2000],
                max(1, attempts),
                str(envelope.get("traceid"))[:128] if envelope.get("traceid") else None,
                json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
            )
            return record_id
        finally:
            await connection.close()


class KombuEventConsumer:
    """One-message adapter used by supervisors/tests; ack occurs only after DB commit."""

    def __init__(
        self,
        *,
        broker_url: str,
        runtime: EventConsumerRuntime,
        dead_letters: DeadLetterStore,
        binding_key: str = "#",
    ) -> None:
        self.broker_url = broker_url
        self.runtime = runtime
        self.dead_letters = dead_letters
        self.binding_key = binding_key

    def consume_one(self, handler: EventHandler, *, timeout: float = 1.0) -> str:
        queue = domain_queue(self.runtime.consumer, self.binding_key)
        with Connection(self.broker_url) as connection:
            with connection.SimpleQueue(queue) as simple_queue:
                message = simple_queue.get(block=True, timeout=timeout)
                envelope = message.payload
                try:
                    result = asyncio.run(self.runtime.process(envelope, handler))
                except Exception as exc:
                    category = classify_error(
                        code=getattr(exc, "code", type(exc).__name__),
                        retryable=(
                            False
                            if isinstance(exc, EventValidationError)
                            else getattr(exc, "retryable", None)
                        ),
                    )
                    if category == ErrorCategory.TRANSIENT:
                        message.reject(requeue=True)
                    else:
                        attempts = _death_attempts(message.headers)
                        asyncio.run(
                            self.dead_letters.record(
                                envelope=(
                                    envelope if isinstance(envelope, dict) else {"data": envelope}
                                ),
                                source_queue=queue.name,
                                consumer=self.runtime.consumer,
                                exchange_name=DOMAIN_EXCHANGE.name,
                                routing_key=str(message.delivery_info.get("routing_key", "#")),
                                category=category,
                                error_code=str(getattr(exc, "code", type(exc).__name__)),
                                error_message=str(exc),
                                attempts=attempts,
                            )
                        )
                        message.reject(requeue=False)
                    raise
                else:
                    message.ack()
                    return result


def validate_event_envelope(envelope: dict[str, Any]) -> None:
    required = {
        "specversion",
        "id",
        "source",
        "type",
        "subject",
        "time",
        "datacontenttype",
        "dataschema",
        "organizationid",
        "correlationid",
        "partitionkey",
        "schemaversion",
        "data",
    }
    missing = required - set(envelope)
    if missing:
        raise EventValidationError(f"EVENT_REQUIRED:{','.join(sorted(missing))}")
    if envelope["specversion"] != "1.0" or envelope["datacontenttype"] != "application/json":
        raise EventValidationError("EVENT_ENVELOPE_VERSION_INVALID")
    UUID(str(envelope["id"]))
    UUID(str(envelope["organizationid"]))
    UUID(str(envelope["correlationid"]))
    if not str(envelope["type"]).startswith("lumi."):
        raise EventValidationError("EVENT_TYPE_INVALID")
    if not str(envelope["source"]).startswith("lumi://"):
        raise EventValidationError("EVENT_SOURCE_INVALID")
    if not isinstance(envelope["schemaversion"], int) or envelope["schemaversion"] < 1:
        raise EventValidationError("EVENT_SCHEMA_VERSION_INVALID")
    if not isinstance(envelope["data"], dict):
        raise EventValidationError("EVENT_DATA_INVALID")
    if envelope["type"] == "lumi.asset.ready":
        data = envelope["data"]
        if not data.get("asset_id") or not data.get("kind"):
            raise EventValidationError("ASSET_READY_PAYLOAD_INVALID")
        UUID(str(data["asset_id"]))
    encoded = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 256 * 1024:
        raise EventValidationError("EVENT_TOO_LARGE")


def _normalized_event_data(record: OutboxRecord) -> dict[str, Any]:
    data = dict(record.payload)
    if record.event_name == "asset.ready":
        data.setdefault("asset_id", str(record.aggregate_id))
        data.setdefault("kind", _asset_kind_from_mime(data.get("mime_type")))
        if "full_checksum_sha256" in data and "checksum_sha256" not in data:
            data["checksum_sha256"] = data["full_checksum_sha256"]
    return data


def _asset_kind_from_mime(value: Any) -> str:
    mime_type = str(value or "").lower()
    if mime_type == "image/svg+xml":
        return "vector"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("video/"):
        return "video"
    if mime_type.startswith("font/") or mime_type in {
        "application/font-sfnt",
        "application/vnd.ms-fontobject",
    }:
        return "font"
    if mime_type == "application/pdf":
        return "document"
    return "asset"


def _safe_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _death_attempts(headers: dict[str, Any] | None) -> int:
    if not headers:
        return 1
    deaths = headers.get("x-death")
    if isinstance(deaths, list) and deaths:
        count = deaths[0].get("count", 1) if isinstance(deaths[0], dict) else 1
        try:
            return max(1, int(count))
        except (TypeError, ValueError):
            return 1
    return 1
