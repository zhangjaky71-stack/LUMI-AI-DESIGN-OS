import { describe, expect, it } from "vitest";
import { buildCalibrationProfile } from "./calibration";
import { identityCacheKey } from "./cache";
import { StructuredIdentitySignalProvider } from "./provider";
import { IdentityValidationRuntime } from "./runtime";
import type {
  CalibrationSample,
  IdentityCandidate,
  IdentityReferenceSet,
  ThresholdCalibrationProfile,
  VerifiedIdentityAsset,
} from "./types";

const H1 = "1".repeat(64);
const H2 = "2".repeat(64);

function samples(type: "LOGO" | "PRODUCT", scenario: "STRICT_PRESERVE" | "BACKGROUND_REPLACEMENT"): CalibrationSample[] {
  const rows = type === "LOGO"
    ? [["p1", "POSITIVE", 98], ["p2", "POSITIVE", 96], ["p3", "POSITIVE", 92], ["n1", "NEGATIVE", 20], ["n2", "NEGATIVE", 35], ["m1", "NEAR_MISS", 70], ["m2", "NEAR_MISS", 75]] as const
    : [["p1", "POSITIVE", 95], ["p2", "POSITIVE", 91], ["p3", "POSITIVE", 88], ["n1", "NEGATIVE", 20], ["n2", "NEGATIVE", 40], ["m1", "NEAR_MISS", 65], ["m2", "NEAR_MISS", 72]] as const;
  return rows.map(([sample_id, label, score]) => ({ sample_id, label, score, identity_type: type, scenario }));
}

function logoProfile(): ThresholdCalibrationProfile {
  return buildCalibrationProfile({
    profile_id: "logo-strict",
    organization_id: "org-1",
    identity_type: "LOGO",
    scenario: "STRICT_PRESERVE",
    version: "1",
    model_bundle_version: "fixture-model@1",
    preprocessor_version: "prep@1",
    calibration_dataset_version: "logo-cal@1",
    signal_weights: { exact_hash: 0.25, perceptual: 0.2, feature: 0.2, ocr_wordmark: 0.35 },
    required_signals: ["exact_hash", "perceptual", "feature", "ocr_wordmark"],
    review_margin: 10,
    minimum_confidence: 0.7,
    samples: samples("LOGO", "STRICT_PRESERVE"),
    objective: { minimum_precision: 0.95, minimum_recall: 0.9 },
  });
}

function productProfile(): ThresholdCalibrationProfile {
  return buildCalibrationProfile({
    profile_id: "product-background",
    organization_id: "org-1",
    identity_type: "PRODUCT",
    scenario: "BACKGROUND_REPLACEMENT",
    version: "3",
    model_bundle_version: "fixture-model@1",
    preprocessor_version: "prep@1",
    calibration_dataset_version: "product-cal@3",
    signal_weights: { multimodal: 0.35, shape: 0.25, color: 0.15, brand_region: 0.25 },
    required_signals: ["multimodal", "shape", "color", "brand_region"],
    review_margin: 12,
    minimum_confidence: 0.65,
    samples: samples("PRODUCT", "BACKGROUND_REPLACEMENT"),
  });
}

function reference(type: "LOGO" | "PRODUCT", profile: ThresholdCalibrationProfile): IdentityReferenceSet {
  return {
    identity_id: type === "LOGO" ? "identity-logo" : "identity-product",
    organization_id: "org-1",
    project_id: "project-1",
    type,
    canonical_asset_ids: ["asset-1"],
    reference_views: [{ view_id: "front", asset_id: "asset-1", asset_version: "v1", organization_id: "org-1", role: "CANONICAL", checksum_sha256: H1 }],
    threshold_profile_id: profile.profile_id,
    threshold_profile_version: profile.version,
    version: "ref@4",
    status: "PUBLISHED",
  };
}

function verifiedReference(): VerifiedIdentityAsset {
  return {
    asset_id: "asset-1",
    asset_version: "v1",
    organization_id: "org-1",
    state: "READY",
    checksum_sha256: H1,
    mime_type: "image/png",
    rights: "USER_OWNED",
    metadata: { ocr_text: "LUMI COFFEE" },
  };
}

function candidate(identity_signal_scores: Record<string, number>, checksum = H2, ocr = "LUMI COFFEE"): IdentityCandidate {
  return {
    organization_id: "org-1",
    artifact: {
      artifact_id: "artifact-1",
      version: "7",
      mime_type: "image/png",
      metadata: { checksum_sha256: checksum, ocr_text: ocr },
    },
    target_region: { x: 0.1, y: 0.1, width: 0.6, height: 0.6, coordinate_space: "NORMALIZED" },
    metadata: { identity_signal_scores },
  };
}

const provider = new StructuredIdentitySignalProvider("structured-fixture", "fixture-model@1", "prep@1");

