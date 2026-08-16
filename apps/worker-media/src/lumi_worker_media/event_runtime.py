from __future__ import annotations

import asyncio
import inspect
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID

from kombu import Connection, Producer

from .queue_contracts import ErrorCategory, classify_error
from .topology import DOMAIN_EXCHANGE, domain_queue

MAX_EVENT_MESSAGE_BYTES = 256 * 1024
EVENT_TYPE_RE = re.compile(
    r"^lumi\.[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$"
)
TRACEPARENT_RE = re.compile(r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
PRODUCER_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
AGGREGATE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_ENVELOPE_FIELDS = {
    "spec_version",
    "event_id",
    "event_type",
    "occurred_at",
    "organization_id",
    "aggregate_type",
    "aggregate_id",
    "producer",
    "payload",
}
_OPTIONAL_ENVELOPE_FIELDS = {
    "aggregate_version",
    "correlation_id",
    "causation_id",
    "traceparent",
}
_ALLOWED_ENVELOPE_FIELDS = _REQUIRED_ENVELOPE_FIELDS | _OPTIONAL_ENVELOPE_FIELDS

_PAYLOAD_FIELDS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "lumi.project.created.v1": (
        frozenset({"project_id", "workspace_id", "project_version"}),
        frozenset(),
    ),
    "lumi.asset.ready.v1": (
        frozenset({"asset_id", "mime_type", "checksum_sha256"}),
        frozenset({"project_id"}),
    ),
    "lumi.agent_run.started.v1": (
        frozenset(
            {
                "agent_run_id",
                "project_id",
                "thread_id",
                "graph_version",
                "agent_config_version",
            }
        ),
        frozenset(),
    ),
    "lumi.agent_run.waiting_user.v1": (
        frozenset({"agent_run_id", "project_id", "interaction_id", "reason_code"}),
        frozenset(),
    ),
    "lumi.task.succeeded.v1": (
        frozenset({"task_id", "project_id", "output_artifact_version_ids"}),
        frozenset(),
    ),
    "lumi.generation.completed.v1": (
        frozenset(
            {
                "generation_id",
                "project_id",
                "operation_id",
                "provider",
                "model",
                "output_artifact_version_ids",
            }
        ),
        frozenset(),
    ),
    "lumi.artifact.version_created.v1": (
        frozenset({"artifact_id", "artifact_version_id", "branch_id", "version_number"}),
        frozenset(),
    ),
    "lumi.artifact.approved.v1": (
        frozenset({"artifact_version_id"}),
        frozenset({"approval_id", "actor_id"}),
    ),
    "lumi.cost.recorded.v1": (
        frozenset({"cost_entry_id", "operation_id", "amount", "currency", "kind"}),
        frozenset(),
    ),
}


class EventValidationError(ValueError):
    code = "EVENT_VALIDATION_FAILED"
    retryable = False


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    raw: dict[str, Any]
    event_id: UUID
    event_type: str
    occurred_at: datetime
    organization_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    producer: str
    aggregate_version: int | None
    correlation_id: str | None
    causation_id: UUID | None
    traceparent: str | None
    payload: dict[str, Any]

    @property
    def partition_key(self) -> str:
        return (
            f"org:{self.organization_id}:aggregate:"
            f"{self.aggregate_type}:{self.aggregate_id}"
        )


