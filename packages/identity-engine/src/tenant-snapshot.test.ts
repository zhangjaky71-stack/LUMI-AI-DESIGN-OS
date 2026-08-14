import { describe, expect, it } from "vitest";
import { identityCacheKey } from "./cache";
import { identityValidationBatchSnapshotId } from "./runtime";
import type { IdentityReferenceSet, IdentityValidationReport, ThresholdCalibrationProfile } from "./types";

const profile: ThresholdCalibrationProfile = {
  profile_id: "p",
  organization_id: "org-a",
  identity_type: "LOGO",
  scenario: "STRICT_PRESERVE",
  version: "1",
  status: "PUBLISHED",
  threshold: 90,
  review_floor: 80,
  minimum_confidence: 0.7,
  signal_weights: { exact_hash: 0.5, feature: 0.5 },
  required_signals: ["exact_hash", "feature"],
  model_bundle_version: "m@1",
  preprocessor_version: "prep@1",
  calibration_dataset_version: "cal@1",
  metrics: { threshold: 90, precision: 1, recall: 1, f1: 1, false_positive_rate: 0, false_negative_rate: 0, roc_auc: 1, average_precision: 1, positive_count: 1, negative_count: 1, near_miss_count: 1 },
};
function identity(org: string): IdentityReferenceSet {
  return {
    identity_id: "same-logical-id",
    organization_id: org,
    type: "LOGO",
    canonical_asset_ids: ["asset"],
    reference_views: [{ view_id: "front", asset_id: "asset", asset_version: "1", organization_id: org }],
    threshold_profile_id: "p",
    threshold_profile_version: "1",
    version: "1",
    status: "PUBLISHED",
  };
}
function report(org: string): IdentityValidationReport {
  return {
    report_id: `identity-report:${"a".repeat(64)}`,
    organization_id: org,
    identity_id: "same-logical-id",
    identity_type: "LOGO",
    severity: "HARD",
    scenario: "STRICT_PRESERVE",
    status: "PASS",
    identity_score: 100,
    confidence: 1,
    threshold: 90,
    review_floor: 80,
    signal_scores: [],
    reference_set_version: "1",
    threshold_profile_id: "p",
    threshold_profile_version: "1",
    calibration_dataset_version: "cal@1",
    provider_id: "provider",
    provider_version: "m@1",
    preprocessor_version: "prep@1",
    evidence_refs: [],
    identity_validation_snapshot_id: `identity-validation:${"b".repeat(64)}`,
  };
}

describe("NODE-44 tenant-bound identity hashes", () => {
  it("produces different cache keys for different tenants with otherwise identical inputs", async () => {
    const base = { candidate_checksum_sha256: "1".repeat(64), profile, provider_id: "provider", provider_version: "m@1", preprocessor_version: "prep@1" };
    const first = await identityCacheKey({ ...base, identity: identity("org-a") });
    const second = await identityCacheKey({ ...base, identity: identity("org-b"), profile: { ...profile, organization_id: "org-b" } });
    expect(first).not.toBe(second);
  });

  it("binds aggregate batch snapshots to the tenant", async () => {
    const first = await identityValidationBatchSnapshotId([report("org-a")]);
    const second = await identityValidationBatchSnapshotId([report("org-b")]);
    expect(first).not.toBe(second);
  });
});
