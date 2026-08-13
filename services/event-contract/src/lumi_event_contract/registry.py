from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from .envelope import EventEnvelope

_ROUTING_KEY = re.compile(r"^[a-z0-9_]+\.[a-z0-9_.]+$")


@dataclass(frozen=True, slots=True)
class EventDefinition:
    name: str
    type: str
    owner_context: str
    routing_key: str
    schema_version: int
    payload_schema: Path
    partition_field: str
    subject_template: str
    payload_schema_id: str
    required_payload_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class EventRegistry:
    exchange: str
    dead_letter_exchange: str
    delivery_semantics: str
    ordering_scope: str
    definitions: Mapping[str, EventDefinition]

    def get(self, name: str) -> EventDefinition:
        try:
            return self.definitions[name]
        except KeyError as exc:
            raise KeyError(f"event is not registered: {name}") from exc


EXPECTED_DOMAIN_EVENTS = frozenset(
    {
        "project.created",
        "asset.ready",
        "agent_run.started",
        "agent_run.waiting_user",
        "artifact.version_created",
        "artifact.approved",
        "task.succeeded",
        "generation.completed",
        "cost.recorded",
    }
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_contract_root() -> Path:
    return repository_root() / "contracts" / "events" / "v1"


def load_registry(contract_root: Path | None = None) -> EventRegistry:
    root = contract_root or default_contract_root()
    registry_json = json.loads((root / "registry.json").read_text(encoding="utf-8"))
    definitions: dict[str, EventDefinition] = {}
    seen_types: set[str] = set()
    seen_routing_keys: set[str] = set()

    for item in registry_json["events"]:
        name = str(item["name"])
        event_type = str(item["type"])
        routing_key = str(item["routing_key"])
        schema_version = int(item["schema_version"])
        schema_path = root / str(item["payload_schema"])
        payload_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        payload_schema_id = str(payload_schema["$id"])

        if name in definitions:
            raise ValueError(f"duplicate event name: {name}")
        if event_type in seen_types:
            raise ValueError(f"duplicate event type: {event_type}")
        if routing_key in seen_routing_keys:
            raise ValueError(f"duplicate routing key: {routing_key}")
        if not _ROUTING_KEY.fullmatch(routing_key):
            raise ValueError(f"invalid routing key: {routing_key}")
        expected_schema_id = f"urn:lumi:event:{name}:{schema_version}"
        if payload_schema_id != expected_schema_id:
            raise ValueError(
                f"payload schema id mismatch for {name}: {payload_schema_id} != {expected_schema_id}"
            )

        definitions[name] = EventDefinition(
            name=name,
            type=event_type,
            owner_context=str(item["owner_context"]),
            routing_key=routing_key,
            schema_version=schema_version,
            payload_schema=schema_path,
            partition_field=str(item["partition_field"]),
            subject_template=str(item["subject_template"]),
            payload_schema_id=payload_schema_id,
            required_payload_fields=frozenset(str(field) for field in payload_schema["required"]),
        )
        seen_types.add(event_type)
        seen_routing_keys.add(routing_key)

    if frozenset(definitions) != EXPECTED_DOMAIN_EVENTS:
        missing = EXPECTED_DOMAIN_EVENTS - frozenset(definitions)
        extra = frozenset(definitions) - EXPECTED_DOMAIN_EVENTS
        raise ValueError(f"event vocabulary mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    if registry_json["delivery_semantics"] != "at_least_once":
        raise ValueError("NODE-12 must not claim delivery semantics other than at_least_once")
    if registry_json["ordering_scope"] != "partitionkey":
        raise ValueError("event ordering scope must be partitionkey")

    return EventRegistry(
        exchange=str(registry_json["exchange"]),
        dead_letter_exchange=str(registry_json["dead_letter_exchange"]),
        delivery_semantics=str(registry_json["delivery_semantics"]),
        ordering_scope=str(registry_json["ordering_scope"]),
        definitions=definitions,
    )


def validate_payload(definition: EventDefinition, payload: Mapping[str, Any]) -> None:
    missing = definition.required_payload_fields - payload.keys()
    if missing:
        raise ValueError(f"missing required payload fields for {definition.name}: {sorted(missing)}")
    partition_value = payload.get(definition.partition_field)
    if partition_value in (None, ""):
        raise ValueError(
            f"partition field {definition.partition_field} is required for {definition.name}"
        )


def build_envelope(
    *,
    registry: EventRegistry,
    event_name: str,
    event_id: UUID,
    source: str,
    organization_id: UUID,
    correlation_id: UUID,
    payload: Mapping[str, Any],
    causation_id: UUID | None = None,
    trace_id: str | None = None,
    occurred_at: datetime | None = None,
) -> EventEnvelope:
    definition = registry.get(event_name)
    validate_payload(definition, payload)
    format_values = {key: str(value) for key, value in payload.items()}
    subject = definition.subject_template.format_map(format_values)
    partition_value = str(payload[definition.partition_field])
    return EventEnvelope(
        id=event_id,
        source=source,
        type=definition.type,
        subject=subject,
        organization_id=organization_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        trace_id=trace_id,
        partition_key=f"{definition.partition_field}:{partition_value}",
        schema_version=definition.schema_version,
        data_schema=definition.payload_schema_id,
        data=dict(payload),
        time=occurred_at or datetime.now(UTC),
    )


def broker_headers(envelope: EventEnvelope, *, delivery_attempt: int) -> dict[str, str | int]:
    if delivery_attempt < 1:
        raise ValueError("delivery_attempt must be >= 1")
    headers: dict[str, str | int] = {
        "x-lumi-event-id": str(envelope.id),
        "x-lumi-schema-version": envelope.schema_version,
        "x-lumi-correlation-id": str(envelope.correlation_id),
        "x-lumi-delivery-attempt": delivery_attempt,
    }
    if envelope.causation_id is not None:
        headers["x-lumi-causation-id"] = str(envelope.causation_id)
    if envelope.trace_id is not None:
        headers["x-lumi-trace-id"] = envelope.trace_id
    return headers