def validate_event_envelope(value: dict[str, Any]) -> CanonicalEvent:
    if not isinstance(value, dict):
        raise EventValidationError("EVENT_ENVELOPE_OBJECT_REQUIRED")
    missing = _REQUIRED_ENVELOPE_FIELDS - set(value)
    if missing:
        raise EventValidationError(f"EVENT_REQUIRED:{','.join(sorted(missing))}")
    unknown = set(value) - _ALLOWED_ENVELOPE_FIELDS
    if unknown:
        raise EventValidationError(f"EVENT_UNKNOWN_FIELDS:{','.join(sorted(unknown))}")
    if value.get("spec_version") != "lumi.events/1.0":
        raise EventValidationError("EVENT_SPEC_VERSION_UNSUPPORTED")
    event_type = str(value.get("event_type", ""))
    if not EVENT_TYPE_RE.fullmatch(event_type):
        raise EventValidationError("EVENT_TYPE_INVALID")
    if event_type not in _PAYLOAD_FIELDS:
        raise EventValidationError("EVENT_TYPE_UNSUPPORTED")
    aggregate_type = str(value.get("aggregate_type", ""))
    producer = str(value.get("producer", ""))
    if not AGGREGATE_RE.fullmatch(aggregate_type):
        raise EventValidationError("EVENT_AGGREGATE_TYPE_INVALID")
    if not PRODUCER_RE.fullmatch(producer):
        raise EventValidationError("EVENT_PRODUCER_INVALID")
    event_id = _uuid(value.get("event_id"), "EVENT_ID_INVALID")
    organization_id = _uuid(value.get("organization_id"), "EVENT_ORGANIZATION_ID_INVALID")
    aggregate_id = _uuid(value.get("aggregate_id"), "EVENT_AGGREGATE_ID_INVALID")
    causation_id = (
        _uuid(value.get("causation_id"), "EVENT_CAUSATION_ID_INVALID")
        if value.get("causation_id") is not None
        else None
    )
    occurred_at = _datetime(value.get("occurred_at"))
    aggregate_version = value.get("aggregate_version")
    if aggregate_version is not None and (
        not isinstance(aggregate_version, int) or isinstance(aggregate_version, bool) or aggregate_version < 1
    ):
        raise EventValidationError("EVENT_AGGREGATE_VERSION_INVALID")
    correlation_id = value.get("correlation_id")
    if correlation_id is not None and (
        not isinstance(correlation_id, str) or not 1 <= len(correlation_id) <= 128
    ):
        raise EventValidationError("EVENT_CORRELATION_ID_INVALID")
    traceparent = value.get("traceparent")
    if traceparent is not None and (
        not isinstance(traceparent, str) or not TRACEPARENT_RE.fullmatch(traceparent)
    ):
        raise EventValidationError("EVENT_TRACEPARENT_INVALID")
    payload = value.get("payload")
    if not isinstance(payload, dict):
        raise EventValidationError("EVENT_PAYLOAD_OBJECT_REQUIRED")
    _validate_payload(event_type, payload)
    _reject_secret_or_binary(payload, path="$.payload", depth=0)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_EVENT_MESSAGE_BYTES:
        raise EventValidationError("EVENT_TOO_LARGE")
    normalized = json.loads(encoded.decode("utf-8"))
    return CanonicalEvent(
        raw=normalized,
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        organization_id=organization_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        producer=producer,
        aggregate_version=aggregate_version,
        correlation_id=correlation_id,
        causation_id=causation_id,
        traceparent=traceparent,
        payload=dict(payload),
    )


def _validate_payload(event_type: str, payload: dict[str, Any]) -> None:
    required, optional = _PAYLOAD_FIELDS[event_type]
    missing = required - set(payload)
    if missing:
        raise EventValidationError(f"EVENT_PAYLOAD_REQUIRED:{','.join(sorted(missing))}")
    unknown = set(payload) - required - optional
    if unknown:
        raise EventValidationError(f"EVENT_PAYLOAD_UNKNOWN:{','.join(sorted(unknown))}")
    for key, item in payload.items():
        if item is None and key in optional:
            continue
        if key.endswith("_id"):
            _uuid(item, f"EVENT_PAYLOAD_UUID_INVALID:{key}")
        elif key.endswith("_ids"):
            if not isinstance(item, list):
                raise EventValidationError(f"EVENT_PAYLOAD_UUID_LIST_INVALID:{key}")
            for candidate in item:
                _uuid(candidate, f"EVENT_PAYLOAD_UUID_LIST_INVALID:{key}")
    if "checksum_sha256" in payload and not SHA256_RE.fullmatch(str(payload["checksum_sha256"])):
        raise EventValidationError("EVENT_PAYLOAD_CHECKSUM_INVALID")
    for key in ("project_version", "version_number"):
        if key in payload and (
            not isinstance(payload[key], int) or isinstance(payload[key], bool) or payload[key] < 1
        ):
            raise EventValidationError(f"EVENT_PAYLOAD_VERSION_INVALID:{key}")
    if event_type == "lumi.cost.recorded.v1":
        if not isinstance(payload["amount"], str):
            raise EventValidationError("EVENT_COST_AMOUNT_DECIMAL_STRING_REQUIRED")
        try:
            Decimal(payload["amount"])
        except (InvalidOperation, ValueError) as exc:
            raise EventValidationError("EVENT_COST_AMOUNT_INVALID") from exc
        if not re.fullmatch(r"[A-Z]{3}", str(payload["currency"])):
            raise EventValidationError("EVENT_COST_CURRENCY_INVALID")
        if payload["kind"] not in {"charge", "reversal", "adjustment"}:
            raise EventValidationError("EVENT_COST_KIND_INVALID")


