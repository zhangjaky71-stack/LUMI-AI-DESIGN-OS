import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import {
  approveExtractionProposal,
  buildBrandContext,
  createExtractionProposal,
  evaluateBrandApprovalGate,
  evaluateBrandCompliance,
  publishBrandRuleSet,
  validateBrandRuleSet,
} from "./index";
import type { BrandAssetSet, BrandRule, BrandRuleSet, BrandTokenSet } from "./types";

const document: DesignDocument = {
  schema_version: "1.0",
  document_id: "doc-1",
  unit: "px",
  root_id: "root",
  metadata: { document_version: 4 },
  resources: {},
  nodes: {
    root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["logo", "title", "box"] },
    logo: {
      id: "logo",
      kind: "IMAGE",
      role: "logo",
      parent_id: "root",
      children: [],
      asset_id: "logo-a",
      transform: { x: 0, y: 0, width: 20, height: 10, rotation_deg: 5 },
    },
    title: {
      id: "title",
      kind: "TEXT",
      role: "headline",
      parent_id: "root",
      children: [],
      fill: "#ff0000",
      text: "Cheap forever",
      font_asset_id: "font-bad",
      font_size: 10,
    },
    box: {
      id: "box",
      kind: "SHAPE",
      parent_id: "root",
      children: [],
      transform: { x: 22, y: 0, width: 20, height: 10 },
      metadata: { spacing: 7 },
    },
  },
};

const tokenSet: BrandTokenSet = {
  id: "tokens-1",
  brand_profile_id: "brand-1",
  version: "1.0.0",
  colors: [{ id: "primary", name: "Primary", value: "#111111", roles: ["primary"] }],
  fonts: [{ id: "body", name: "Body", asset_id: "font-good", roles: ["body"] }],
  spacing_scale: [4, 8, 12, 16],
};

const assetSet: BrandAssetSet = {
  id: "assets-1",
  brand_profile_id: "brand-1",
  version: "1.0.0",
  logo_asset_ids: ["logo-a"],
  font_asset_ids: ["font-good"],
  reference_asset_ids: ["ref-a"],
};

const rules: readonly BrandRule[] = [
  { id: "color", category: "COLOR", type: "FORBIDDEN_COLORS", severity: "HARD", source: "MANUAL_ADMIN", priority: 100, scope: { roles: ["headline"] }, parameters: { colors: ["#ff0000"] }, active: true },
  { id: "font", category: "TYPOGRAPHY", type: "ALLOWED_FONT_ASSETS", severity: "HARD", source: "MANUAL_ADMIN", priority: 90, scope: { roles: ["headline"] }, parameters: { asset_ids: ["font-good"] }, active: true },
  { id: "size", category: "TYPOGRAPHY", type: "MIN_TEXT_SIZE", severity: "SOFT", source: "MANUAL_ADMIN", priority: 80, scope: { roles: ["headline"] }, parameters: { px: 14 }, active: true },
  { id: "logo-space", category: "LOGO", type: "LOGO_CLEAR_SPACE", severity: "HARD", source: "MANUAL_ADMIN", priority: 100, scope: { roles: ["logo"] }, parameters: { px: 4 }, active: true },
  { id: "logo-rotate", category: "LOGO", type: "LOGO_FORBID_ROTATION", severity: "HARD", source: "MANUAL_ADMIN", priority: 100, scope: { roles: ["logo"] }, parameters: {}, active: true },
  { id: "spacing", category: "SPACING", type: "SPACING_SCALE", severity: "SOFT", source: "MANUAL_ADMIN", priority: 30, scope: { node_ids: ["box"] }, parameters: {}, active: true },
  { id: "voice", category: "VOICE", type: "VOICE_FORBIDDEN_TERMS", severity: "SOFT", source: "MANUAL_ADMIN", priority: 20, scope: { roles: ["headline"] }, parameters: { terms: ["cheap"] }, active: true },
];

const draft: BrandRuleSet = {
  id: "rules-1",
  organization_id: "org-1",
  brand_profile_id: "brand-1",
  version: "1.0.0",
  status: "DRAFT",
  token_set_version: "1.0.0",
  asset_set_version: "1.0.0",
  rules,
  voice: { tone_attributes: ["precise"], preferred_vocabulary: ["crafted"], forbidden_terms: ["cheap"] },
  visual_references: { reference_asset_ids: ["ref-a"], negative_reference_asset_ids: [] },
  created_at: "2026-08-14T00:00:00Z",
};

