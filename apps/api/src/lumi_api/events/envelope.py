from __future__ import annotations

from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lumi_api.domain.ids import new_uuid7

T = TypeVar("T", bound=BaseModel)

EVENT_TYPE_PATTERN = (
    r"^lumi\.[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$"
)
TRACEPARENT_PATTERN = r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"


class EventContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventEnvelope(EventContractModel, Generic[T]):
    spec_version: str = Field(default="lumi.events/1.0", pattern=r"^lumi\.events/1\.0$")
    event_id: UUID
    event_type: str = Field(pattern=EVENT_TYPE_PATTERN, max_length=200)
    occurred_at: datetime
    organization_id: UUID
    aggregate_type: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    aggregate_id: UUID
    aggregate_version: int | None = Field(default=None, ge=1)
    producer: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    causation_id: UUID | None = None
    traceparent: str | None = Field(default=None, pattern=TRACEPARENT_PATTERN)
    payload: T

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


def new_event(
    *,
    event_type: str,
    organization_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    producer: str,
    payload: T,
    aggregate_version: int | None = None,
    correlation_id: str | None = None,
    causation_id: UUID | None = None,
    traceparent: str | None = None,
    occurred_at: datetime | None = None,
    event_id: UUID | None = None,
) -> EventEnvelope[T]:
    return EventEnvelope[T](
        event_id=event_id or new_uuid7(),
        event_type=event_type,
        occurred_at=occurred_at or datetime.now(UTC),
        organization_id=organization_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        producer=producer,
        correlation_id=correlation_id,
        causation_id=causation_id,
        traceparent=traceparent,
        payload=payload,
    )


def partition_key(event: EventEnvelope[BaseModel]) -> str:
    """Stable aggregate-local partition key; it is not a global ordering key."""

    return (
        f"org:{event.organization_id}:"
        f"aggregate:{event.aggregate_type}:{event.aggregate_id}"
    )
