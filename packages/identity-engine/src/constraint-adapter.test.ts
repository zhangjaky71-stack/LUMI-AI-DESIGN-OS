import { describe, expect, it } from "vitest";
import { CalibratedIdentityConstraintAdapter } from "./constraint-adapter";
import type { DesignConstraint, PostflightContext } from "../../design-constraints/src/types";
import type { IdentityPostflightResolver, IdentityValidationReport } from "./types";

const context = {
  document: { root_id: "root" },
  constraints: [],
  before_ref: { artifact_id: "a", version: "1" },
  after_ref: { artifact_id: "a", version: "2" },
} as unknown as PostflightContext;

const constraint: DesignConstraint = {
  id: "identity-constraint",
  type: "REQUIRE_IDENTITY_SCORE",
  scope: { node_ids: ["product"] },
  severity: "HARD",
  source: "USER_EXPLICIT",
  priority: 100,
  parameters: {
    identity_id: "identity-product",
    reference_set_version: "ref@4",
    threshold_profile_id: "product-background",
    threshold_profile_version: "3",
  },
  active: true,
};

function report(status: "PASS" | "FAIL" | "REVIEW" | "UNAVAILABLE"): IdentityValidationReport {
  return {
    report_id: "report-1",
    organization_id: "org-1",
    identity_id: "identity-product",
    identity_type: "PRODUCT",
    severity: "HARD",
    scenario: "BACKGROUND_REPLACEMENT",
    status,
    identity_score: status === "UNAVAILABLE" ? null : status === "PASS" ? 95 : 70,
    confidence: 0.9,
    threshold: 88,
    review_floor: 76,
    signal_scores: [],
    reference_set_version: "ref@4",
    threshold_profile_id: "product-background",
    threshold_profile_version: "3",
    calibration_dataset_version: "product-cal@3",
    provider_id: "provider",
    provider_version: "model@1",
    preprocessor_version: "prep@1",
    evidence_refs: [{ kind: "CALIBRATION", ref: "product-cal@3" }],
    ...(status === "PASS" ? {} : { reason_code: status === "UNAVAILABLE" ? "IDENTITY_VALIDATION_UNAVAILABLE" : status === "REVIEW" ? "IDENTITY_REVIEW_REQUIRED" : "IDENTITY_SCORE_BELOW_THRESHOLD" }),
    identity_validation_snapshot_id: "identity-validation:abc",
  };
}

function resolver(value: IdentityValidationReport): IdentityPostflightResolver {
  return { validate: async () => value };
}

describe("NODE-44 Constraint adapter", () => {
  it("returns no violation for calibrated PASS", async () => {
    const adapter = new CalibratedIdentityConstraintAdapter(resolver(report("PASS")));
    await expect(adapter.validate(context, constraint)).resolves.toEqual([]);
  });

  it("maps FAIL/REVIEW into NODE-39 violations with profile threshold", async () => {
    const adapter = new CalibratedIdentityConstraintAdapter(resolver(report("FAIL")));
    const violations = await adapter.validate(context, constraint);
    expect(violations).toHaveLength(1);
    expect(violations[0]?.reason_code).toBe("IDENTITY_SCORE_BELOW_THRESHOLD");
    expect(violations[0]?.threshold).toBe(88);
    expect(violations[0]?.score).toBe(70);
    expect(violations[0]?.target_id).toBe("product");
  });

  it("throws on unavailable validator so NODE-39 fail-closed behavior applies", async () => {
    const adapter = new CalibratedIdentityConstraintAdapter(resolver(report("UNAVAILABLE")));
    await expect(adapter.validate(context, constraint)).rejects.toThrow("IDENTITY_VALIDATION_UNAVAILABLE");
  });

  it("refuses ad-hoc numeric thresholds in constraint parameters", async () => {
    const adapter = new CalibratedIdentityConstraintAdapter(resolver(report("PASS")));
    await expect(adapter.validate(context, { ...constraint, parameters: { ...constraint.parameters, threshold: 80 } })).rejects.toThrow("IDENTITY_NUMERIC_THRESHOLD_MUST_COME_FROM_CALIBRATION_PROFILE");
  });
});
