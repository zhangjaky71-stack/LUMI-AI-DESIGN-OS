import { describe, expect, it } from "vitest";
import type { DesignDocument, DesignOperation } from "../../design-ir/src/index";
import {
  StructuredContrastEvaluator,
  buildConstraintSnapshot,
  contrastRatio,
  guardedExecute,
  hashConstraintSnapshot,
  type DesignConstraint,
} from "../src/index";

function document(): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-quality",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: {
        id: "frame",
        kind: "FRAME",
        parent_id: "root",
        children: ["logo"],
        transform: { x: 0, y: 0, width: 1000, height: 1000 },
      },
      logo: {
        id: "logo",
        kind: "IMAGE",
        parent_id: "frame",
        children: [],
        transform: { x: 100, y: 100, width: 200, height: 200 },
      },
    },
    resources: {},
    metadata: { document_version: 1 },
  };
}

function safeArea(): DesignConstraint {
  return {
    id: "safe",
    type: "SAFE_AREA",
    scope: {
      node_ids: ["logo"],
      frame_id: "frame",
      region: { x: 0.05, y: 0.05, width: 0.9, height: 0.9 },
    },
    severity: "HARD",
    source: "APPROVED_BRAND_RULE",
    priority: 500,
    parameters: {},
    active: true,
    document_version: 1,
  };
}

describe("NODE-39 quality helpers", () => {
  it("interprets SAFE_AREA as normalized frame coordinates", () => {
    const move: DesignOperation = {
      operation_id: "move-logo",
      type: "MOVE_NODE",
      target_ids: ["logo"],
      expected_document_version: 1,
      payload: { x: 10, y: 10 },
    };
    const result = guardedExecute(document(), [move], [safeArea()]);
    expect(result.preflight.decision).toBe("DENY");
    expect(result.preflight.violations[0]?.reason_code).toBe("CONSTRAINT_OUTSIDE_SAFE_AREA");
  });

  it("computes deterministic structured contrast ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 6);
  });

  it("uses the configured contrast profile threshold", async () => {
    const evaluator = new StructuredContrastEvaluator();
    const constraint: DesignConstraint = {
      id: "contrast",
      type: "REQUIRE_CONTRAST",
      scope: { node_ids: ["logo"] },
      severity: "HARD",
      source: "PROJECT_RULE",
      priority: 100,
      parameters: { foreground: "#777777", background: "#ffffff", min_ratio: 7 },
      active: true,
    };
    const violations = await evaluator.evaluate(
      {
        document: document(),
        constraints: [constraint],
        before_ref: { artifact_id: "a", version: "1" },
        after_ref: { artifact_id: "a", version: "2" },
      },
      constraint,
    );
    expect(violations[0]?.reason_code).toBe("CONTRAST_BELOW_PROFILE_THRESHOLD");
  });

  it("produces a deterministic constraint snapshot hash", async () => {
    const first = buildConstraintSnapshot(document(), [safeArea()]);
    const second = buildConstraintSnapshot(document(), [safeArea()]);
    expect(await hashConstraintSnapshot(first)).toBe(await hashConstraintSnapshot(second));
  });
});
