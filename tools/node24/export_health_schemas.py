from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-24/generated-schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
STATES = [
    "unknown",
    "healthy",
    "degraded",
    "open_circuit",
    "recovering",
    "disabled",
]


def object_schema(
    title: str,
    properties: dict[str, object],
    required: list[str],
) -> dict[str, object]:
    return {
        "$schema": DRAFT,
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def nullable(schema: dict[str, object]) -> dict[str, object]:
    return {"anyOf": [schema, {"type": "null"}]}


def schemas() -> dict[str, dict[str, object]]:
    text = {"type": "string", "minLength": 1}
    optional_text = nullable(text)
    nonnegative_int = {"type": "integer", "minimum": 0}
    rate = {"type": "number", "minimum": 0, "maximum": 1}
    epoch = {"type": "number", "minimum": 0}
    optional_epoch = nullable(epoch)
    optional_int = nullable(nonnegative_int)

    capacity = object_schema(
        "CapacityHint",
        {
            "remaining": optional_int,
            "limit": optional_int,
            "reset_at_epoch": optional_epoch,
            "retry_after_seconds": optional_epoch,
        },
        [
            "remaining",
            "limit",
            "reset_at_epoch",
            "retry_after_seconds",
        ],
    )
    snapshot = object_schema(
        "ProviderHealthSnapshot",
        {
            "provider": text,
            "model": optional_text,
            "capability": optional_text,
            "state": {"type": "string", "enum": STATES},
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
            "sample_count": nonnegative_int,
            "success_rate": rate,
            "failure_rate": rate,
            "rate_limit_rate": rate,
            "timeout_rate": rate,
            "latency_p50_ms": optional_int,
            "latency_p95_ms": optional_int,
            "queue_completion_p95_ms": optional_int,
            "consecutive_failures": nonnegative_int,
            "open_until_epoch": optional_epoch,
            "recovering_inflight": nonnegative_int,
            "recovering_successes": nonnegative_int,
            "capacity_hint": nullable(capacity),
            "updated_at_epoch": epoch,
            "reason": text,
            "store_available": {"type": "boolean"},
        },
        [
            "provider",
            "model",
            "capability",
            "state",
            "score",
            "sample_count",
            "success_rate",
            "failure_rate",
            "rate_limit_rate",
            "timeout_rate",
            "latency_p50_ms",
            "latency_p95_ms",
            "queue_completion_p95_ms",
            "consecutive_failures",
            "open_until_epoch",
            "recovering_inflight",
            "recovering_successes",
            "capacity_hint",
            "updated_at_epoch",
            "reason",
            "store_available",
        ],
    )
    transition = object_schema(
        "ProviderHealthTransition",
        {
            "provider": text,
            "model": optional_text,
            "capability": optional_text,
            "previous_state": {
                "type": "string",
                "enum": STATES,
            },
            "current_state": {
                "type": "string",
                "enum": STATES,
            },
            "score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
            "sample_count": nonnegative_int,
            "failure_rate": rate,
            "latency_p95_ms": optional_int,
            "observed_at_epoch": epoch,
            "reason": text,
        },
        [
            "provider",
            "model",
            "capability",
            "previous_state",
            "current_state",
            "score",
            "sample_count",
            "failure_rate",
            "latency_p95_ms",
            "observed_at_epoch",
            "reason",
        ],
    )
    audit = object_schema(
        "ProviderHealthAuditEvent",
        {
            "action": {
                "type": "string",
                "enum": [
                    "force_disabled",
                    "force_degraded",
                    "clear_override",
                    "clear_breaker",
                ],
            },
            "provider": text,
            "model": optional_text,
            "capability": optional_text,
            "actor_id": text,
            "reason": text,
            "observed_at_epoch": epoch,
            "expires_at_epoch": optional_epoch,
        },
        [
            "action",
            "provider",
            "model",
            "capability",
            "actor_id",
            "reason",
            "observed_at_epoch",
            "expires_at_epoch",
        ],
    )
    probe = object_schema(
        "SyntheticProbeDefinition",
        {
            "provider": text,
            "model": text,
            "capability": text,
            "enabled": {"type": "boolean"},
            "provider_terms_allowed": {"type": "boolean"},
            "side_effect_free": {"type": "boolean"},
            "estimated_cost_usd": {
                "type": "string",
                "pattern": "^[0-9]+(?:\\.[0-9]+)?$",
            },
            "timeout_seconds": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
        },
        [
            "provider",
            "model",
            "capability",
            "enabled",
            "provider_terms_allowed",
            "side_effect_free",
            "estimated_cost_usd",
            "timeout_seconds",
        ],
    )
    return {
        "capacity-hint.schema.json": capacity,
        "provider-health-snapshot.schema.json": snapshot,
        "provider-health-transition.schema.json": transition,
        "provider-health-audit.schema.json": audit,
        "synthetic-probe-definition.schema.json": probe,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.schema.json"):
        path.unlink()
    for filename, schema in schemas().items():
        (OUT / filename).write_text(
            json.dumps(
                schema,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"NODE24_EXPORTED_SCHEMAS={len(schemas())}")


if __name__ == "__main__":
    main()
