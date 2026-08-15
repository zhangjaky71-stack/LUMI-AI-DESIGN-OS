from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

from lumi_api.events.envelope import EventEnvelope, new_event, partition_key
from lumi_api.events.outbox import consumer_receipt, project_to_outbox
from lumi_api.events.payloads import CostRecordedV1, ProjectCreatedV1
from lumi_api.events.registry import (
    COST_RECORDED_V1,
    EVENT_PAYLOAD_MODELS,
    PROJECT_CREATED_V1,
    parse_event,
)

ORG_A = UUID("01910000-0000-7000-8000-000000000001")
PROJECT_A = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE_A = UUID("01910000-0000-7000-8000-000000000021")


def project_event() -> EventEnvelope[ProjectCreatedV1]:
    return new_event(
        event_type=PROJECT_CREATED_V1,
        organization_id=ORG_A,
        aggregate_type="project",
        aggregate_id=PROJECT_A,
        aggregate_version=1,
        producer="lumi.api",
        correlation_id="request-123",
        payload=ProjectCreatedV1(
            project_id=PROJECT_A,
            workspace_id=WORKSPACE_A,
            project_version=1,
        ),
    )


def test_event_factory_creates_uuid7_and_aware_timestamp() -> None:
    event = project_event()
    assert event.event_id.version == 7
    assert event.occurred_at.tzinfo is not None
    assert event.occurred_at.utcoffset() is not None
    assert event.spec_version == "lumi.events/1.0"


def test_event_envelope_is_immutable_and_extra_fields_are_rejected() -> None:
    event = project_event()
    with pytest.raises(ValidationError):
        EventEnvelope[ProjectCreatedV1].model_validate(
            {**event.model_dump(mode="json"), "broker_offset": 99}
        )

    with pytest.raises(ValidationError):
        event.model_copy(update={"event_type": "bad"}).model_validate(
            {"unexpected": True}
        )


def test_event_type_is_versioned_and_broker_neutral() -> None:
    payload = ProjectCreatedV1(
        project_id=PROJECT_A,
        workspace_id=WORKSPACE_A,
        project_version=1,
    )
    with pytest.raises(ValidationError):
        new_event(
            event_type="project.created",
            organization_id=ORG_A,
            aggregate_type="project",
            aggregate_id=PROJECT_A,
            producer="lumi.api",
            payload=payload,
        )


def test_registry_covers_nine_frozen_p0_event_types_and_round_trips() -> None:
    assert len(EVENT_PAYLOAD_MODELS) == 9
    event = project_event()
    parsed = parse_event(event.model_dump(mode="json"))
    assert parsed.event_id == event.event_id
    assert parsed.event_type == PROJECT_CREATED_V1
    assert parsed.payload.model_dump(mode="json") == event.payload.model_dump(mode="json")


def test_partition_key_is_stable_and_aggregate_local() -> None:
    first = project_event()
    second = first.model_copy(update={"event_id": UUID("01910000-0000-7000-8000-000000000099")})
    assert partition_key(cast(EventEnvelope[BaseModel], first)) == partition_key(
        cast(EventEnvelope[BaseModel], second)
    )

    other = first.model_copy(update={"aggregate_id": WORKSPACE_A})
    assert partition_key(cast(EventEnvelope[BaseModel], first)) != partition_key(
        cast(EventEnvelope[BaseModel], other)
    )


def test_cost_event_preserves_decimal_as_string_in_canonical_json() -> None:
    payload = CostRecordedV1(
        cost_entry_id=UUID("01910000-0000-7000-8000-000000000073"),
        operation_id=UUID("01910000-0000-7000-8000-000000000071"),
        amount=Decimal("0.12345678"),
        currency="USD",
        kind="charge",
    )
    event = new_event(
        event_type=COST_RECORDED_V1,
        organization_id=ORG_A,
        aggregate_type="cost_entry",
        aggregate_id=payload.cost_entry_id,
        producer="lumi.billing",
        payload=payload,
    )
    encoded = event.model_dump(mode="json")
    assert encoded["payload"]["amount"] == "0.12345678"
    assert not isinstance(encoded["payload"]["amount"], float)


def test_outbox_projection_preserves_identity_and_full_envelope() -> None:
    event = project_event()
    projected = project_to_outbox(cast(EventEnvelope[BaseModel], event))
    assert projected.event_id == event.event_id
    assert projected.organization_id == event.organization_id
    assert projected.event_type == event.event_type
    assert projected.aggregate_id == event.aggregate_id
    assert projected.envelope_json["event_id"] == str(event.event_id)
    assert projected.envelope_json["payload"]["project_id"] == str(PROJECT_A)


def test_consumer_receipt_is_event_id_plus_consumer_identity() -> None:
    event = project_event()
    receipt = consumer_receipt(cast(EventEnvelope[BaseModel], event), "artifact-indexer.v1")
    assert receipt.event_id == event.event_id
    assert receipt.consumer == "artifact-indexer.v1"


def test_replay_can_preserve_original_event_identity_and_time() -> None:
    original = project_event()
    replayed = new_event(
        event_type=original.event_type,
        organization_id=original.organization_id,
        aggregate_type=original.aggregate_type,
        aggregate_id=original.aggregate_id,
        aggregate_version=original.aggregate_version,
        producer=original.producer,
        correlation_id=original.correlation_id,
        payload=original.payload,
        occurred_at=original.occurred_at,
        event_id=original.event_id,
    )
    assert replayed.event_id == original.event_id
    assert replayed.occurred_at == original.occurred_at


def test_naive_event_timestamp_is_rejected() -> None:
    payload = ProjectCreatedV1(
        project_id=PROJECT_A,
        workspace_id=WORKSPACE_A,
        project_version=1,
    )
    with pytest.raises(ValidationError):
        new_event(
            event_type=PROJECT_CREATED_V1,
            organization_id=ORG_A,
            aggregate_type="project",
            aggregate_id=PROJECT_A,
            producer="lumi.api",
            payload=payload,
            occurred_at=datetime(2026, 8, 16),
        )


def test_event_package_has_no_broker_orm_or_provider_sdk_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "lumi_api" / "events"
    forbidden = {
        "sqlalchemy",
        "asyncpg",
        "alembic",
        "kafka",
        "confluent_kafka",
        "nats",
        "redis",
        "celery",
        "langgraph",
        "langchain",
        "openai",
        "anthropic",
        "boto3",
    }
    discovered: set[str] = set()

    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                discovered.add(node.module.split(".")[0])

    assert discovered.isdisjoint(forbidden)
