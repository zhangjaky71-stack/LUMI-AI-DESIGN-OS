import { api } from "@/lib/api/client";
import {
  parseApprovalDecisionResult,
  parseApprovalList,
  parseApprovalResource,
  type ApprovalDecision,
  type ApprovalDecisionResult,
  type ApprovalResource,
} from "@/lib/approvals/types";
import { tenantHeaders } from "@/lib/workspace/api";

function writeHeaders(organizationId: string): Record<string, string> {
  return { ...tenantHeaders(organizationId), "Idempotency-Key": crypto.randomUUID() };
}

export async function listProjectApprovals(
  organizationId: string,
  projectId: string,
): Promise<readonly ApprovalResource[]> {
  const payload = await api.get<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/approvals?limit=100`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseApprovalList(payload);
}

export async function requestArtifactApproval(
  organizationId: string,
  projectId: string,
  input: { artifactVersionId: string; title: string; summary: string },
): Promise<ApprovalResource> {
  const payload = await api.post<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/approvals/artifact-version`,
    {
      artifact_version_id: input.artifactVersionId,
      title: input.title,
      summary: input.summary,
    },
    { headers: writeHeaders(organizationId) },
  );
  return parseApprovalResource(payload);
}

export async function decideApproval(
  organizationId: string,
  approvalId: string,
  input: {
    decision: ApprovalDecision;
    reason?: string | null;
    comment?: string | null;
    nodeIds?: readonly string[];
    requestedChanges?: readonly string[];
  },
): Promise<ApprovalDecisionResult> {
  const payload = await api.post<unknown>(
    `/api/v1/approvals/${encodeURIComponent(approvalId)}/decision`,
    {
      decision: input.decision,
      reason: input.reason ?? null,
      comment: input.comment ?? null,
      node_ids: [...(input.nodeIds ?? [])],
      requested_changes: [...(input.requestedChanges ?? [])],
    },
    { headers: writeHeaders(organizationId) },
  );
  return parseApprovalDecisionResult(payload);
}
