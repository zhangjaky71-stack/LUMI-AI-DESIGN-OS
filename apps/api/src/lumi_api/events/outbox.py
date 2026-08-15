from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .envelope import EventEnvelope, partition_key


class OutboxProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    organization_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    occurred_at: datetime
    partition_key: str
    envelope_json: dict[str, Any]


class ConsumerReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    consumer: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,159}$")


def project_to_outbox(event: EventEnvelope[BaseModel]) -> OutboxProjection:
    return OutboxProjection(
        event_id=event.event_id,
        organization_id=event.organization_id,
        event_type=event.event_type,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        occurred_at=event.occurred_at,
        partition_key=partition_key(event),
        envelope_json=event.model_dump(mode="json"),
    )


def consumer_receipt(event: EventEnvelope[BaseModel], consumer: str) -> ConsumerReceipt:
    """Map delivery handling to NODE-10 inbox deduplication identity."""

    return ConsumerReceipt(event_id=event.event_id, consumer=consumer)
