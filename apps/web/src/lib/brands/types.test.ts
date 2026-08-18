import { describe, expect, it } from "vitest";

import {
  draftWire,
  parseBrandRecord,
  parseBrandRuleSet,
  type BrandDraftInput,
} from "./types";

const HASH = "a".repeat(64);

function ruleSetPayload() {
  return {
    id: "rule-set-1",
    organization_id: "org-1",
    brand_id: "brand-1",
    version: 4,
    status: "PUBLISHED",
    source: "USER_EXPLICIT",
    token_set: {
      id: "token-set-1",
      version: 2,
      tokens: [{ id: "color.primary", value: "#111111", profile: "srgb" }],
    },
    asset_set: {
      id: "asset-set-1",
      version: 2,
      allowed_logo_asset_ids: ["logo-1"],
      allowed_font_asset_ids: ["font-1"],
      reference_asset_ids: ["ref-1"],
      negative_reference_asset_ids: ["ref-bad"],
    },
    rules: [{
      id: "rule-1",
      key: "palette.allowed",
      kind: "ALLOWED_COLOR",
      severity: "HARD",
      source: "USER_EXPLICIT",
      parameters: { colors: ["#111111"] },
      description: "Approved palette",
    }],
    voice: {
      tone_attributes: ["calm"],
      preferred_vocabulary: ["considered"],
      forbidden_terms: ["cheap"],
      do_examples: ["Clear and concise"],
      dont_examples: ["Overclaim"],
      locale_notes: [["en-US", "Use sentence case"]],
    },
    visual_style: {
      photography_direction: ["editorial"],
      lighting: ["soft"],
      composition: ["spacious"],
      background_style: ["neutral"],
      texture: ["subtle"],
      illustration_style: ["minimal"],
    },
    created_by: "user:test",
    created_at: "2026-08-18T00:00:00Z",
    published_at: "2026-08-18T00:05:00Z",
    published_by: "user:test",
    snapshot_hash: HASH,
  };
}

describe("NODE-58 Brand Kit public contracts", () => {
  it("preserves Brand resource version and active RuleSet pointer", () => {
    const brand = parseBrandRecord({
      id: "brand-1",
      organization_id: "org-1",
      name: "LUMI",
      profile: { category: "design" },
      active_rule_set_version_id: "rule-set-1",
      version: 7,
      created_at: "2026-08-18T00:00:00Z",
      updated_at: "2026-08-18T00:10:00Z",
    });
    expect(brand.version).toBe(7);
    expect(brand.activeRuleSetVersionId).toBe("rule-set-1");
  });

  it("parses the complete immutable BrandRuleSet snapshot", () => {
    const value = parseBrandRuleSet(ruleSetPayload());
    expect(value.status).toBe("PUBLISHED");
    expect(value.tokenSet.tokens[0]?.id).toBe("color.primary");
    expect(value.assetSet.allowedFontAssetIds).toEqual(["font-1"]);
    expect(value.rules[0]?.parameters).toEqual({ colors: ["#111111"] });
    expect(value.voice.forbiddenTerms).toEqual(["cheap"]);
    expect(value.snapshotHash).toBe(HASH);
  });

  it("serializes a new draft without mutating source semantics", () => {
    const parsed = parseBrandRuleSet(ruleSetPayload());
    const input: BrandDraftInput = {
      source: "USER_EXPLICIT",
      tokenSet: parsed.tokenSet,
      assetSet: parsed.assetSet,
      rules: parsed.rules,
      voice: parsed.voice,
      visualStyle: parsed.visualStyle,
    };
    const wire = draftWire(input);
    expect(wire).toMatchObject({
      source: "USER_EXPLICIT",
      token_set: { tokens: [{ id: "color.primary", value: "#111111" }] },
      asset_set: { allowed_logo_asset_ids: ["logo-1"], allowed_font_asset_ids: ["font-1"] },
      rules: [{ kind: "ALLOWED_COLOR", source: "USER_EXPLICIT" }],
    });
  });

  it("rejects invalid status and malformed snapshot hashes", () => {
    expect(() => parseBrandRuleSet({ ...ruleSetPayload(), status: "ACTIVE" })).toThrow("BRAND_RULE_SET_STATUS_INVALID");
    expect(() => parseBrandRuleSet({ ...ruleSetPayload(), snapshot_hash: "bad" })).toThrow("SHA256_INVALID");
  });
});
