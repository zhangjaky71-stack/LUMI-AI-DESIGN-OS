from __future__ import annotations

from typing import Any

from .model import BrandAssetSet, BrandRuleError, BrandRuleSet, BrandTokenSet, validate_rule_set


def build_brand_context(
    rule_set: BrandRuleSet,
    token_set: BrandTokenSet,
    asset_set: BrandAssetSet,
) -> dict[str, Any]:
    validate_rule_set(rule_set)
    if rule_set.status != "PUBLISHED":
        raise BrandRuleError("BrandContext requires a PUBLISHED BrandRuleSet")
    if token_set.brand_profile_id != rule_set.brand_profile_id:
        raise BrandRuleError("BrandContext token profile mismatch")
    if asset_set.brand_profile_id != rule_set.brand_profile_id:
        raise BrandRuleError("BrandContext asset profile mismatch")
    if token_set.version != rule_set.token_set_version:
        raise BrandRuleError("BrandContext token version mismatch")
    if asset_set.version != rule_set.asset_set_version:
        raise BrandRuleError("BrandContext asset version mismatch")

    hard_rules = [
        rule
        for rule in sorted(rule_set.rules, key=lambda item: (-item.priority, item.id))
        if rule.active and rule.severity == "HARD"
    ]
    allowed_assets = sorted(
        set(asset_set.logo_asset_ids)
        | set(asset_set.font_asset_ids)
        | set(asset_set.reference_asset_ids)
    )
    return {
        "brand_profile_id": rule_set.brand_profile_id,
        "brand_rule_set_id": rule_set.id,
        "brand_rule_set_version": rule_set.version,
        "hard_rule_ids": [rule.id for rule in hard_rules],
        "selected_tokens": {
            "colors": dict(sorted(token_set.colors.items())),
            "font_asset_ids": list(token_set.font_asset_ids),
            "spacing_scale": list(token_set.spacing_scale),
        },
        "allowed_assets": allowed_assets,
        "voice_summary": dict(rule_set.voice),
        "reference_asset_ids": sorted(asset_set.reference_asset_ids),
        "pinned": True,
    }
