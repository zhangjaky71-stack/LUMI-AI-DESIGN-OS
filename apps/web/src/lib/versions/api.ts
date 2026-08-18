import { api } from "@/lib/api/client";
import { assertPublicVersionProvenance } from "@/lib/versions/security";
import {
  type SafeVersionProvenance,
  type VersionBranch,
  type VersionCompare,
  type VersionHistory,
  type VersionHistoryItem,
  parseBranch,
  parseSafeVersionProvenance,
  parseVersionCompare,
  parseVersionHistory,
  parseVersionItem,
} from "@/lib/versions/types";
import { tenantHeaders } from "@/lib/workspace/api";

export async function getVersionHistory(
  organizationId: string,
  artifactId: string,
): Promise<VersionHistory> {
  const payload = await api.get<unknown>(
    `/api/v1/artifacts/${encodeURIComponent(artifactId)}/version-history`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseVersionHistory(payload);
}

export async function getSafeVersionProvenance(
  organizationId: string,
  versionId: string,
): Promise<SafeVersionProvenance> {
  const payload = await api.get<unknown>(
    `/api/v1/artifact-versions/${encodeURIComponent(versionId)}/provenance-safe`,
    { headers: tenantHeaders(organizationId) },
  );
  assertPublicVersionProvenance(payload);
  return parseSafeVersionProvenance(payload);
}

export async function compareVersions(
  organizationId: string,
  leftVersionId: string,
  rightVersionId: string,
): Promise<VersionCompare> {
  const payload = await api.get<unknown>(
    `/api/v1/artifact-versions/${encodeURIComponent(leftVersionId)}/compare/${encodeURIComponent(rightVersionId)}`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseVersionCompare(payload);
}

export async function forkVersionForUser(
  organizationId: string,
  sourceVersionId: string,
  name: string,
): Promise<VersionBranch> {
  const branchName = name.trim();
  if (!branchName) throw new Error("VERSION_BRANCH_NAME_REQUIRED");
  const payload = await api.post<unknown>(
    `/api/v1/artifact-versions/${encodeURIComponent(sourceVersionId)}/fork-user`,
    { name: branchName },
    { headers: tenantHeaders(organizationId) },
  );
  return parseBranch(payload);
}

export async function restoreVersionForUser(
  organizationId: string,
  sourceVersionId: string,
  targetBranchId: string,
  expectedHeadVersionId: string | null,
): Promise<VersionHistoryItem> {
  const payload = await api.post<unknown>(
    `/api/v1/artifact-versions/${encodeURIComponent(sourceVersionId)}/restore-user`,
    {
      target_branch_id: targetBranchId,
      expected_head_version_id: expectedHeadVersionId,
    },
    { headers: tenantHeaders(organizationId) },
  );
  return parseVersionItem(payload);
}
