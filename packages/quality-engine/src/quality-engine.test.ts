import { describe, expect, it } from "vitest";
import type { BrandComplianceReport } from "../../brand-rules/src/index";
import type { PostflightReport } from "../../design-constraints/src/index";
import type { DesignDocument } from "../../design-ir/src/index";
import type { IdentityValidationReport } from "../../identity-engine/src/index";
import { QualityEngine } from "./engine";
import type { QualityEnginePorts, VisualGraderPort } from "./ports";
import type { CriticSubject, HumanCalibrationSummary, QualityDimension, QualityProfile, VisualGradeResult } from "./types";

const NOW = "2026-08-15T00:00:00.000Z";

function document(overrides: Partial<DesignDocument> = {}): DesignDocument {
  return {
    schema_version: "1.0",
    document_id: "doc-1",
    unit: "px",
    root_id: "root",
    nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: ["title"], transform: { x: 0, y: 0, width: 400, height: 300 } },
      title: { id: "title", kind: "TEXT", parent_id: "frame", children: [], content: "Hello", transform: { x: 20, y: 20, width: 160, height: 40 }, metadata: { measured_width: 150, measured_height: 36, foreground_color: "#111111", background_color: "#ffffff" } },
    },
    resources: {},
    metadata: { document_version: 7 },
    ...overrides,
  };
}

function subject(overrides: Partial<CriticSubject> = {}): CriticSubject {
  return {
    organization_id: "00000000-0000-4000-8000-000000000001",
    project_id: "00000000-0000-4000-8000-000000000002",
    artifact_id: "00000000-0000-4000-8000-000000000003",
    artifact_version_id: "00000000-0000-4000-8000-000000000004",
    design_document_version_id: "00000000-0000-4000-8000-000000000005",
    design_document: document(),
    rendered_asset_ref: "artifact-file:preview",
    width: 1200,
    height: 900,
    ...overrides,
  };
}

function profile(dimension: QualityDimension, options: { threshold?: number; hard_gate?: boolean; minimum_confidence?: number } = {}): QualityProfile {
  return {
    profile_id: `test:${dimension}`,
    version: "1.0.0",
    name: "production-web",
    overall_pass_threshold: options.threshold ?? 80,
    overall_warning_threshold: Math.max(0, (options.threshold ?? 80) - 5),
    review_confidence_threshold: options.minimum_confidence ?? 0.7,
    dimensions: [{ dimension, weight: 1, threshold: options.threshold ?? 80, hard_gate: options.hard_gate ?? false, minimum_confidence: options.minimum_confidence ?? 0.7 }],
  };
}

const calibration: HumanCalibrationSummary = {
  grader_id: "critic-vlm",
  grader_version: "2.1.0",
  dataset_version: "human-pairs-2026-08",
  sample_count: 120,
  precision: 0.9,
  recall: 0.86,
  f1: 0.88,
  false_positive_rate: 0.05,
  false_negative_rate: 0.09,
  inter_rater_agreement: 0.78,
  approved: true,
};

function visualGrade(score = 95, confidence = 0.95, dataset = calibration.dataset_version): VisualGradeResult {
  return {
    grader_id: calibration.grader_id,
    grader_version: calibration.grader_version,
    model_provider: "mock-gateway",
    model_name: "critic-model",
    model_version: "2026-08-01",
    calibration_dataset_version: dataset,
    prompt_version: "critic-prompt-v3",
    dimensions: [{ dimension: "COMPOSITION", score, confidence, reason_codes: score < 80 ? ["WEAK_COMPOSITION"] : [] }],
    strengths: score >= 80 ? ["clear focal hierarchy"] : [],
  };
}

function visualPort(grade: () => Promise<VisualGradeResult>): VisualGraderPort {
  return { grader_id: calibration.grader_id, grader_version: calibration.grader_version, role_id: "visual-critic", grade };
}