const published = publishBrandRuleSet(draft, "2026-08-14T00:01:00Z");

describe("NODE-43 Brand Rules Engine", () => {
  it("detects deterministic hard/soft brand violations and returns Design IR repair operations", () => {
    const report = evaluateBrandCompliance({
      document,
      rule_set: published,
      token_set: tokenSet,
      asset_set: assetSet,
      verified_asset_ids: ["logo-a", "font-good"],
      font_rights_allowed_asset_ids: ["font-good"],
    });
    expect(report.decision).toBe("FAIL");
    expect(report.hard_violation_count).toBeGreaterThanOrEqual(4);
    expect(report.diagnostics.some((item) => item.reason_code === "BRAND_COLOR_FORBIDDEN")).toBe(true);
    expect(report.diagnostics.some((item) => item.reason_code === "BRAND_LOGO_CLEAR_SPACE_VIOLATION")).toBe(true);
    expect(report.diagnostics.some((item) => item.reason_code === "BRAND_FONT_NOT_ALLOWED")).toBe(true);
    const colorFix = report.diagnostics.find((item) => item.rule_id === "color")?.repair_operations?.[0];
    expect(colorFix?.type).toBe("SET_PROPERTY");
    expect(colorFix?.expected_document_version).toBe(4);
  });

  it("keeps approved brand rules pinned in compact BrandContext", () => {
    const context = buildBrandContext(published, tokenSet, assetSet);
    expect(context.pinned).toBe(true);
    expect(context.brand_rule_set_version).toBe("1.0.0");
    expect(context.hard_rules.every((rule) => rule.severity === "HARD")).toBe(true);
  });

  it("rejects unreviewed inferred HARD rules", () => {
    expect(() => validateBrandRuleSet({
      ...draft,
      rules: [{ ...rules[0]!, id: "inferred", source: "INFERRED_PROPOSAL", severity: "HARD" }],
    })).toThrow(/cannot be HARD/);
  });

  it("requires citations and human approval before extracted rules can become HARD", () => {
    const proposal = createExtractionProposal({
      id: "proposal-1",
      organization_id: "org-1",
      brand_profile_id: "brand-1",
      source_asset_id: "guide-pdf",
      created_at: "2026-08-14T00:00:00Z",
      candidates: [{
        candidate_id: "candidate-1",
        confidence: 0.9,
        citations: [{ source_asset_id: "guide-pdf", page: 3, span: "Primary logo clear space" }],
        rule: { ...rules[3]!, source: "INFERRED_PROPOSAL", severity: "SOFT" },
      }],
    });
    const approved = approveExtractionProposal(proposal, [{ candidate_id: "candidate-1", severity: "HARD" }], "reviewer-1", "2026-08-14T00:02:00Z");
    expect(approved.approved_rules[0]?.source).toBe("APPROVED_GUIDE_EXTRACTION");
    expect(approved.approved_rules[0]?.severity).toBe("HARD");
    expect(approved.approved_rules[0]?.citations?.[0]?.page).toBe(3);
  });

  it("fails closed on stale token/rule-set versions and artifact approval mismatch", () => {
    expect(() => evaluateBrandCompliance({ document, rule_set: published, token_set: { ...tokenSet, version: "2.0.0" }, asset_set: assetSet })).toThrow(/version mismatch/);
    expect(evaluateBrandApprovalGate({
      id: "v1", organization_id: "org-1", artifact_id: "a1", branch_id: "b1", parent_version_id: null,
      schema_version: "1", version_number: 1, status: "READY", content_hash: "a".repeat(64), constraint_snapshot_hash: "b".repeat(64),
      created_by_type: "SYSTEM", created_by_id: "system", created_at: "2026-08-14T00:00:00Z", brand_rule_set_version: "0.9.0",
    }, { brand_rule_set_version: "1.0.0", decision: "PASS", score: 1, diagnostics: [], hard_violation_count: 0, soft_violation_count: 0, advisory_count: 0 }).reason_code).toBe("BRAND_RULE_VERSION_MISMATCH");
  });
});