def _uuid(value: Any, code: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise EventValidationError(code) from exc


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EventValidationError("EVENT_OCCURRED_AT_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventValidationError("EVENT_OCCURRED_AT_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EventValidationError("EVENT_OCCURRED_AT_TIMEZONE_REQUIRED")
    return parsed


def _reject_secret_or_binary(value: Any, *, path: str, depth: int) -> None:
    if depth > 12:
        raise EventValidationError("EVENT_PAYLOAD_TOO_DEEP")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise EventValidationError(f"EVENT_BINARY_FORBIDDEN:{path}")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if any(
                token in normalized
                for token in (
                    "secret",
                    "password",
                    "api_key",
                    "apikey",
                    "access_token",
                    "refresh_token",
                    "authorization",
                    "credential",
                    "presigned_url",
                    "signed_url",
                )
            ):
                raise EventValidationError(f"EVENT_SECRET_FIELD_FORBIDDEN:{path}.{key}")
            _reject_secret_or_binary(child, path=f"{path}.{key}", depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_secret_or_binary(child, path=f"{path}[{index}]", depth=depth + 1)


@dataclass(frozen=True, slots=True)
class OutboxItem:
    event_id: UUID
    organization_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    envelope_json: dict[str, Any]
    occurred_at: datetime
    created_at: datetime
    published_at: datetime | None = None
    publish_attempts: int = 0
    next_publish_at: datetime | None = None
    last_publish_error: str | None = None
    locked: bool = False

    def canonical_event(self) -> CanonicalEvent:
        event = validate_event_envelope(self.envelope_json)
        if (
            event.event_id != self.event_id
            or event.organization_id != self.organization_id
            or event.event_type != self.event_type
            or event.aggregate_type != self.aggregate_type
            or event.aggregate_id != self.aggregate_id
        ):
            raise EventValidationError("OUTBOX_ENVELOPE_ROW_MISMATCH")
        return event


class DomainPublisher(Protocol):
    def publish(self, event: CanonicalEvent) -> None: ...


class RawPublisher(Protocol):
    def publish_raw(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> None: ...


class KombuDomainPublisher(DomainPublisher, RawPublisher):
    def __init__(self, broker_url: str) -> None:
        self.broker_url = broker_url

    def publish(self, event: CanonicalEvent) -> None:
        self.publish_raw(
            exchange=DOMAIN_EXCHANGE.name,
            routing_key=event.event_type,
            payload=event.raw,
            headers={"lumi-partition-key": event.partition_key},
        )

    def publish_raw(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> None:
        with Connection(self.broker_url, transport_options={"confirm_publish": True}) as connection:
            connection.ensure_connection(max_retries=3)
            with connection.channel() as channel:
                confirm_select = getattr(channel, "confirm_select", None)
                if callable(confirm_select):
                    confirm_select()
                producer = Producer(channel, serializer="json")
                producer.publish(
                    payload,
                    exchange=exchange,
                    routing_key=routing_key,
                    serializer="json",
                    content_type="application/json",
                    delivery_mode=2,
                    headers=headers or {},
                    retry=True,
                    retry_policy={
                        "max_retries": 3,
                        "interval_start": 0,
                        "interval_step": 1,
                        "interval_max": 3,
                    },
                    mandatory=True,
                    declare=[DOMAIN_EXCHANGE] if exchange == DOMAIN_EXCHANGE.name else None,
                )


class MemoryDomainPublisher(DomainPublisher, RawPublisher):
    def __init__(self) -> None:
        self.events: list[CanonicalEvent] = []
        self.raw_messages: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
        self.fail_after_publish = False

    def publish(self, event: CanonicalEvent) -> None:
        self.events.append(event)
        if self.fail_after_publish:
            raise RuntimeError("SIMULATED_CRASH_AFTER_BROKER_ACCEPT")

    def publish_raw(
        self,
        *,
        exchange: str,
        routing_key: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> None:
        self.raw_messages.append((exchange, routing_key, dict(payload), dict(headers or {})))


class OutboxStore(Protocol):
    def claim_batch(
        self,
        *,
        organization_id: UUID,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]: ...

    def mark_published(self, event_id: UUID, *, now: datetime) -> None: ...

    def mark_failed(
        self,
        event_id: UUID,
        *,
        now: datetime,
        next_publish_at: datetime,
        error: str,
    ) -> None: ...


class MemoryOutboxStore(OutboxStore):
    def __init__(self, items: tuple[OutboxItem, ...] = ()) -> None:
        self.items = {item.event_id: item for item in items}

    def claim_batch(
        self,
        *,
        organization_id: UUID,
        now: datetime,
        limit: int,
    ) -> tuple[OutboxItem, ...]:
        candidates = [
            item
            for item in self.items.values()
            if item.organization_id == organization_id
            and item.published_at is None
            and not item.locked
            and (item.next_publish_at is None or item.next_publish_at <= now)
        ]
        candidates.sort(key=lambda item: (item.created_at, item.event_id.int))
        claimed: list[OutboxItem] = []
        for item in candidates[:limit]:
            locked = replace(item, locked=True, publish_attempts=item.publish_attempts + 1)
            self.items[item.event_id] = locked
            claimed.append(locked)
        return tuple(claimed)

    def mark_published(self, event_id: UUID, *, now: datetime) -> None:
        item = self.items[event_id]
        self.items[event_id] = replace(
            item,
            published_at=now,
            next_publish_at=None,
            last_publish_error=None,
            locked=False,
        )

    def mark_failed(
        self,
        event_id: UUID,
        *,
        now: datetime,
        next_publish_at: datetime,
        error: str,
    ) -> None:
        _ = now
        item = self.items[event_id]
        self.items[event_id] = replace(
            item,
            next_publish_at=next_publish_at,
            last_publish_error=error[:2000],
            locked=False,
        )


@dataclass(frozen=True, slots=True)
class DispatchResult:
    claimed: int
    published: int
    failed: int


class OutboxDispatcher:
    def __init__(self, store: OutboxStore, publisher: DomainPublisher) -> None:
        self.store = store
        self.publisher = publisher

    def dispatch_batch(
        self,
        organization_id: UUID,
        *,
        now: datetime,
        limit: int = 100,
    ) -> DispatchResult:
        if not 1 <= limit <= 1000:
            raise ValueError("OUTBOX_BATCH_LIMIT_INVALID")
        items = self.store.claim_batch(organization_id=organization_id, now=now, limit=limit)
        published = 0
        failed = 0
        for item in items:
            try:
                event = item.canonical_event()
                self.publisher.publish(event)
            except Exception as exc:
                failed += 1
                delay = _outbox_retry_delay(item.publish_attempts)
                self.store.mark_failed(
                    item.event_id,
                    now=now,
                    next_publish_at=now + timedelta(seconds=delay),
                    error=f"{type(exc).__name__}:{exc}",
                )
            else:
                self.store.mark_published(item.event_id, now=now)
                published += 1
        return DispatchResult(claimed=len(items), published=published, failed=failed)


def _outbox_retry_delay(attempt: int) -> int:
    return min(300, 2 ** max(0, min(attempt, 8) - 1))


EventHandler = Callable[[CanonicalEvent, object | None], Awaitable[None] | None]


class InboxStore(Protocol):
    async def apply_once(
        self,
        event: CanonicalEvent,
        *,
        consumer: str,
        handler: EventHandler,
    ) -> bool: ...


class MemoryInboxStore(InboxStore):
    def __init__(self) -> None:
        self.receipts: set[tuple[UUID, str]] = set()

    async def apply_once(
        self,
        event: CanonicalEvent,
        *,
        consumer: str,
        handler: EventHandler,
    ) -> bool:
        key = (event.event_id, consumer)
        if key in self.receipts:
            return False
        self.receipts.add(key)
        try:
            result = handler(event, None)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self.receipts.remove(key)
            raise
        return True


class EventConsumerRuntime:
    def __init__(self, inbox: InboxStore, *, consumer: str) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,159}", consumer):
            raise ValueError("CONSUMER_NAME_INVALID")
        self.inbox = inbox
        self.consumer = consumer

    async def process(self, envelope: dict[str, Any], handler: EventHandler) -> str:
        event = validate_event_envelope(envelope)
        applied = await self.inbox.apply_once(event, consumer=self.consumer, handler=handler)
        return "PROCESSED" if applied else "DUPLICATE"


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    id: UUID
    organization_id: UUID
    message_id: UUID
    message_kind: str
    source_queue: str
    exchange_name: str
    routing_key: str
    error_category: ErrorCategory
    error_code: str
    error_message: str
    attempts: int
    payload: dict[str, Any]
    consumer: str | None = None
    traceparent: str | None = None
    first_failed_at: datetime | None = None
    last_failed_at: datetime | None = None
    replayed_at: datetime | None = None


class DeadLetterStore(Protocol):
    async def record(self, record: DeadLetterRecord) -> None: ...

    async def get(self, organization_id: UUID, record_id: UUID) -> DeadLetterRecord | None: ...

    async def mark_replayed(
        self,
        organization_id: UUID,
        record_id: UUID,
        *,
        now: datetime,
    ) -> None: ...


class MemoryDeadLetterStore(DeadLetterStore):
    def __init__(self) -> None:
        self.records: dict[UUID, DeadLetterRecord] = {}

    async def record(self, record: DeadLetterRecord) -> None:
        self.records[record.id] = record

    async def get(self, organization_id: UUID, record_id: UUID) -> DeadLetterRecord | None:
        record = self.records.get(record_id)
        return record if record and record.organization_id == organization_id else None

    async def mark_replayed(
        self,
        organization_id: UUID,
        record_id: UUID,
        *,
        now: datetime,
    ) -> None:
        record = await self.get(organization_id, record_id)
        if record is None:
            raise ValueError("DEAD_LETTER_NOT_FOUND")
        self.records[record_id] = replace(record, replayed_at=now)


class KombuEventConsumer:
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
                payload = message.payload
                try:
                    if not isinstance(payload, dict):
                        raise EventValidationError("EVENT_ENVELOPE_OBJECT_REQUIRED")
                    result = asyncio.run(self.runtime.process(payload, handler))
                except Exception as exc:
                    retryable = False if isinstance(exc, EventValidationError) else getattr(exc, "retryable", None)
                    category = classify_error(
                        code=str(getattr(exc, "code", type(exc).__name__)),
                        retryable=retryable,
                    )
                    if category is ErrorCategory.TRANSIENT:
                        message.reject(requeue=True)
                    else:
                        record = _dead_letter_from_message(
                            payload if isinstance(payload, dict) else {"invalid_payload": str(payload)},
                            source_queue=queue.name,
                            consumer=self.runtime.consumer,
                            exchange_name=DOMAIN_EXCHANGE.name,
                            routing_key=str(message.delivery_info.get("routing_key", "#")),
                            category=category,
                            error_code=str(getattr(exc, "code", type(exc).__name__)),
                            error_message=str(exc),
                            attempts=_delivery_attempts(message.headers),
                        )
                        asyncio.run(self.dead_letters.record(record))
                        message.reject(requeue=False)
                    raise
                else:
                    message.ack()
                    return result


@dataclass(frozen=True, slots=True)
class DeadLetterReplayService:
    store: DeadLetterStore
    publisher: RawPublisher

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
        if record.replayed_at is not None:
            raise ValueError("DEAD_LETTER_ALREADY_REPLAYED")
        if record.message_kind == "domain_event":
            validate_event_envelope(record.payload)
        self.publisher.publish_raw(
            exchange=record.exchange_name,
            routing_key=record.routing_key,
            payload=record.payload,
            headers={"lumi-replayed-from": str(record.id)},
        )
        replayed_at = now or datetime.now(UTC)
        await self.store.mark_replayed(organization_id, record_id, now=replayed_at)
        updated = await self.store.get(organization_id, record_id)
        if updated is None:
            raise RuntimeError("DEAD_LETTER_REPLAY_STATE_LOST")
        return updated


def _dead_letter_from_message(
    payload: dict[str, Any],
    *,
    source_queue: str,
    consumer: str,
    exchange_name: str,
    routing_key: str,
    category: ErrorCategory,
    error_code: str,
    error_message: str,
    attempts: int,
) -> DeadLetterRecord:
    from uuid import uuid4

    organization_id = _uuid(payload.get("organization_id"), "EVENT_ORGANIZATION_ID_INVALID")
    message_id = _uuid(payload.get("event_id"), "EVENT_ID_INVALID")
    traceparent = payload.get("traceparent")
    now = datetime.now(UTC)
    return DeadLetterRecord(
        id=uuid4(),
        organization_id=organization_id,
        message_id=message_id,
        message_kind="domain_event",
        source_queue=source_queue,
        consumer=consumer,
        exchange_name=exchange_name,
        routing_key=routing_key,
        error_category=category,
        error_code=error_code[:128],
        error_message=error_message[:2000],
        attempts=max(1, attempts),
        traceparent=str(traceparent)[:128] if traceparent else None,
        payload=dict(payload),
        first_failed_at=now,
        last_failed_at=now,
    )


def _delivery_attempts(headers: dict[str, Any] | None) -> int:
    if not headers:
        return 1
    value = headers.get("x-delivery-count")
    if value is not None:
        try:
            return max(1, int(value) + 1)
        except (TypeError, ValueError):
            pass
    deaths = headers.get("x-death")
    if isinstance(deaths, list) and deaths and isinstance(deaths[0], dict):
        try:
            return max(1, int(deaths[0].get("count", 1)))
        except (TypeError, ValueError):
            return 1
    return 1
