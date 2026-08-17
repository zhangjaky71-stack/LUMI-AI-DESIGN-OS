import { describe, expect, it } from "vitest";
import {
  P0_VALIDATORS,
  createIrPreflight,
  proposeFixOperations,
  stableViolationId,
  validateBatch,
  validateConstraints,
  validateExport,
  validateProposedFix,
  type DesignDocumentLike,
  type RuntimeConstraint,
} from "../src/index";

function document(): DesignDocumentLike {
  return {
    schema_version: "1.0",
    document_id: "poster",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"], transform: { x: 0, y: 0, width: 750, height: 1624 } },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: ["headline", "qr", "logo", "hero"], transform: { x: 0, y: 0, width: 750, height: 1624 } },
      headline: { id: "headline", kind: "TEXT", role: "HEADLINE", parent_id: "frame", children: [], content: "夏日咖啡", font_size: 48, font_family: "Inter", fill: "#111111", background: "#ffffff", transform: { x: 80, y: 100, width: 500, height: 100 } },
      qr: { id: "qr", kind: "IMAGE", role: "QR_CODE", parent_id: "frame", children: [], quiet_zone_px: 12, foreground: "#000000", background: "#ffffff", transform: { x: 550, y: 1400, width: 120, height: 120 } },
      logo: { id: "logo", kind: "IMAGE", role: "LOGO", parent_id: "frame", children: [], locked: true, transform: { x: 50, y: 50, width: 100, height: 60, rotation_deg: 0 } },
      hero: { id: "hero", kind: "IMAGE", role: "HERO_PRODUCT", parent_id: "frame", children: [], asset_id: "asset-a", transform: { x: 100, y: 400, width: 500, height: 500 } },
    },
    metadata: { document_version: 7 },
  };
}

function c(id: string, type: string, nodes: readonly string[], parameters: Record<string, unknown> = {}): RuntimeConstraint {
  return { constraint_id: id, type, severity: "HARD", scope: { node_ids: nodes }, parameters };
}

describe("NODE-39 Constraint Validator", () => {
  it("freezes the 12-validator P0 registry", () => expect(P0_VALIDATORS).toHaveLength(12));

  it("projects operation candidates before validation and creates IR hook issues", () => {
    const rule = c("bounds", "MUST_STAY_INSIDE", ["headline"], { region: { x: 0, y: 0, width: 750, height: 1624 } });
    const operation = { operation_id: "move", type: "MOVE_NODE", target_ids: ["headline"], expected_document_version: 7, payload: { x: 700, y: 100 } };
    const report = validateConstraints(document(), [rule], { operation });
    expect(report.hard_pass).toBe(false);
    expect(createIrPreflight([rule])(document(), operation)[0]?.code).toBe("IR_CONSTRAINT_FAILED");
    expect((document().nodes.headline!.transform as { x: number }).x).toBe(80);
  });

  it("fails closed for unavailable CJK text and identity evidence", () => {
    const rules = [
      c("text", "REQUIRE_TEXT_READABILITY", ["headline"], { require_measurement: true }),
      c("identity", "REQUIRE_IDENTITY_SCORE", ["hero"], { min_score: 0.95 }),
    ];
    const report = validateConstraints(document(), rules);
    expect(report.status).toBe("BLOCKED");
    expect(report.violations.filter((item) => item.unavailable)).toHaveLength(2);
  });

  it("enforces QR decode/size and export dimensions", () => {
    const qr = c("qr", "REQUIRE_SCANNABILITY", ["qr"], { min_size_px: 128, require_decode: true });
    const report = validateConstraints(document(), [qr], { adapters: { qr_decode: () => true } });
    expect(report.violations.some((item) => item.validator === "QRValidator")).toBe(true);
    const exportRule = c("export", "REQUIRE_RESOLUTION", ["frame"], { width: 1080, height: 1920 });
    expect(validateExport(document(), [exportRule]).hard_pass).toBe(false);
  });

  it("returns all batch violations and prevents unsafe autofix", () => {
    const rules = [
      c("bounds", "MUST_STAY_INSIDE", ["headline"], { region: { x: 0, y: 0, width: 750, height: 1624 } }),
      c("lock", "LOCK_TRANSFORM", ["logo"]),
      c("font", "REQUIRE_TEXT_READABILITY", ["headline"], { min_font_size: 60, require_measurement: false }),
      c("brand", "REQUIRE_BRAND_COMPLIANCE", ["headline"], { allowed_fonts: ["Brand Sans"] }),
    ];
    const batch = validateBatch(document(), rules, [
      { operation_id: "move-head", type: "MOVE_NODE", target_ids: ["headline"], payload: { x: 740, y: 100 } },
      { operation_id: "move-logo", type: "MOVE_NODE", target_ids: ["logo"], payload: { x: 120, y: 50 } },
    ]);
    expect(batch.metrics.blocking_count).toBeGreaterThanOrEqual(2);
    const fixes = proposeFixOperations(validateConstraints(document(), rules).violations, 7);
    expect(fixes.some((item) => item.payload.property === "font_size")).toBe(true);
    expect(fixes.some((item) => item.reason !== "constraint-validator-safe-autofix")).toBe(false);
    const fontFix = fixes.find((item) => item.payload.property === "font_size")!;
    expect(validateProposedFix(document(), rules, fontFix).violations.some((item) => item.validator === "FontSizeValidator")).toBe(false);
  });

  it("stable violation ids are deterministic", () => {
    const first = stableViolationId("constraint", "BoundsValidator", ["b", "a"], "BOUNDS");
    const second = stableViolationId("constraint", "BoundsValidator", ["a", "b"], "BOUNDS");
    expect(first).toBe(second);
    expect(first).toMatch(/^cv1-[0-9a-f]{16}$/);
  });
});
