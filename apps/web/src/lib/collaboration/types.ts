export type ThreadStatus = "OPEN" | "RESOLVED";

export type CollaborationComment = {
  id: string;
  organizationId: string;
  threadId: string;
  body: string;
  mentionUserIds: readonly string[];
  createdBy: string;
  revision: number;
  createdAt: string;
  editedAt: string | null;
  deletedAt: string | null;
};

export type CommentThread = {
  id: string;
  organizationId: string;
  projectId: string;
  artifactId: string;
  artifactVersionId: string;
  designNodeId: string | null;
  x: number | null;
  y: number | null;
  status: ThreadStatus;
  needsReanchor: boolean;
  createdBy: string;
  createdAt: string;
  resolvedBy: string | null;
  resolvedAt: string | null;
};

export type CommentThreadBundle = {
  thread: CommentThread;
  comments: readonly CollaborationComment[];
};

export function parseCommentThreadBundles(value: unknown): readonly CommentThreadBundle[] {
  return array(value, "COLLABORATION_THREADS_INVALID").map((entry) => {
    const record = object(entry, "COLLABORATION_THREAD_BUNDLE_INVALID");
    return {
      thread: parseThread(record.thread),
      comments: array(record.comments, "COLLABORATION_COMMENTS_INVALID").map(parseComment),
    };
  });
}

export function parseComment(value: unknown): CollaborationComment {
  const record = object(value, "COLLABORATION_COMMENT_INVALID");
  return {
    id: requiredString(record.id, "COLLABORATION_COMMENT_ID_REQUIRED"),
    organizationId: requiredString(record.organization_id ?? record.organizationId, "COLLABORATION_COMMENT_ORG_REQUIRED"),
    threadId: requiredString(record.thread_id ?? record.threadId, "COLLABORATION_COMMENT_THREAD_REQUIRED"),
    body: requiredString(record.body, "COLLABORATION_COMMENT_BODY_REQUIRED"),
    mentionUserIds: stringArray(record.mention_user_ids ?? record.mentionUserIds ?? [], "COLLABORATION_COMMENT_MENTIONS_INVALID"),
    createdBy: requiredString(record.created_by ?? record.createdBy, "COLLABORATION_COMMENT_CREATOR_REQUIRED"),
    revision: integer(record.revision, "COLLABORATION_COMMENT_REVISION_INVALID", 1),
    createdAt: requiredString(record.created_at ?? record.createdAt, "COLLABORATION_COMMENT_CREATED_REQUIRED"),
    editedAt: nullableString(record.edited_at ?? record.editedAt),
    deletedAt: nullableString(record.deleted_at ?? record.deletedAt),
  };
}

export function parseThread(value: unknown): CommentThread {
  const record = object(value, "COLLABORATION_THREAD_INVALID");
  return {
    id: requiredString(record.id, "COLLABORATION_THREAD_ID_REQUIRED"),
    organizationId: requiredString(record.organization_id ?? record.organizationId, "COLLABORATION_THREAD_ORG_REQUIRED"),
    projectId: requiredString(record.project_id ?? record.projectId, "COLLABORATION_THREAD_PROJECT_REQUIRED"),
    artifactId: requiredString(record.artifact_id ?? record.artifactId, "COLLABORATION_THREAD_ARTIFACT_REQUIRED"),
    artifactVersionId: requiredString(record.artifact_version_id ?? record.artifactVersionId, "COLLABORATION_THREAD_VERSION_REQUIRED"),
    designNodeId: nullableString(record.design_node_id ?? record.designNodeId),
    x: nullableNumber(record.x),
    y: nullableNumber(record.y),
    status: enumValue(record.status, ["OPEN", "RESOLVED"] as const, "COLLABORATION_THREAD_STATUS_INVALID"),
    needsReanchor: booleanValue(record.needs_reanchor ?? record.needsReanchor, "COLLABORATION_REANCHOR_FLAG_REQUIRED"),
    createdBy: requiredString(record.created_by ?? record.createdBy, "COLLABORATION_THREAD_CREATOR_REQUIRED"),
    createdAt: requiredString(record.created_at ?? record.createdAt, "COLLABORATION_THREAD_CREATED_REQUIRED"),
    resolvedBy: nullableString(record.resolved_by ?? record.resolvedBy),
    resolvedAt: nullableString(record.resolved_at ?? record.resolvedAt),
  };
}

function object(value: unknown, code: string): Record<string, unknown> { if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code); return value as Record<string, unknown>; }
function array(value: unknown, code: string): unknown[] { if (!Array.isArray(value)) throw new Error(code); return value; }
function requiredString(value: unknown, code: string): string { if (typeof value !== "string" || !value.trim()) throw new Error(code); return value; }
function nullableString(value: unknown): string | null { if (value === undefined || value === null) return null; if (typeof value !== "string") throw new Error("COLLABORATION_OPTIONAL_STRING_INVALID"); return value; }
function stringArray(value: unknown, code: string): string[] { const items = array(value, code); if (!items.every((item) => typeof item === "string")) throw new Error(code); return items as string[]; }
function integer(value: unknown, code: string, min: number): number { if (!Number.isInteger(value) || (value as number) < min) throw new Error(code); return value as number; }
function nullableNumber(value: unknown): number | null { if (value === undefined || value === null) return null; if (typeof value !== "number" || !Number.isFinite(value)) throw new Error("COLLABORATION_NUMBER_INVALID"); return value; }
function booleanValue(value: unknown, code: string): boolean { if (typeof value !== "boolean") throw new Error(code); return value; }
function enumValue<const T extends readonly string[]>(value: unknown, allowed: T, code: string): T[number] { if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) throw new Error(code); return value as T[number]; }
