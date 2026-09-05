from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVENT_SRC = ROOT / "services" / "event-contract" / "src"
sys.path.insert(0, str(EVENT_SRC))

from lumi_event_contract import EXPECTED_DOMAIN_EVENTS, load_registry  # noqa: E402

ALLOWED_CONTEXTS = {
    "identity_tenancy",
    "workspace_project",
    "brand",
    "asset",
    "design",
    "artifact_version",
    "agent_execution",
    "workflow_task",
    "generation_provider",
    "billing_cost",
    "collaboration",
    "audit_governance",
}
FORBIDDEN_PAYLOAD_FIELDS = re.compile(
    r"(?:api_?key|secret|password|authorization|access_?token|refresh_?token|raw_?response)$",
    re.IGNORECASE,
)


def fail(message: str) -> None:
    raise SystemExit(f"event contract validation failed: {message}")


def main() -> int:
    contract_root = ROOT / "contracts" / "events" / "v1"
    envelope = json.loads((contract_root / "envelope.schema.json").read_text(encoding="utf-8"))
    registry_json = json.loads((contract_root / "registry.json").read_text(encoding="utf-8"))
    registry = load_registry(contract_root)

    if set(registry.definitions) != set(EXPECTED_DOMAIN_EVENTS):
        fail("registry does not match frozen NODE-09 event vocabulary")
    if registry.delivery_semantics != "at_least_once":
        fail("delivery semantics must remain at_least_once")
    if registry.ordering_scope != "partitionkey":
        fail("ordering scope must remain partitionkey")
    if registry.exchange == registry.dead_letter_exchange:
        fail("event exchange and dead-letter exchange must be distinct")
    if envelope.get("additionalProperties") is not False:
        fail("envelope top-level attributes must be closed")

    required_envelope = {
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
    if not required_envelope.issubset(set(envelope.get("required", []))):
        fail("envelope is missing required identity/tenant/correlation attributes")

    registered_items = {item["name"]: item for item in registry_json["events"]}
    if len(registered_items) != 9:
        fail(f"expected 9 registered events, got {len(registered_items)}")

    for name, definition in registry.definitions.items():
        item = registered_items[name]
        if definition.type != f"lumi.{name}":
            fail(f"{name}: event type must be lumi.{name}")
        if definition.routing_key != name:
            fail(f"{name}: routing key must equal stable domain event name")
        if definition.owner_context not in ALLOWED_CONTEXTS:
            fail(f"{name}: unknown bounded context {definition.owner_context}")
        if definition.schema_version != 1:
            fail(f"{name}: NODE-12 initial schema version must be 1")

        schema = json.loads(definition.payload_schema.read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"{name}: payload must use JSON Schema 2020-12")
        if schema.get("$id") != f"urn:lumi:event:{name}:1":
            fail(f"{name}: payload $id mismatch")
        if schema.get("type") != "object":
            fail(f"{name}: payload root must be object")
        if schema.get("additionalProperties") is not True:
            fail(f"{name}: payload must tolerate additive unknown fields")
        required = set(schema.get("required", []))
        properties = set(schema.get("properties", {}))
        if not required:
            fail(f"{name}: payload must declare at least one required fact")
        if not required.issubset(properties):
            fail(f"{name}: required fields must exist in properties")
        if definition.partition_field not in required:
            fail(f"{name}: partition field must be required in payload")
        for property_name in properties:
            if FORBIDDEN_PAYLOAD_FIELDS.search(property_name):
                fail(f"{name}: forbidden secret/raw field in payload: {property_name}")

        subject_fields = {
            part.split("}", 1)[0]
            for part in definition.subject_template.split("{")[1:]
            if "}" in part
        }
        if not subject_fields.issubset(required):
            fail(f"{name}: subject template may reference required fields only")
        if item["payload_schema"] != f"payloads/{name}.schema.json":
            fail(f"{name}: payload schema path must follow canonical naming")

    cost_schema = json.loads(
        (contract_root / "payloads" / "cost.recorded.schema.json").read_text(encoding="utf-8")
    )
    if cost_schema["properties"]["amount"].get("type") != "string":
        fail("cost.recorded.amount must remain a decimal string, never JSON floating point")

    print(
        "Event Contract V1 PASS: "
        f"{len(registry.definitions)} events, "
        f"exchange={registry.exchange}, semantics={registry.delivery_semantics}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
