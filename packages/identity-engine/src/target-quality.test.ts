import { describe, expect, it } from "vitest";
import { StructuredIdentitySignalProvider } from "./provider";
import { IdentityValidationRuntime } from "./runtime";
import type { IdentityReferenceSet, ThresholdCalibrationProfile, VerifiedIdentityAsset } from "./types";

const H = "a".repeat(64);
const profile: ThresholdCalibrationProfile = {
  profile_id: "product-strict",
  organization_id: "org-1",
  identity_type: "PRODUCT",
  scenario: "STRICT_PRESERVE",
  version: "1",
  status: "PUBLISHED",
  threshold: 90,
  review_floor: 80,
  minimum_confidence: 0.8,
  signal_weights: { multimodal: 0.5, shape: 0.5 },
  required_signals: ["multimodal", "shape"],
  model_bundle_version: "fixture@1",
  preprocessor_version: "prep@1",
  calibration_dataset_version: "cal@1",
  metrics: {
    threshold: 90,
    precision: 1,
    recall: 1,
    f1: 1,
    false_positive_rate: 0,
    false_negative_rate: 0,
    roc_auc: 1,
    average_precision: 1,
    positive_count: 3,
    negative_count: 2,
    near_miss_count: 2,
  },
};
const identity: IdentityReferenceSet = {
  identity_id: "product-1",
  organization_id: "org-1",
  type: "PRODUCT",
  canonical_asset_ids: ["asset-1"],
  reference_views: [{ view_id: "front", asset_id: "asset-1", asset_version: "v1", organization_id: "org-1" }],
  threshold_profile_id: profile.profile_id,
  threshold_profile_version: profile.version,
  version: "ref@1",
  status: "PUBLISHED",
};
const reference: VerifiedIdentityAsset = {
  asset_id: "asset-1",
  asset_version: "v1",
  organization_id: "org-1",
  state: "READY",
  checksum_sha256: H,
  mime_type: "image/png",
  rights: "USER_OWNED",
};
const provider = new StructuredIdentitySignalProvider("fixture", "fixture@1", "prep@1");

describe("NODE-44 target and evidence quality", () => {
  it("fails closed when no IR bounds or detector target evidence exists", async () => {
    const runtime = new IdentityValidationRuntime(provider);
    await expect(runtime.validate({
      identity,
      profile,
      references: [reference],
      candidate: {
        organization_id: "org-1",
        artifact: { artifact_id: "a", version: "1", metadata: { checksum_sha256: H } },
        metadata: { identity_signal_scores: { multimodal: 96, shape: 95 } },
      },
      severity: "HARD",
      scenario: "STRICT_PRESERVE",
    })).rejects.toThrow("IDENTITY_TARGET_REGION_UNAVAILABLE");
  });

  it("sends a low-quality crop to REVIEW even when raw similarity is high", async () => {
    const runtime = new IdentityValidationRuntime(provider);
    const report = await runtime.validate({
      identity,
      profile,
      references: [reference],
      candidate: {
        organization_id: "org-1",
        artifact: { artifact_id: "a", version: "1", metadata: { checksum_sha256: H } },
        target_region: { x: 0, y: 0, width: 100, height: 100, coordinate_space: "PIXELS" },
        metadata: {
          identity_signal_scores: {
            multimodal: { score: 96, confidence: 0.55, evidence_ref: "crop:low-quality" },
            shape: { score: 95, confidence: 0.6, evidence_ref: "crop:low-quality" },
          },
        },
      },
      severity: "HARD",
      scenario: "STRICT_PRESERVE",
    });
    expect(report.status).toBe("REVIEW");
    expect(report.reason_code).toBe("IDENTITY_CONFIDENCE_BELOW_MINIMUM");
  });
});
