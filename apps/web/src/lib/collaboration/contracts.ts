import { LumiApiError } from "@/lib/app-shell/api-client";
import type {
  CollaborationActorSummary,
  CollaborationCommentAnchor,
  CollaborationOperation,
  CollaborationRole,
  CollaborationThread,
} from "./types";

const FLOATING_VERSION = /^(latest|head|current)$/i;

export function assertExactCollaborationVersion(value: string, label: string): void {
  if (!value.trim() || FLOATING_VERSION.test(value.trim())) {
    throw new Error(`COLLABORATION_${label.toUpperCase()}_MUST_BE_EXACT`);
  }
}

export function validateCommentBody(value: string): string {
  const normalized = value.trim();
  if (!normalized) throw new Error("COLLABORATION_COMMENT_EMPTY");
  if (normalized.length > 4000) throw new Error("COLLABORATION_COMMENT_TOO_LONG");
  return normalized;
}

export function validateAnchor(anchor: CollaborationCommentAnchor): CollaborationCommentAnchor {
  assertExactCollaborationVersion(anchor.artifact_version_id, "artifact_version");
  assertExactCollaborationVersion(anchor.design_document_version_id, "design_version");
  return anchor;
}

export function canComment(role: CollaborationRole): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "EDITOR" || role === "VIEWER";
}

export function canEdit(role: CollaborationRole): boolean {
  return role === "OWNER" || role === "ADMIN" || role === "EDITOR";
}

export function mentionOptions(
  current: CollaborationActorSummary,
  members: readonly CollaborationActorSummary[],
): readonly CollaborationActorSummary[] {
  return members.filter((member) => member.actor_id !== current.actor_id && member.role !== "BILLING");
}

export function anchorLabel(thread: CollaborationThread, canonicalVersionId: string): string {
  const anchor = validateAnchor(thread.anchor);
  const historical = anchor.design_document_version_id !== canonicalVersionId;
  const target = anchor.node_id ? `Node ${anchor.node_id}` : anchor.frame_id ? `Frame ${anchor.frame_id}` : "Project";
  return `${target} · ${anchor.design_document_version_id}${historical ? " · Historical" : ""}`;
}

export function operationConflictKey(operation: CollaborationOperation): string {
  return `${operation.node_id}::${operation.property_name}`;
}

export function safeCollaborationError(error: unknown): { message: string; request_id: string | null } {
  if (error instanceof LumiApiError) {
    return {
      message: safeCode(error.problem.code),
      request_id: error.problem.request_id ?? null,
    };
  }
  const code = error instanceof Error ? error.message : "COLLABORATION_REQUEST_FAILED";
  return { message: safeCode(code), request_id: null };
}

function safeCode(code: string): string {
  switch (code) {
    case "COLLABORATION_FORBIDDEN":
    case "PERMISSION_DENIED":
      return "You no longer have permission for this collaboration action.";
    case "COLLABORATION_MENTION_FORBIDDEN":
      return "That person cannot be mentioned in this project.";
    case "COLLABORATION_BASE_VERSION_NOT_FOUND":
      return "The local edit is based on an unavailable version. Reload the canonical document before retrying.";
    case "COLLABORATION_HARD_CONSTRAINT_FAILED":
      return "This edit was blocked by a protected design constraint.";
    case "COLLABORATION_CANONICAL_HEAD_CONFLICT":
      return "The document changed again. Your local edit was preserved and needs another rebase.";
    default:
      return "Collaboration could not complete the request. Use the request ID for support if one is shown.";
  }
}

export function shortAgentRun(actor: CollaborationActorSummary): string | null {
  if (actor.actor_type !== "AGENT" || !actor.agent_run_id) return null;
  return actor.agent_run_id.length > 18 ? `${actor.agent_run_id.slice(0, 18)}…` : actor.agent_run_id;
}
