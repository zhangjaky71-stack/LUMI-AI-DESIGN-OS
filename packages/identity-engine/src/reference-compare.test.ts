import { describe, expect, it } from "vitest";
import { compareIdentityCandidates } from "./compare";
import { createIdentityReferenceSet } from "./reference-set";
import type {
  IdentityCandidate,
  IdentitySignalScore,
  ThresholdCalibrationProfile,
  VerifiedIdentityAsset,
} from "./types";

const profile: ThresholdCalibrationProfile = {
  profile_id: "logo-profile",
  organization_id: "org-1",
  identity_type: "LOGO",
  scenario: "STRICT_PRESERVE",
  version: "1",
  status: "PUBLISHED",
  threshold: 90,
  review_floor: 80,
  minimum_confidence: 0.7,
  signal_weights: { feature: 0.5, perceptual: 0.5 },
  required_signals: ["feature", "perceptual"],
  model_bundle_version: "bundle@1",
  preprocessor_version: "prep@1",
  calibration_dataset_version: "cal@1",
  metrics: { threshold: 90, precision: 1, recall: 1, f1: 1, false_positive_rate: 0, false_negative_rate: 0, roc_auc: 1, average_precision: 1, positive_count: 1, negative_count: 1, near_miss_count: 1 },
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
function candidate(id: string, org = "org-1"): IdentityCandidate {
  return {
    organization_id: org,
    artifact: { artifact_id: id, version: "1" },
    target_region: { x: 0, y: 0, width: 1, height: 1, coordinate_space: "NORMALIZED" },
  };
}

describe("NODE-44 reference and compare APIs", () => {
  it("publishes a governed reference set only when pinned READY assets/profile agree", () => {
    const result = createIdentityReferenceSet({
      identity_id: "logo-1",
      organization_id: "org-1",
      type: "LOGO",
      canonical_asset_ids: ["asset-1"],
      reference_views: [{ view_id: "front", asset_id: "asset-1", asset_version: "v1", organization_id: "org-1" }],
      threshold_profile_id: profile.profile_id,
      threshold_profile_version: profile.version,
      version: "ref@1",
      status: "PUBLISHED",
    }, [asset], profile);
    expect(result.status).toBe("PUBLISHED");
    expect(result.canonical_asset_ids).toEqual(["asset-1"]);
  });

  it("rejects unverified/missing reference asset versions", () => {
    expect(() => createIdentityReferenceSet({
      identity_id: "logo-1",
      organization_id: "org-1",
      type: "LOGO",
      canonical_asset_ids: ["asset-1"],
      reference_views: [{ view_id: "front", asset_id: "asset-1", asset_version: "v2", organization_id: "org-1" }],
      threshold_profile_id: profile.profile_id,
      threshold_profile_version: profile.version,
      version: "ref@2",
      status: "PUBLISHED",
    }, [asset], profile)).toThrow("IDENTITY_REFERENCE_ASSET_NOT_READY");
  });

  it("compares two candidates with multiple signals without inventing a threshold", async () => {
    const rows: IdentitySignalScore[] = [
      { signal: "feature", score: 96, confidence: 0.9, evidence_refs: [{ kind: "FEATURE", ref: "feature:1" }] },
      { signal: "perceptual", score: 94, confidence: 0.95, evidence_refs: [{ kind: "MODEL", ref: "perceptual:1" }] },
    ];
    const report = await compareIdentityCandidates(
      candidate("a"),
      candidate("b"),
      "LOGO",
      { provider_id: "pairwise", provider_version: "1", preprocessor_version: "1", compare: async () => rows },
      { feature: 0.5, perceptual: 0.5 },
    );
    expect(report.score).toBe(95);
    expect(report.comparison_id).toMatch(/^identity-compare:[0-9a-f]{64}$/);
  });

  it("rejects cross-tenant pairwise comparison", async () => {
    await expect(compareIdentityCandidates(
      candidate("a", "org-1"),
      candidate("b", "org-2"),
      "LOGO",
      { provider_id: "pairwise", provider_version: "1", preprocessor_version: "1", compare: async () => [] },
      { feature: 1 },
    )).rejects.toThrow("IDENTITY_COMPARE_TENANT_MISMATCH");
  });
});
