from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-23/generated-schemas"
BASE = {"$schema": "https://json-schema.org/draft/2020-12/schema"}
CAPABILITIES = [
    "llm.reasoning",
    "llm.structured_output",
    "llm.vision",
    "image.generate",
    "image.edit",
    "image.mask_edit",
    "image.reference_consistency",
    "image.transparent_background",
    "video.text_to_video",
    "video.image_to_video",
    "embedding.text",
    "embedding.multimodal",
    "ocr.document",
]

SCHEMAS = {
    "registry-snapshot": {
        **BASE,
        "type": "object",
        "required": [
            "snapshot_id",
            "version",
            "checksum_sha256",
            "observed_at",
            "published_at",
            "models",
            "routing_profiles",
            "source_ref",
        ],
        "properties": {
            "snapshot_id": {
                "type": "string",
                "minLength": 1,
            },
            "version": {
                "type": "string",
                "minLength": 1,
            },
            "checksum_sha256": {
                "type": "string",
                "pattern": "^[0-9a-f]{64}$",
            },
            "observed_at": {
                "type": "string",
                "format": "date-time",
            },
            "published_at": {
                "type": "string",
                "format": "date-time",
            },
            "models": {"type": "object"},
            "routing_profiles": {"type": "object"},
            "source_ref": {
                "type": "string",
                "minLength": 1,
            },
        },
    },
    "capability-claim": {
        **BASE,
        "type": "object",
        "required": [
            "model_key",
            "capability",
            "support",
            "limits",
            "confidence",
            "observed_at",
            "source_ref",
        ],
        "properties": {
            "model_key": {
                "type": "string",
                "minLength": 1,
            },
            "capability": {"enum": CAPABILITIES},
            "support": {
                "enum": [
                    "full",
                    "partial",
                    "none",
                    "unknown",
                ]
            },
            "limits": {"type": "object"},
            "confidence": {
                "enum": [
                    "verified_docs",
                    "live_test",
                    "inferred",
                ]
            },
            "observed_at": {
                "type": "string",
                "format": "date-time",
            },
            "source_ref": {
                "type": "string",
                "minLength": 1,
            },
        },
    },
    "pricing-snapshot": {
        **BASE,
        "type": "object",
        "required": [
            "pricing_snapshot_id",
            "model_key",
            "metric",
            "currency",
            "unit",
            "price",
            "effective_from",
            "observed_at",
            "source_ref",
        ],
        "properties": {
            "pricing_snapshot_id": {
                "type": "string",
                "minLength": 1,
            },
            "model_key": {
                "type": "string",
                "minLength": 1,
            },
            "metric": {
                "type": "string",
                "minLength": 1,
            },
            "currency": {"const": "USD"},
            "unit": {
                "type": "string",
                "minLength": 1,
            },
            "price": {
                "type": "string",
                "pattern": "^[0-9]+(?:\\.[0-9]+)?$",
            },
            "minimum_charge": {
                "type": ["string", "null"],
            },
            "region": {
                "type": ["string", "null"],
            },
            "effective_from": {
                "type": "string",
                "format": "date-time",
            },
            "observed_at": {
                "type": "string",
                "format": "date-time",
            },
            "expires_at": {
                "type": ["string", "null"],
                "format": "date-time",
            },
            "source_ref": {
                "type": "string",
                "minLength": 1,
            },
        },
    },
    "benchmark-score": {
        **BASE,
        "type": "object",
        "required": [
            "benchmark_score_id",
            "model_key",
            "profile",
            "dataset_version",
            "run_id",
            "sample_count",
            "score",
            "observed_at",
            "source_ref",
        ],
        "properties": {
            "benchmark_score_id": {
                "type": "string",
                "minLength": 1,
            },
            "model_key": {
                "type": "string",
                "minLength": 1,
            },
            "profile": {
                "type": "string",
                "minLength": 1,
            },
            "dataset_version": {
                "type": "string",
                "minLength": 1,
            },
            "run_id": {
                "type": "string",
                "minLength": 1,
            },
            "sample_count": {
                "type": "integer",
                "minimum": 1,
            },
            "score": {
                "type": "string",
                "pattern": (
                    "^(?:100(?:\\.0+)?|"
                    "[0-9]{1,2}(?:\\.[0-9]+)?)$"
                ),
            },
            "confidence_low": {
                "type": ["string", "null"],
            },
            "confidence_high": {
                "type": ["string", "null"],
            },
            "statistics": {"type": "object"},
            "observed_at": {
                "type": "string",
                "format": "date-time",
            },
            "source_ref": {
                "type": "string",
                "minLength": 1,
            },
        },
    },
    "routing-profile": {
        **BASE,
        "type": "object",
        "required": [
            "name",
            "required_capabilities",
            "candidate_model_keys",
            "selection_gate",
            "weights",
        ],
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
            },
            "required_capabilities": {
                "type": "array",
                "items": {"enum": CAPABILITIES},
            },
            "candidate_model_keys": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "string",
                    "minLength": 1,
                },
            },
            "stable_fallback_model_keys": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                },
            },
            "selection_gate": {
                "type": "string",
                "minLength": 1,
            },
            "weights": {
                "type": "object",
                "required": [
                    "quality",
                    "constraint",
                    "cost",
                    "latency",
                    "availability",
                ],
            },
        },
    },
    "organization-model-policy": {
        **BASE,
        "type": "object",
        "required": [
            "organization_id",
            "version",
        ],
        "properties": {
            "organization_id": {
                "type": "string",
                "format": "uuid",
            },
            "version": {
                "type": "integer",
                "minimum": 1,
            },
            "disabled_providers": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "allowed_regions": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
            "preferred_models": {
                "type": "array",
                "items": {"type": "string"},
            },
            "max_cost_class": {
                "type": ["string", "null"],
            },
            "data_handling_restrictions": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
            },
        },
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.glob("*.schema.json"):
        path.unlink()
    for name, schema in sorted(SCHEMAS.items()):
        target = OUT / f"{name}.schema.json"
        target.write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
