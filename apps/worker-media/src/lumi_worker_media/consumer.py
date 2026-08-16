from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from kombu import Connection

from .event_runtime import (
    DeadLetterRecord,
    DeadLetterStore,
    EventConsumerRuntime,
    EventHandler,
    EventValidationError,
    RawPublisher,
)
from .queue_contracts import ErrorCategory, classify_error
from .runtime_ids import new_uuid7
from .topology import DEAD_LETTER_EXCHANGE, DOMAIN_EXCHANGE, domain_queue


class SafeKombuEventConsumer:
    """Fail-closed consumer that cannot poison-loop malformed permanent messages."""

    def __init__(
        self,
        *,
        broker_url: str,
        runtime: EventConsumerRuntime,
        dead_letters: DeadLetterStore,
        quarantine_publisher: RawPublisher,
        binding_key: str = "#",
    ) -> None:
        self.broker_url = broker_url
        self.runtime = runtime
        self.dead_letters = dead_letters
        self.quarantine_publisher = quarantine_publisher
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
                    category = classify_error(
                        code=str(getattr(exc, "code", type(exc).__name__)),
                        retryable=(
                            False
                            if isinstance(exc, EventValidationError)
                            else getattr(exc, "retryable", None)
                        ),
                    )
                    if category is ErrorCategory.TRANSIENT:
                        message.reject(requeue=True)
                    else:
                        self._record_or_quarantine(
                            payload,
                            source_queue=queue.name,
                            routing_key=str(message.delivery_info.get("routing_key", "#")),
                            category=category,
                            error_code=str(getattr(exc, "code", type(exc).__name__)),
                            error_message=str(exc),
                            attempts=_delivery_attempts(message.headers),
                        )
                        message.reject(requeue=False)
                    raise
                else:
                    message.ack()
                    return result

    def _record_or_quarantine(
        self,
        payload: Any,
        *,
        source_queue: str,
        routing_key: str,
        category: ErrorCategory,
        error_code: str,
        error_message: str,
        attempts: int,
    ) -> None:
        envelope = payload if isinstance(payload, dict) else {"invalid_payload": str(payload)}
        organization_id = _try_uuid(envelope.get("organization_id"))
        event_id = _try_uuid(envelope.get("event_id"))
        if organization_id is None or event_id is None:
            self.quarantine_publisher.publish_raw(
                exchange=DEAD_LETTER_EXCHANGE.name,
                routing_key=f"{source_queue}.dead",
                payload={
                    "quarantine_reason": "INVALID_EVENT_IDENTITY",
                    "source_queue": source_queue,
                    "error_code": error_code[:128],
                    "error_message": error_message[:2000],
                    "payload": envelope,
                },
                headers={"lumi-quarantine": True},
            )
            return
        traceparent = envelope.get("traceparent")
        now = datetime.now(UTC)
        record = DeadLetterRecord(
            id=new_uuid7(),
            organization_id=organization_id,
            message_id=event_id,
            message_kind="domain_event",
            source_queue=source_queue,
            consumer=self.runtime.consumer,
            exchange_name=DOMAIN_EXCHANGE.name,
            routing_key=routing_key,
            error_category=category,
            error_code=error_code[:128],
            error_message=error_message[:2000],
            attempts=max(1, attempts),
            traceparent=str(traceparent)[:128] if traceparent else None,
            payload=dict(envelope),
            first_failed_at=now,
            last_failed_at=now,
        )
        try:
            asyncio.run(self.dead_letters.record(record))
        except Exception as exc:
            self.quarantine_publisher.publish_raw(
                exchange=DEAD_LETTER_EXCHANGE.name,
                routing_key=f"{source_queue}.dead",
                payload={
                    "quarantine_reason": "DLQ_PERSISTENCE_FAILED",
                    "record_id": str(record.id),
                    "organization_id": str(organization_id),
                    "event_id": str(event_id),
                    "error": f"{type(exc).__name__}:{exc}"[:2000],
                    "payload": envelope,
                },
                headers={"lumi-quarantine": True},
            )


def _try_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _delivery_attempts(headers: dict[str, Any] | None) -> int:
    if not headers:
        return 1
    raw_count = headers.get("x-delivery-count")
    if raw_count is not None:
        try:
            return max(1, int(raw_count) + 1)
        except (TypeError, ValueError):
            pass
    deaths = headers.get("x-death")
    if isinstance(deaths, list) and deaths and isinstance(deaths[0], dict):
        try:
            return max(1, int(deaths[0].get("count", 1)))
        except (TypeError, ValueError):
            pass
    return 1
