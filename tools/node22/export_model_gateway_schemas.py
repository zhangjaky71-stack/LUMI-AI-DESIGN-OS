from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-22/generated-schemas"

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

BASE = {"$schema": "https://json-schema.org/draft/2020-12/schema"}

SCHEMAS = {
    "model-request": {
        **BASE,
        "type": "object",
        "required": [
            "request_id",
            "organization_id",
            "operation_id",
            "capability",
            "inputs",
        ],
        "properties": {
            "request_id": {"type": "string", "format": "uuid"},
            "organization_id": {"type": "string", "format": "uuid"},
            "operation_id": {"type": "string", "format": "uuid"},
            "capability": {"enum": CAPABILITIES},
            "quality_profile": {"enum": ["draft", "balanced", "high", "max"]},
            "latency_profile": {"enum": ["interactive", "standard", "batch"]},
            "budget_limit": {"type": ["string", "null"]},
            "inputs": {"type": "array", "minItems": 1},
        },
        "additionalProperties": True,
    },
    "normalized-result": {
        **BASE,
        "type": "object",
        "required": ["status", "provider", "model", "outputs", "usage", "cost"],
        "properties": {
            "status": {"enum": ["completed", "pending", "failed", "cancelled"]},
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "provider_request_id": {"type": ["string", "null"]},
            "outputs": {"type": "array"},
            "usage": {"type": "object"},
            "cost": {"type": "object"},
        },
    },
    "model-stream-chunk": {
        **BASE,
        "type": "object",
        "required": ["event", "provider", "model"],
        "properties": {
            "event": {"enum": ["started", "text_delta", "usage", "completed", "error"]},
            "provider": {"type": "string"},
            "model": {"type": "string"},
        },
    },
    "provider-model": {
        **BASE,
        "type": "object",
        "required": ["provider", "model", "capabilities", "paid"],
        "properties": {
            "provider": {"type": "string"},
            "model": {"type": "string"},
            "capabilities": {"type": "array", "items": {"enum": CAPABILITIES}},
            "paid": {"type": "boolean"},
        },
    },
    "route-decision": {
        **BASE,
        "type": "object",
        "required": ["request_id", "candidates", "rejected_reason_codes"],
        "properties": {
            "request_id": {"type": "string", "format": "uuid"},
            "candidates": {"type": "array"},
            "rejected_reason_codes": {"type": "array", "items": {"type": "string"}},
        },
    },
    "provider-error": {
        **BASE,
        "type": "object",
        "required": ["category", "acceptance", "retryable"],
        "properties": {
            "category": {"type": "string"},
            "acceptance": {"enum": ["not_accepted", "accepted", "unknown"]},
            "retryable": {"type": "boolean"},
        },
    },
    "cost-telemetry": {
        **BASE,
        "type": "object",
        "required": ["request", "candidate", "result", "fallback_index", "retry_count"],
        "properties": {
            "fallback_index": {"type": "integer", "minimum": 0},
            "retry_count": {"type": "integer", "minimum": 0},
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
