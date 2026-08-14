import type { ArtifactProvenance, ArtifactVersion } from "../../artifact-sdk/src/types";
import type { IdentityValidationReport } from "./types";

export interface IdentityArtifactApprovalDecision {
  readonly allowed: boolean;
  readonly reason_codes: readonly string[];
}

export function evaluateIdentityArtifactApproval(
  version: ArtifactVersion,
  provenance: ArtifactProvenance,
  reports: readonly IdentityValidationReport[],
  expectedBatchSnapshotId: string | null,
): IdentityArtifactApprovalDecision {
  const reasons = new Set<string>();
  if (version.organization_id !== provenance.organization_id) reasons.add("IDENTITY_PROVENANCE_TENANT_MISMATCH");
  if (version.id !== provenance.artifact_version_id) reasons.add("IDENTITY_PROVENANCE_ARTIFACT_MISMATCH");

  const versionSnapshot = version.identity_validation_snapshot_id ?? null;
  const provenanceSnapshot = provenance.identity_validation_snapshot_id ?? null;
  if (versionSnapshot !== provenanceSnapshot) reasons.add("IDENTITY_SNAPSHOT_PROVENANCE_MISMATCH");
  if (expectedBatchSnapshotId !== null && versionSnapshot !== expectedBatchSnapshotId) reasons.add("IDENTITY_SNAPSHOT_VERSION_MISMATCH");

  for (const report of reports) {
    if (report.organization_id !== version.organization_id) {
      reasons.add("IDENTITY_REPORT_TENANT_MISMATCH");
      continue;
    }
    if (report.severity !== "HARD") continue;
    if (report.status === "UNAVAILABLE") reasons.add("IDENTITY_VALIDATION_UNAVAILABLE");
    else if (report.status === "REVIEW") reasons.add("IDENTITY_MANUAL_REVIEW_REQUIRED");
    else if (report.status !== "PASS") reasons.add("IDENTITY_HARD_VIOLATION");
  }
  return { allowed: reasons.size === 0, reason_codes: [...reasons].sort() };
}