function engine(ports: QualityEnginePorts, options: { calibrations?: readonly HumanCalibrationSummary[]; timeout?: number } = {}): QualityEngine {
  return new QualityEngine({ ports, calibrations: options.calibrations ?? [calibration], visual_timeout_ms: options.timeout ?? 25, now: () => NOW });
}

function constraintPass(): PostflightReport {
  return { decision: "PASS", violations: [], unavailable_validators: [] };
}

function identityReport(status: IdentityValidationReport["status"], severity: IdentityValidationReport["severity"], score: number | null, confidence = 0.98): IdentityValidationReport {
  return {
    report_id: "identity-report-1",
    organization_id: subject().organization_id,
    identity_id: "product-1",
    identity_type: "PRODUCT",
    severity,
    scenario: "STRICT_PRESERVE",
    status,
    identity_score: score,
    confidence,
    threshold: 90,
    review_floor: 80,
    signal_scores: [],
    reference_set_version: "3",
    threshold_profile_id: "product-strict",
    threshold_profile_version: "4",
    calibration_dataset_version: "identity-human-v4",
    provider_id: "identity-provider",
    provider_version: "5",
    preprocessor_version: "2",
    evidence_refs: [],
    ...(status === "FAIL" ? { reason_code: "WRONG_SKU" } : {}),
    identity_validation_snapshot_id: "identity-validation:abc",
  };
}

describe("NODE-50 Visual Critic hard gates", () => {
  it("does not let a high aesthetic score hide a hard QR failure", async () => {
    const result = await engine({
      constraints: { async evaluate() { return constraintPass(); } },
      qr: { async evaluate() { return { provider_id: "qr-decoder", provider_version: "1", status: "FAIL", confidence: 1, detected: true, payload_matches: false, readable_at_target_size: false }; } },
      visual: visualPort(async () => visualGrade(99, 0.99)),
    }).evaluate({ subject: subject(), profile: profile("QR_READABILITY", { threshold: 100, hard_gate: true, minimum_confidence: 0.95 }) });
    expect(result.status).toBe("FAIL_HARD");
    expect(result.overall_score).toBe(0);
    expect(result.violations.some((item) => item.reason_code === "QR_READABILITY_FAILED")).toBe(true);
  });

  it("propagates a hard brand font failure and preserves a typed repair operation", async () => {
    const brand: BrandComplianceReport = {
      brand_rule_set_version: "brand-v7",
      decision: "FAIL",
      score: 42,
      hard_violation_count: 1,
      soft_violation_count: 0,
      advisory_count: 0,
      diagnostics: [{
        rule_id: "font-allowlist",
        severity: "HARD",
        category: "TYPOGRAPHY",
        reason_code: "FONT_ASSET_NOT_ALLOWED",
        node_id: "title",
        repair_operations: [{ operation_id: "brand-fix-font", type: "APPLY_STYLE", target_ids: ["title"], expected_document_version: 7, payload: { style_ref: "approved-font-style" }, reason: "Use approved brand font" }],
      }],
    };
    const result = await engine({ brand: { async evaluate() { return brand; } } }).evaluate({ subject: subject(), profile: profile("BRAND_CONSISTENCY", { hard_gate: true, threshold: 100, minimum_confidence: 0.95 }) });
    expect(result.status).toBe("FAIL_HARD");
    expect(result.repair_actions).toHaveLength(1);
    expect(result.repair_actions[0]?.type).toBe("APPLY_STYLE");
  });

  it("gives product identity precedence over aesthetics", async () => {
    const result = await engine({ identity: { async evaluate() { return [identityReport("FAIL", "HARD", 35)]; } }, visual: visualPort(async () => visualGrade(100, 1)) }).evaluate({ subject: subject(), profile: profile("IDENTITY_CONSISTENCY", { hard_gate: true, threshold: 100, minimum_confidence: 0.95 }) });
    expect(result.status).toBe("FAIL_HARD");
    expect(result.violations[0]?.reason_code).toBe("WRONG_SKU");
  });

  it("fails hard on deterministic export resolution before subjective grading", async () => {
    const result = await engine({ visual: visualPort(async () => visualGrade(100, 1)) }).evaluate({ subject: subject({ width: 640, height: 480, metadata: { minimum_export_width: 1200, minimum_export_height: 900 } }), profile: profile("RESOLUTION_EXPORT_READINESS", { hard_gate: true, threshold: 100, minimum_confidence: 0.95 }) });
    expect(result.status).toBe("FAIL_HARD");
    expect(result.evidence[0]?.kind).toBe("DETERMINISTIC");
  });
});

