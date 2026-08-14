import { describe, expect, it } from "vitest";
import type { DesignConstraint, PostflightContext } from "../../design-constraints/src/types";
import type { DesignDocument } from "../../design-ir/src/index";
import { BrandConstraintAdapter } from "./constraint-adapter";
import type { BrandAssetSet, BrandRuleSet, BrandTokenSet } from "./types";

const document: DesignDocument = {
  schema_version: "1.0",
  document_id: "doc-brand-adapter",
  unit: "px",
  root_id: "root",
  resources: {},
  metadata: { document_version: 1 },
  nodes: {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["title"] },
    title: {
      id: "title",
      kind: "TEXT",
      role: "headline",
      parent_id: "root",
      children: [],
      fill: "#ff0000",
    },
  },
};

const constraint: DesignConstraint = {
  id: "brand-compliance",
  type: "REQUIRE_BRAND_COMPLIANCE",
  scope: {},
  severity: "HARD",
  source: "APPROVED_BRAND_RULE",
  priority: 800,
  parameters: {},
  active: true,
};

const postflight: PostflightContext = {
  document,
  constraints: [constraint],
  before_ref: { artifact_id: "artifact", version: "v1" },
  after_ref: { artifact_id: "artifact", version: "v2" },
};

const ruleSet: BrandRuleSet = {
  id: "rules",
  organization_id: "org",
  brand_profile_id: "brand",
  version: "1.0.0",
  status: "PUBLISHED",
  token_set_version: "1.0.0",
  asset_set_version: "1.0.0",
  rules: [{
    id: "forbidden-red",
    category: "COLOR",
    type: "FORBIDDEN_COLORS",
    severity: "HARD",
    source: "MANUAL_ADMIN",
    priority: 100,
    scope: { roles: ["headline"] },
    parameters: { colors: ["#ff0000"] },
    active: true,
  }],
  voice: { tone_attributes: [], preferred_vocabulary: [], forbidden_terms: [] },
  visual_references: { reference_asset_ids: [], negative_reference_asset_ids: [] },
  created_at: "2026-08-14T00:00:00Z",
  published_at: "2026-08-14T00:01:00Z",
};

const tokenSet: BrandTokenSet = {
  id: "tokens",
  brand_profile_id: "brand",
  version: "1.0.0",
  colors: [{ id: "primary", name: "Primary", value: "#111111", roles: ["primary"] }],
  fonts: [],
  spacing_scale: [4, 8],
};

const assetSet: BrandAssetSet = {
  id: "assets",
  brand_profile_id: "brand",
  version: "1.0.0",
  logo_asset_ids: [],
  font_asset_ids: [],
  reference_asset_ids: [],
};

describe("NODE-43 BrandConstraintAdapter", () => {
  it("maps deterministic brand diagnostics into NODE-39 violations", async () => {
    const adapter = new BrandConstraintAdapter({
      async resolve() {
        return { document, rule_set: ruleSet, token_set: tokenSet, asset_set: assetSet };
      },
    });
    const violations = await adapter.validate(postflight, constraint);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.reason_code).toBe("BRAND_COLOR_FORBIDDEN");
    expect(violations[0]?.severity).toBe("HARD");
  });

  it("fails closed when brand context resolution is unavailable", async () => {
    const adapter = new BrandConstraintAdapter({
      async resolve() {
        throw new Error("brand repository unavailable");
      },
    });
    const violations = await adapter.validate(postflight, constraint);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.reason_code).toBe("VALIDATION_UNAVAILABLE");
    expect(violations[0]?.severity).toBe("HARD");
  });
});
