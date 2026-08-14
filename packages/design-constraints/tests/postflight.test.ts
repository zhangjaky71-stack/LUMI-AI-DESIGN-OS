import { describe, expect, it } from "vitest";
import type { DesignDocument } from "../../design-ir/src/index";
import {
  ConstraintPostflightRuntime,
  QrScannabilityEvaluator,
  ResolutionEvaluator,
  type DesignConstraint,
  type PostflightContext,
  type PostflightEvaluator,
  type QrDecoder,
} from "../src/index";

const doc: DesignDocument = {
  schema_version: "1.0",
  document_id: "doc",
  unit: "px",
  root_id: "root",
  nodes: { root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: [] } },
  resources: {},
  metadata: { document_version: 3 },
};

function constraint(overrides: Partial<DesignConstraint> = {}): DesignConstraint {
  return {
    id: "qr",
    type: "REQUIRE_SCANNABILITY",
    scope: { node_ids: ["qr"] },
    severity: "HARD",
    source: "USER_EXPLICIT",
    priority: 1000,
    parameters: { payload: "https://lumi.example/qr" },
    active: true,
    ...overrides,
  };
}

function context(constraints: readonly DesignConstraint[]): PostflightContext {
  return {
    document: doc,
    constraints,
    before_ref: { artifact_id: "a", version: "1", width: 750, height: 1624 },
    after_ref: { artifact_id: "a", version: "2", width: 750, height: 1624 },
  };
}

describe("NODE-39 postflight", () => {
  it("fails closed when a hard QR validator is unavailable", async () => {
    const report = await new ConstraintPostflightRuntime([]).validate(context([constraint()]));
    expect(report.decision).toBe("FAIL");
    expect(report.violations[0]?.reason_code).toBe("VALIDATION_UNAVAILABLE");
  });

  it("detects a changed QR payload", async () => {
    const decoder: QrDecoder = {
      async decode() {
        return { detected: true, payload: "https://wrong.example", quiet_zone_modules: 4, readable_at_target_size: true };
      },
    };
    const report = await new ConstraintPostflightRuntime([new QrScannabilityEvaluator(decoder)]).validate(
      context([constraint()]),
    );
    expect(report.decision).toBe("FAIL");
    expect(report.violations.some((item) => item.reason_code === "QR_PAYLOAD_CHANGED")).toBe(true);
  });

  it("passes a valid QR payload", async () => {
    const decoder: QrDecoder = {
      async decode() {
        return { detected: true, payload: "https://lumi.example/qr", quiet_zone_modules: 4, readable_at_target_size: true };
      },
    };
    const report = await new ConstraintPostflightRuntime([new QrScannabilityEvaluator(decoder)]).validate(
      context([constraint()]),
    );
    expect(report.decision).toBe("PASS");
  });

  it("fails resolution requirements deterministically", async () => {
    const resolution = constraint({
      id: "resolution",
      type: "REQUIRE_RESOLUTION",
      parameters: { min_width: 1000, min_height: 2000 },
    });
    const report = await new ConstraintPostflightRuntime([new ResolutionEvaluator()]).validate(context([resolution]));
    expect(report.decision).toBe("FAIL");
    expect(report.violations[0]?.reason_code).toBe("RESOLUTION_TOO_LOW");
  });

  it("turns a hard evaluator crash into VALIDATION_UNAVAILABLE", async () => {
    const broken: PostflightEvaluator = {
      name: "broken",
      supported_types: ["REQUIRE_SCANNABILITY"],
      supports_preflight: false,
      supports_postflight: true,
      async evaluate() {
        throw new Error("decoder timeout");
      },
    };
    const report = await new ConstraintPostflightRuntime([broken]).validate(context([constraint()]));
    expect(report.decision).toBe("FAIL");
    expect(report.unavailable_validators).toContain("broken");
  });
});
