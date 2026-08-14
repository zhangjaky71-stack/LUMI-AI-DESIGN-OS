import { describe, expect, it } from "vitest";
import { artifactManifestSha256, buildArtifactExportManifest } from "../../artifact-sdk/src/index";
import type { ArtifactFile, ArtifactProvenance, ArtifactVersion } from "../../artifact-sdk/src/types";
import { evaluateIdentityArtifactApproval } from "./artifact-gate";
import type { IdentityValidationReport } from "./types";

const H = "a".repeat(64);
const C = "b".repeat(64);
const GIT = "c".repeat(40);

function version(snapshot?: string): ArtifactVersion {
  return {
    id: "v1",
    organization_id: "org-1",
    artifact_id: "a1",
    branch_id: "main",
    parent_version_id: null,
    schema_version: "1.0",
    version_number: 1,
    status: "READY",
    content_hash: H,
    constraint_snapshot_hash: C,
    created_by_type: "AGENT",
    created_by_id: "identity-agent",
    created_at: "2026-08-14T10:00:00Z",
    ...(snapshot ? { identity_validation_snapshot_id: snapshot } : {}),
  };
}
function provenance(snapshot?: string): ArtifactProvenance {
  return {
    artifact_version_id: "v1",
    organization_id: "org-1",
    constraint_snapshot_hash: C,
    code_git_sha: GIT,
    ...(snapshot ? { identity_validation_snapshot_id: snapshot } : {}),
  };
}
const file: ArtifactFile = {
  id: "f1",
  organization_id: "org-1",
  artifact_version_id: "v1",
  role: "PREVIEW",
  storage_key: "org/org-1/a1/v1.png",
  mime_type: "image/png",
  size_bytes: 100,
  checksum_sha256: H,
};
function report(status: "PASS" | "FAIL" | "REVIEW" = "PASS"): IdentityValidationReport {
  return {
    report_id: "r1",
    organization_id: "org-1",
    identity_id: "product-1",
    identity_type: "PRODUCT",
    severity: "HARD",
    scenario: "STRICT_PRESERVE",
    status,
    identity_score: status === "PASS" ? 96 : 70,
    confidence: 0.95,
    threshold: 90,
    review_floor: 80,
    signal_scores: [],
    reference_set_version: "ref@1",
    threshold_profile_id: "strict",
    threshold_profile_version: "1",
    calibration_dataset_version: "cal@1",
    provider_id: "provider",
    provider_version: "model@1",
    preprocessor_version: "prep@1",
    evidence_refs: [{ kind: "CALIBRATION", ref: "cal@1" }],
    ...(status === "PASS" ? {} : { reason_code: status === "REVIEW" ? "IDENTITY_REVIEW_REQUIRED" : "IDENTITY_SCORE_BELOW_THRESHOLD" }),
    identity_validation_snapshot_id: "identity-validation:single",
  };
}

describe("NODE-44 Artifact identity provenance", () => {
  it("keeps the legacy stable manifest hash unchanged when identity validation is absent", async () => {
    const before = await artifactManifestSha256(version(), provenance(), [file]);
    const after = await artifactManifestSha256({ ...version(), identity_validation_snapshot_id: null }, provenance(), [file]);
    expect(after).toBe(before);
  });

  it("changes the canonical manifest hash when an identity snapshot is pinned", async () => {
    const legacy = await artifactManifestSha256(version(), provenance(), [file]);
    const pinned = await artifactManifestSha256(version("identity-batch:one"), provenance("identity-batch:one"), [file]);
    expect(pinned).not.toBe(legacy);
    const manifest = await buildArtifactExportManifest(version("identity-batch:one"), provenance("identity-batch:one"), [file]);
    expect(manifest.identity_validation_snapshot_id).toBe("identity-batch:one");
  });

  it("rejects version/provenance snapshot disagreement", async () => {
    await expect(artifactManifestSha256(version("identity-batch:one"), provenance("identity-batch:two"), [file])).rejects.toThrow("identity validation snapshot mismatch");
  });

  it("requires the exact batch snapshot and all HARD identity reports to pass approval", () => {
    expect(evaluateIdentityArtifactApproval(
      version("identity-batch:one"),
      provenance("identity-batch:one"),
      [report("PASS")],
      "identity-batch:one",
    ).allowed).toBe(true);
    expect(evaluateIdentityArtifactApproval(
      version("identity-batch:one"),
      provenance("identity-batch:one"),
      [report("FAIL")],
      "identity-batch:one",
    ).reason_codes).toContain("IDENTITY_HARD_VIOLATION");
    expect(evaluateIdentityArtifactApproval(
      version("identity-batch:one"),
      provenance("identity-batch:one"),
      [report("REVIEW")],
      "identity-batch:one",
    ).reason_codes).toContain("IDENTITY_MANUAL_REVIEW_REQUIRED");
    expect(evaluateIdentityArtifactApproval(
      version("identity-batch:one"),
      provenance("identity-batch:one"),
      [report("PASS")],
      "identity-batch:two",
    ).reason_codes).toContain("IDENTITY_SNAPSHOT_VERSION_MISMATCH");
  });
});
