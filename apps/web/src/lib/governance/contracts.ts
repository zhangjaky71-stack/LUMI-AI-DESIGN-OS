import { LumiApiError } from "@/lib/app-shell/api-client";
import type {
  AuditDownloadLeaseView,
  AuditExportJobView,
  GovernanceWorkspace,
  RetentionPolicyView,
} from "./types";

export const RETENTION_CLASSES = [
  "SECURITY_AUDIT",
  "BILLING",
  "CONTENT",
  "AGENT_TRACE",
  "TEMP_SANDBOX",
  "EXPORT",
  "ANALYTICS",
] as const;

export function latestRetentionPolicies(
  values: readonly RetentionPolicyView[],
): readonly RetentionPolicyView[] {
  const latest = new Map<string, RetentionPolicyView>();
  for (const item of values) {
    const prior = latest.get(item.retention_class);
    if (!prior || item.version > prior.version) latest.set(item.retention_class, item);
  }
  return RETENTION_CLASSES.map((item) => latest.get(item)).filter(
    (item): item is RetentionPolicyView => Boolean(item),
  );
}

export function auditEventLabel(action: string): string {
  return action.replaceAll("_", " ").toLowerCase();
}

export function safeGovernanceError(value: unknown): string {
  if (value instanceof LumiApiError) {
    const requestId = value.problem.request_id ? ` Request ID: ${value.problem.request_id}` : "";
    const known: Record<string, string> = {
      GOVERNANCE_FORBIDDEN: "You do not have permission for this governance operation.",
      AUDIT_TENANT_SCOPE_MISMATCH: "Audit access is limited to the active organization.",
      GOVERNANCE_TENANT_SCOPE_MISMATCH: "Governance access is limited to the active organization.",
      LEGAL_HOLD_NOT_ACTIVE: "That legal hold is no longer active.",
      DELETION_REQUEST_NOT_FOUND: "Deletion request was not found.",
      AUDIT_EXPORT_NOT_READY: "Audit export is not ready yet.",
      AUDIT_EXPORT_FORBIDDEN: "You cannot download this audit export.",
    };
    return `${known[value.problem.code] ?? "Governance request could not be completed."}${requestId}`;
  }
  if (value instanceof Error && value.name === "AbortError") return "Request cancelled.";
  return "Governance request could not be completed.";
}

export function safeAuditDownloadUrl(lease: AuditDownloadLeaseView | null): string | null {
  if (!lease) return null;
  try {
    const url = new URL(lease.signed_url);
    return url.protocol === "https:" ? lease.signed_url : null;
  } catch {
    return null;
  }
}

export function canDownload(job: AuditExportJobView): boolean {
  return job.status === "READY" && Boolean(job.file_name && job.checksum_sha256 && job.size_bytes !== null);
}

export function workspaceHasSevenRetentionClasses(workspace: GovernanceWorkspace): boolean {
  return latestRetentionPolicies(workspace.retention_policies).length === RETENTION_CLASSES.length;
}
