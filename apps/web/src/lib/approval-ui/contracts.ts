import { LumiApiError } from "@/lib/app-shell/api-client";
import type { ApprovalRecord, ApprovalStatus, ApprovalWorkspace } from "./types";

const FLOATING = /^(latest|head|current)$/i;

export function assertExactApprovalSubject(record: ApprovalRecord): void {
  const version = record.subject.subject_version.trim();
  if (!version || FLOATING.test(version)) throw new Error("APPROVAL_SUBJECT_VERSION_MUST_BE_EXACT");
}

export function isPending(status: ApprovalStatus): boolean {
  return status === "PENDING";
}

export function isTerminal(status: ApprovalStatus): boolean {
  return status !== "PENDING";
}

export function pendingApprovals(workspace: ApprovalWorkspace): readonly ApprovalRecord[] {
  return workspace.approvals.filter((item) => item.status === "PENDING");
}

export function historyApprovals(workspace: ApprovalWorkspace): readonly ApprovalRecord[] {
  return workspace.approvals.filter((item) => item.status !== "PENDING");
}

export function policyLabel(record: ApprovalRecord): string {
  const policy = record.policy;
  if (policy.mode === "MIN_N") return `MIN_N · ${policy.min_approvals} approvals`;
  if (policy.mode === "ROLE_BASED_SEQUENCE") return `Sequence · ${policy.sequence_roles.join(" → ")}`;
  if (policy.mode === "ALL") return `ALL · ${policy.required_roles.join(" + ")}`;
  return "ANY_ONE";
}

export function safeApprovalError(error: unknown): { message: string; request_id: string | null } {
  if (error instanceof LumiApiError) {
    return { message: safeCode(error.problem.code), request_id: error.problem.request_id ?? null };
  }
  return { message: safeCode(error instanceof Error ? error.message : "APPROVAL_REQUEST_FAILED"), request_id: null };
}

function safeCode(code: string): string {
  switch (code) {
    case "APPROVAL_STALE":
      return "This approval is no longer actionable. The exact subject, permission, status or Agent run changed.";
    case "APPROVAL_FORBIDDEN":
    case "PERMISSION_DENIED":
      return "You do not currently have permission to decide this approval.";
    case "APPROVAL_CHANGES_FEEDBACK_REQUIRED":
      return "Add feedback before requesting changes.";
    case "APPROVAL_SEQUENCE_ROLE_REQUIRED":
      return "A different approval role must act before you in this sequence.";
    default:
      return "Approval could not complete. Use the request ID for support if one is shown.";
  }
}