describe("NODE-44 calibrated Identity Engine", () => {
  it("derives thresholds from positive/negative/near-miss data", () => {
    const profile = logoProfile();
    expect(profile.threshold).toBe(92);
    expect(profile.metrics.precision).toBe(1);
    expect(profile.metrics.recall).toBe(1);
    expect(profile.metrics.near_miss_count).toBe(2);
    expect(profile.metrics.roc_auc).toBe(1);
  });

  it("passes an exact logo using multiple signals and emits traceable evidence", async () => {
    const profile = logoProfile();
    const identity = reference("LOGO", profile);
    const runtime = new IdentityValidationRuntime(provider);
    const report = await runtime.validate({
      identity,
      profile,
      references: [verifiedReference()],
      candidate: candidate({ perceptual: 99, feature: 98 }, H1),
      severity: "HARD",
      scenario: "STRICT_PRESERVE",
    });
    expect(report.status).toBe("PASS");
    expect(report.identity_score).toBeGreaterThanOrEqual(profile.threshold);
    expect(report.signal_scores.map((row) => row.signal)).toEqual(["exact_hash", "feature", "ocr_wordmark", "perceptual"]);
    expect(report.identity_validation_snapshot_id).toMatch(/^identity-validation:[0-9a-f]{64}$/);
  });

  it("rejects a stretched/recolored logo near miss even when OCR remains correct", async () => {
    const profile = logoProfile();
    const runtime = new IdentityValidationRuntime(provider);
    const report = await runtime.validate({
      identity: reference("LOGO", profile),
      profile,
      references: [verifiedReference()],
      candidate: candidate({ perceptual: 60, feature: 55 }),
      severity: "HARD",
      scenario: "STRICT_PRESERVE",
    });
    expect(report.status).toBe("FAIL");
    expect(report.reason_code).toBe("IDENTITY_SCORE_BELOW_THRESHOLD");
  });

  it("passes the same product after a background change but rejects a wrong SKU", async () => {
    const profile = productProfile();
    const identity = reference("PRODUCT", profile);
    const runtime = new IdentityValidationRuntime(provider);
    const same = await runtime.validate({
      identity,
      profile,
      references: [verifiedReference()],
      candidate: candidate({ multimodal: 96, shape: 92, color: 90, brand_region: 94 }),
      severity: "HARD",
      scenario: "BACKGROUND_REPLACEMENT",
    });
    const wrong = await runtime.validate({
      identity,
      profile,
      references: [verifiedReference()],
      candidate: candidate({ multimodal: 42, shape: 38, color: 60, brand_region: 25 }),
      severity: "HARD",
      scenario: "BACKGROUND_REPLACEMENT",
    });
    expect(same.status).toBe("PASS");
    expect(wrong.status).toBe("FAIL");
  });

  it("fails closed when a required signal is unavailable", async () => {
    const profile = productProfile();
    const runtime = new IdentityValidationRuntime(provider);
    await expect(runtime.validate({
      identity: reference("PRODUCT", profile),
      profile,
      references: [verifiedReference()],
      candidate: candidate({ multimodal: 95, shape: 92, color: 90 }),
      severity: "HARD",
      scenario: "BACKGROUND_REPLACEMENT",
    })).rejects.toThrow("IDENTITY_REQUIRED_SIGNAL_UNAVAILABLE:brand_region");
  });

  it("rejects stale reference versions and cross-tenant candidates", async () => {
    const profile = productProfile();
    const identity = reference("PRODUCT", profile);
    const runtime = new IdentityValidationRuntime(provider);
    await expect(runtime.validate({
      identity,
      profile,
      references: [{ ...verifiedReference(), asset_version: "v2" }],
      candidate: candidate({ multimodal: 96, shape: 92, color: 90, brand_region: 94 }),
      severity: "HARD",
      scenario: "BACKGROUND_REPLACEMENT",
    })).rejects.toThrow("IDENTITY_REFERENCE_VERSION_MISMATCH");
    await expect(runtime.validate({
      identity,
      profile,
      references: [verifiedReference()],
      candidate: { ...candidate({ multimodal: 96, shape: 92, color: 90, brand_region: 94 }), organization_id: "org-2" },
      severity: "HARD",
      scenario: "BACKGROUND_REPLACEMENT",
    })).rejects.toThrow("IDENTITY_CANDIDATE_TENANT_MISMATCH");
  });

  it("does not enable face processing or persistent biometric indexing by default", async () => {
    const base = productProfile();
    const faceProfile: ThresholdCalibrationProfile = { ...base, profile_id: "face", identity_type: "FACE", scenario: "STRICT_PRESERVE", required_signals: ["face_similarity"] };
    const face: IdentityReferenceSet = {
      ...reference("PRODUCT", base),
      identity_id: "face-1",
      type: "FACE",
      threshold_profile_id: "face",
      face_policy: { explicit_processing_consent: true, purpose: "user requested identity preservation", retention_until: "2026-08-15T00:00:00Z", persistent_biometric_index: false },
    };
    const runtime = new IdentityValidationRuntime(provider);
    await expect(runtime.validate({ identity: face, profile: faceProfile, references: [verifiedReference()], candidate: candidate({ face_similarity: 99 }), severity: "HARD", scenario: "STRICT_PRESERVE" })).rejects.toThrow("FACE_PROCESSING_NOT_ALLOWED");
  });

  it("invalidates cache keys when calibration or provider versions change", async () => {
    const profile = productProfile();
    const identity = reference("PRODUCT", profile);
    const base = { candidate_checksum_sha256: H2, identity, profile, provider_id: provider.provider_id, provider_version: provider.provider_version, preprocessor_version: provider.preprocessor_version };
    const first = await identityCacheKey(base);
    const second = await identityCacheKey({ ...base, profile: { ...profile, version: "4" } });
    const third = await identityCacheKey({ ...base, provider_version: "fixture-model@2" });
    expect(first).not.toBe(second);
    expect(first).not.toBe(third);
  });
});