describe("NODE-50 repair and review policy", () => {
  it("turns known typography overflow into DesignOperation repair actions without executing them", async () => {
    const d = document({ nodes: {
      root: { id: "root", kind: "DOCUMENT_ROOT", parent_id: null, children: ["frame"] },
      frame: { id: "frame", kind: "FRAME", parent_id: "root", children: ["title"], transform: { x: 0, y: 0, width: 400, height: 300 } },
      title: { id: "title", kind: "TEXT", parent_id: "frame", children: [], content: "Long title", transform: { x: 20, y: 20, width: 80, height: 20 }, metadata: { measured_width: 180, measured_height: 40 } },
    } });
    const result = await engine({}).evaluate({ subject: subject({ design_document: d }), profile: profile("TYPOGRAPHY_READABILITY", { threshold: 90 }) });
    expect(result.status).toBe("FAIL_REPAIRABLE");
    expect(result.repair_actions).toEqual([expect.objectContaining({ type: "RESIZE_NODE", target_ids: ["title"], expected_document_version: 7 })]);
    expect(d.nodes.title?.transform?.width).toBe(80);
  });

  it("routes visual grader timeout to human review instead of false PASS", async () => {
    const never = new Promise<VisualGradeResult>(() => undefined);
    const result = await engine({ visual: visualPort(async () => never) }, { timeout: 1 }).evaluate({ subject: subject(), profile: profile("COMPOSITION", { threshold: 80, minimum_confidence: 0.8 }) });
    expect(result.status).toBe("REVIEW_REQUIRED");
    expect(result.unavailable_graders).toContain("visual-grader");
  });

  it("routes low-confidence high-impact visual evidence to review", async () => {
    const result = await engine({ visual: visualPort(async () => visualGrade(98, 0.25)) }).evaluate({ subject: subject(), profile: profile("COMPOSITION", { hard_gate: true, threshold: 80, minimum_confidence: 0.8 }) });
    expect(result.status).toBe("REVIEW_REQUIRED");
    expect(result.dimensions[0]?.score).toBe(98);
    expect(result.dimensions[0]?.passed).toBe(false);
  });

  it("invalidates a grader when its calibration dataset version changes", async () => {
    const result = await engine({ visual: visualPort(async () => visualGrade(95, 0.95, "new-unreviewed-dataset")) }).evaluate({ subject: subject(), profile: profile("COMPOSITION") });
    expect(result.status).toBe("REVIEW_REQUIRED");
    expect(result.unavailable_graders).toContain("visual-grader");
  });

  it("prevents the same model and prompt from self-approving generation", async () => {
    const result = await engine({ visual: visualPort(async () => visualGrade()) }).evaluate({
      subject: subject(),
      profile: profile("COMPOSITION"),
      generation_context: { model_ref: "mock-gateway/critic-model@2026-08-01", prompt_version: "critic-prompt-v3" },
    });
    expect(result.status).toBe("REVIEW_REQUIRED");
    expect(result.unavailable_graders).toContain("visual-grader:not-isolated");
  });

  it("never treats unavailable hard constraint evidence as PASS", async () => {
    const result = await engine({ constraints: { async evaluate() { throw new Error("down"); } } }).evaluate({ subject: subject(), profile: profile("CONSTRAINT_COMPLIANCE", { hard_gate: true, threshold: 100, minimum_confidence: 0.95 }) });
    expect(result.status).toBe("REVIEW_REQUIRED");
    expect(result.unavailable_graders).toContain("constraint-runtime");
  });
});
