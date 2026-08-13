from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from lumi_event_contract import (
    EXPECTED_DOMAIN_EVENTS,
    EventEnvelope,
    broker_headers,
    build_envelope,
    load_registry,
    validate_payload,
)

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
EVENT_ID = UUID("01900000-0000-7000-8000-000000000101")
CORRELATION_ID = UUID("01900000-0000-7000-8000-000000000102")
PROJECT_ID = UUID("01900000-0000-7000-8000-000000000006")
WORKSPACE_ID = UUID("01900000-0000-7000-8000-000000000004")


class EventContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load_registry()

    def test_registry_matches_frozen_domain_vocabulary(self) -> None:
        self.assertEqual(frozenset(self.registry.definitions), EXPECTED_DOMAIN_EVENTS)
        self.assertEqual(len(self.registry.definitions), 9)
        self.assertEqual(self.registry.delivery_semantics, "at_least_once")
        self.assertEqual(self.registry.ordering_scope, "partitionkey")
        self.assertEqual(self.registry.exchange, "lumi.events.v1")

    def test_payload_schema_ids_match_registry_versions(self) -> None:
        for definition in self.registry.definitions.values():
            schema = json.loads(definition.payload_schema.read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$id"],
                f"urn:lumi:event:{definition.name}:{definition.schema_version}",
            )
            self.assertTrue(schema["additionalProperties"])
            self.assertIn(definition.partition_field, schema["required"])

    def test_project_created_envelope_round_trip(self) -> None:
        envelope = build_envelope(
            registry=self.registry,
            event_name="project.created",
            event_id=EVENT_ID,
            source="lumi://api/projects",
            organization_id=ORG_ID,
            correlation_id=CORRELATION_ID,
            payload={
                "project_id": str(PROJECT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "name": "Campaign",
                "status": "active",
            },
            occurred_at=datetime(2026, 8, 13, 1, 0, tzinfo=UTC),
        )
        self.assertEqual(envelope.type, "lumi.project.created")
        self.assertEqual(envelope.subject, f"project/{PROJECT_ID}")
        self.assertEqual(envelope.partition_key, f"project_id:{PROJECT_ID}")
        self.assertEqual(envelope.data_schema, "urn:lumi:event:project.created:1")

        restored = EventEnvelope.from_dict(envelope.to_dict())
        self.assertEqual(restored.to_json(), envelope.to_json())

    def test_envelope_data_is_deeply_immutable(self) -> None:
        envelope = build_envelope(
            registry=self.registry,
            event_name="project.created",
            event_id=EVENT_ID,
            source="lumi://api/projects",
            organization_id=ORG_ID,
            correlation_id=CORRELATION_ID,
            payload={
                "project_id": str(PROJECT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "name": "Campaign",
                "nested": {"tags": ["a", "b"]},
            },
        )
        with self.assertRaises(TypeError):
            envelope.data["name"] = "mutated"  # type: ignore[index]
        nested = envelope.data["nested"]
        self.assertIsInstance(nested, dict | object)
        self.assertEqual(envelope.to_dict()["data"]["nested"]["tags"], ["a", "b"])

    def test_missing_required_payload_field_is_rejected(self) -> None:
        definition = self.registry.get("project.created")
        with self.assertRaisesRegex(ValueError, "missing required payload fields"):
            validate_payload(
                definition,
                {
                    "project_id": str(PROJECT_ID),
                    "name": "Missing workspace",
                },
            )

    def test_delivery_attempt_is_broker_metadata_not_event_mutation(self) -> None:
        envelope = build_envelope(
            registry=self.registry,
            event_name="project.created",
            event_id=EVENT_ID,
            source="lumi://api/projects",
            organization_id=ORG_ID,
            correlation_id=CORRELATION_ID,
            payload={
                "project_id": str(PROJECT_ID),
                "workspace_id": str(WORKSPACE_ID),
                "name": "Campaign",
            },
        )
        before = envelope.to_json()
        first = broker_headers(envelope, delivery_attempt=1)
        third = broker_headers(envelope, delivery_attempt=3)
        self.assertEqual(first["x-lumi-delivery-attempt"], 1)
        self.assertEqual(third["x-lumi-delivery-attempt"], 3)
        self.assertEqual(envelope.to_json(), before)

    def test_envelope_schema_forbids_unknown_top_level_attributes(self) -> None:
        root = Path(__file__).resolve().parents[3]
        schema_path = root / "contracts" / "events" / "v1" / "envelope.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        for required in (
            "id",
            "source",
            "type",
            "organizationid",
            "correlationid",
            "partitionkey",
            "schemaversion",
            "data",
        ):
            self.assertIn(required, schema["required"])


if __name__ == "__main__":
    unittest.main()
