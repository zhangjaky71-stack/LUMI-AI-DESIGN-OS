from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-27/generated-schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"

UUID = {"type": "string", "format": "uuid"}
DECIMAL = {"type": "string", "pattern": r"^-?\d+(?:\.\d+)?$"}


def object_schema(title: str, properties: dict, required: list[str]) -> dict:
    return {
        "$schema": DRAFT,
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


SCHEMAS = {
    "cost-context": object_schema(
        "CostContext",
        {
            "organization_id": UUID,
            "operation_id": UUID,
            "project_id": {"anyOf": [UUID, {"type": "null"}]},
            "task_id": {"anyOf": [UUID, {"type": "null"}]},
            "agent_run_id": {"anyOf": [UUID, {"type": "null"}]},
            "generation_id": {"anyOf": [UUID, {"type": "null"}]},
        },
        ["organization_id", "operation_id"],
    ),
    "usage-fact": object_schema(
        "UsageFact",
        {
            "metric": {"type": "string", "minLength": 1, "maxLength": 100},
            "quantity": DECIMAL,
            "unit": {"type": "string", "minLength": 1, "maxLength": 64},
            "entry_key": {"type": "string", "minLength": 1, "maxLength": 128},
        },
        ["metric", "quantity", "unit", "entry_key"],
    ),
    "actual-cost": object_schema(
        "ActualCost",
        {
            "context": {"$ref": "cost-context.schema.json"},
            "provider": {"type": "string", "minLength": 1, "maxLength": 100},
            "model": {"type": "string", "minLength": 1, "maxLength": 255},
            "amount": DECIMAL,
            "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            "confidence": {"enum": ["exact", "estimated", "unknown"]},
            "pricing_snapshot_id": {"type": ["string", "null"], "maxLength": 128},
            "external_provider_request_id": {
                "type": ["string", "null"],
                "maxLength": 512,
            },
            "entry_key": {"type": "string", "minLength": 1, "maxLength": 128},
            "usage": {
                "type": "array",
                "items": {"$ref": "usage-fact.schema.json"},
            },
        },
        ["context", "provider", "model", "amount", "currency", "confidence"],
    ),
    "budget-reservation": object_schema(
        "BudgetReservationRequest",
        {
            "context": {"$ref": "cost-context.schema.json"},
            "provider": {"type": "string", "minLength": 1, "maxLength": 100},
            "model": {"type": "string", "minLength": 1, "maxLength": 255},
            "estimated_amount": DECIMAL,
            "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            "pricing_snapshot_id": {"type": ["string", "null"], "maxLength": 128},
            "confidence": {"enum": ["exact", "estimated", "unknown"]},
            "reservation_key": {"type": ["string", "null"], "maxLength": 512},
            "ttl_seconds": {"type": "integer", "minimum": 5, "maximum": 86400},
        },
        ["context", "provider", "model", "estimated_amount", "currency"],
    ),
    "cost-summary": object_schema(
        "CostSummary",
        {
            "organization_id": UUID,
            "project_id": {"anyOf": [UUID, {"type": "null"}]},
            "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
            "actual_cost": DECIMAL,
            "adjustments": DECIMAL,
            "reversals": DECIMAL,
            "net_provider_cost": DECIMAL,
            "active_reservations": DECIMAL,
            "unknown_cost_entries": {"type": "integer", "minimum": 0},
        },
        [
            "organization_id",
            "currency",
            "actual_cost",
            "adjustments",
            "reversals",
            "net_provider_cost",
            "active_reservations",
            "unknown_cost_entries",
        ],
    ),
    "quota-lease": object_schema(
        "QuotaLease",
        {
            "lease_id": UUID,
            "organization_id": UUID,
            "operation_id": UUID,
            "metric": {"type": "string", "minLength": 1, "maxLength": 100},
            "quantity": DECIMAL,
            "unit": {"type": "string", "minLength": 1, "maxLength": 64},
            "expires_at": {"type": "string", "format": "date-time"},
            "replayed": {"type": "boolean"},
        },
        [
            "lease_id",
            "organization_id",
            "operation_id",
            "metric",
            "quantity",
            "unit",
            "expires_at",
            "replayed",
        ],
    ),
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.schema.json"):
        stale.unlink()
    for name, schema in sorted(SCHEMAS.items()):
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"NODE-27 exported {len(SCHEMAS)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
