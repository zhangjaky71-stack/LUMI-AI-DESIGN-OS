import { describe, expect, it } from "vitest";
import { StructuredIdentitySignalProvider } from "./provider";
import { IdentityValidationRuntime } from "./runtime";
import type { IdentityReferenceSet, ThresholdCalibrationProfile, VerifiedIdentityAsset } from "./types";

const profile: ThresholdCalibrationProfile = {
  profile_id: "product-profile",
  organization_id: "org-1",
  identity_type: "PRODUCT",
  scenario: "STRICT_PRESERVE",
  version: "3",
  status: "PUBLISHED",
  threshold: 90,
  review_floor: 80,
  minimum_confidence: 0.7,
  signal_weights: { multimodal: 0.5, shape: 0.5 },
  required_signals: ["multimodal", "shape"],
  model_bundle_version: "model@3",
  preprocessor_version: "prep@2",
  calibration_dataset_version: "cal@3",
  metrics: { threshold: 90, precision: 1, recall: 1, f1: 1, false_positive_rate: 0, false_negative_rate: 0, roc_auc: 1, average_precision: 1, positive_count: 1, negative_count: 1, near_miss_count: 1 },
};
const identity: IdentityReferenceSet = {
  identity_id: "product-1",
  organization_id: "org-1",
  type: "PRODUCT",
  canonical_asset_ids: ["asset-1"],
  reference_views: [{ view_id: "front", asset_id: "asset-1", asset_version: "v1", organization_id: "org-1" }],
  threshold_profile_id: profile.profile_id,
  threshold_profile_version: profile.version,
  version: "ref@2",
  status: "PUBLISHED",
};
const asset: VerifiedIdentityAsset = {
  asset_id: "asset-1",
  asset_version: "v1",
  organization_id: "org-1",
  state: "READY",
  checksum_sha256: "1".repeat(64),
  mime_type: "image/png",
  rights: "USER_OWNED",
};
const candidate = {
  organization_id: "org-1",
  artifact: { artifact_id: "artifact", version: "1" },
  target_region: { x: 0, y: 0, width: 1, height: 1, coordinate_space: "NORMALIZED" as const },
  metadata: { identity_signal_scores: { multimodal: 98, shape: 97 } },
};

describe("NODE-44 authoritative version pinning", () => {
  it("rejects a reference set pointing at another threshold profile version", async () => {
    const runtime = new IdentityValidationRuntime(new StructuredIdentitySignalProvider("fixture", "model@3", "prep@2"));
    await expect(runtime.validate({ identity: { ...identity, threshold_profile_version: "2" }, profile, references: [asset], candidate, severity: "HARD", scenario: "STRICT_PRESERVE" })).rejects.toThrow("IDENTITY_PROFILE_VERSION_MISMATCH");
  });

  it("rejects a model upgrade until a newly calibrated profile pins it", async () => {
    const runtime = new IdentityValidationRuntime(new StructuredIdentitySignalProvider("fixture", "model@4", "prep@2"));
    await expect(runtime.validate({ identity, profile, references: [asset], candidate, severity: "HARD", scenario: "STRICT_PRESERVE" })).rejects.toThrow("IDENTITY_PROVIDER_VERSION_MISMATCH");
  });

  it("rejects a preprocessor upgrade until the profile is recalibrated", async () => {
    const runtime = new IdentityValidationRuntime(new StructuredIdentitySignalProvider("fixture", "model@3", "prep@3"));
    await expect(runtime.validate({ identity, profile, references: [asset], candidate, severity: "HARD", scenario: "STRICT_PRESERVE" })).rejects.toThrow("IDENTITY_PREPROCESSOR_VERSION_MISMATCH");
  });
});
