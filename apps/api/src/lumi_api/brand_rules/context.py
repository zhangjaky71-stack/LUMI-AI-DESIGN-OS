from __future__ import annotations

import json

from .contracts import BrandContext


def render_brand_context(context: BrandContext) -> str:
    payload = {
        "schema": "lumi.brand-context/1.0",
        "brand_id": str(context.brand_id),
        "rule_set_id": str(context.rule_set_id),
        "rule_set_version": context.rule_set_version,
        "snapshot_hash": context.snapshot_hash,
        "hard_rules": [
            {
                "key": item.key,
                "kind": item.kind.value,
                "parameters": item.parameters,
            }
            for item in context.hard_rules
        ],
        "tokens": {item.id: item.value for item in context.selected_tokens},
        "allowed_logo_asset_ids": [str(item) for item in context.allowed_logo_asset_ids],
        "allowed_font_asset_ids": [str(item) for item in context.allowed_font_asset_ids],
        "voice_summary": list(context.voice_summary),
        "reference_asset_ids": [str(item) for item in context.reference_asset_ids],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
