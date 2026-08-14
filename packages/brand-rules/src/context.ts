import type { JsonValue } from "../../design-ir/src/index";
import type { BrandAssetSet, BrandContext, BrandRuleSet, BrandTokenSet } from "./types";
import { BrandRuleError, validateBrandRuleSet } from "./runtime";

function selectedTokens(tokenSet: BrandTokenSet): Readonly<Record<string, JsonValue>> {
  const colors: Record<string, JsonValue> = {};
  for (const token of [...tokenSet.colors].sort((a, b) => a.id.localeCompare(b.id))) {
    colors[token.id] = { name: token.name, value: token.value, roles: [...token.roles] };
  }
  const fonts: Record<string, JsonValue> = {};
  for (const token of [...tokenSet.fonts].sort((a, b) => a.id.localeCompare(b.id))) {
    fonts[token.id] = {
      name: token.name,
      asset_id: token.asset_id,
      roles: [...token.roles],
      fallbacks: [...(token.fallback_asset_ids ?? [])],
    };
  }
  return {
    colors,
    fonts,
    spacing_scale: [...tokenSet.spacing_scale],
  };
}

export function buildBrandContext(
  ruleSet: BrandRuleSet,
  tokenSet: BrandTokenSet,
  assetSet: BrandAssetSet,
): BrandContext {
  validateBrandRuleSet(ruleSet);
  if (ruleSet.status !== "PUBLISHED") throw new BrandRuleError("BrandContext requires a PUBLISHED BrandRuleSet");
  if (tokenSet.brand_profile_id !== ruleSet.brand_profile_id || assetSet.brand_profile_id !== ruleSet.brand_profile_id) {
    throw new BrandRuleError("BrandContext brand profile mismatch");
  }
  if (tokenSet.version !== ruleSet.token_set_version || assetSet.version !== ruleSet.asset_set_version) {
    throw new BrandRuleError("BrandContext version mismatch");
  }

  const hardRules = ruleSet.rules
    .filter((rule) => rule.active && rule.severity === "HARD")
    .sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id));
  const allowedAssets = [...new Set([
    ...assetSet.logo_asset_ids,
    ...assetSet.font_asset_ids,
    ...assetSet.reference_asset_ids,
  ])].sort();

  return {
    brand_profile_id: ruleSet.brand_profile_id,
    brand_rule_set_id: ruleSet.id,
    brand_rule_set_version: ruleSet.version,
    hard_rules: hardRules,
    selected_tokens: selectedTokens(tokenSet),
    allowed_assets: allowedAssets,
    voice_summary: {
      tone_attributes: [...ruleSet.voice.tone_attributes],
      preferred_vocabulary: [...ruleSet.voice.preferred_vocabulary],
      forbidden_terms: [...ruleSet.voice.forbidden_terms],
    },
    reference_asset_ids: [...ruleSet.visual_references.reference_asset_ids].sort(),
    pinned: true,
  };
}
