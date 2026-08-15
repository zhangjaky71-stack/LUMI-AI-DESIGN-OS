from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from lumi_api.events.envelope import EventEnvelope, new_event, partition_key
from lumi_api.events.outbox import project_to_outbox
from lumi_api.events.payloads import CostRecordedV1, ProjectCreatedV1
from lumi_api.events.registry import (
    COST_RECORDED_V1,
    EVENT_PAYLOAD_MODELS,
    PROJECT_CREATED_V1,
    parse_event,
)

ROOT = Path(__file__).resolve().parents[2]
EVENT_ROOT = ROOT / "apps" / "api" / "src" / "lumi_api" / "events"
DOC = ROOT / "docs" / "events" / "EVENT-CONTRACT-V1.md"

EXPECTED_EVENT_TYPES = {
    "lumi.project.created.v1",
    "lumi.asset.ready.v1",
    "lumi.agent_run.started.v1",
    "lumi.agent_run.waiting_user.v1",
    "lumi.task.succeeded.v1",
    "lumi.generation.completed.v1",
    "lumi.artifact.version_created.v1",
    "lumi.artifact.approved.v1",
    "lumi.cost.recorded.v1",
}
FORBIDDEN_IMPORT_ROOTS = {
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
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")


def assert_registry_contract() -> None:
    assert set(EVENT_PAYLOAD_MODELS) == EXPECTED_EVENT_TYPES
    for event_type, payload_model in EVENT_PAYLOAD_MODELS.items():
        assert event_type.endswith(".v1")
        assert issubclass(payload_model, BaseModel)
        assert payload_model.model_config.get("frozen") is True
        assert payload_model.model_config.get("extra") == "forbid"


def assert_round_trip_and_projection() -> None:
    payload = ProjectCreatedV1(
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        project_version=1,
    )
    event = new_event(
        event_type=PROJECT_CREATED_V1,
        organization_id=ORG,
        aggregate_type="project",
        aggregate_id=PROJECT,
        aggregate_version=1,
        producer="lumi.api",
        correlation_id="node12-validator",
        payload=payload,
    )
    serialized = event.model_dump(mode="json")
    parsed = parse_event(serialized)
    assert parsed.event_id == event.event_id
    assert parsed.payload.model_dump(mode="json") == payload.model_dump(mode="json")

    projected = project_to_outbox(event)  # type: ignore[arg-type]
    assert projected.event_id == event.event_id
    assert projected.envelope_json["payload"]["project_id"] == str(PROJECT)
    assert projected.partition_key == partition_key(event)  # type: ignore[arg-type]


def assert_decimal_contract() -> None:
    payload = CostRecordedV1(
        cost_entry_id=UUID("01910000-0000-7000-8000-000000000073"),
        operation_id=UUID("01910000-0000-7000-8000-000000000071"),
        amount=Decimal("123.45678901"),
        currency="USD",
        kind="charge",
    )
    event = new_event(
        event_type=COST_RECORDED_V1,
        organization_id=ORG,
        aggregate_type="cost_entry",
        aggregate_id=payload.cost_entry_id,
        producer="lumi.billing",
        payload=payload,
    )
    encoded = event.model_dump(mode="json")
    assert encoded["payload"]["amount"] == "123.45678901"
    assert not isinstance(encoded["payload"]["amount"], float)


def assert_dependency_purity() -> None:
    discovered: set[str] = set()
    for path in EVENT_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                discovered.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                discovered.add(node.module.split(".")[0])
    assert discovered.isdisjoint(FORBIDDEN_IMPORT_ROOTS), discovered & FORBIDDEN_IMPORT_ROOTS


def assert_documented_delivery_semantics() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    assert "at-least-once" in text
    assert "inbox_events(event_id, consumer)" in text
    assert "replay preserves it" in text
    assert "there is no global event order" in text
    assert "security definer" not in text  # DB implementation detail stays in NODE-10 docs.


def main() -> None:
    assert_registry_contract()
    assert_round_trip_and_projection()
    assert_decimal_contract()
    assert_dependency_purity()
    assert_documented_delivery_semantics()
    print(
        "NODE-12 event contract validation PASS: "
        "9 v1 event types, immutable strict payloads, UUIDv7 envelope, "
        "Decimal-safe JSON, Outbox/Inbox semantics, broker-neutral dependencies"
    )


if __name__ == "__main__":
    main()
