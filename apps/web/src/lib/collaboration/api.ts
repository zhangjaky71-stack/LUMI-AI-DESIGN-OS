import { api } from "@/lib/api/client";
import {
  parseComment,
  parseCommentThreadBundles,
  parseThread,
  type CollaborationComment,
  type CommentThread,
  type CommentThreadBundle,
  type ThreadStatus,
} from "@/lib/collaboration/types";
import { tenantHeaders } from "@/lib/workspace/api";

export async function listCommentThreads(
  organizationId: string,
  projectId: string,
  artifactId: string,
  currentArtifactVersionId: string,
  options: { includeHistory?: boolean; includeResolved?: boolean } = {},
): Promise<readonly CommentThreadBundle[]> {
  const search = new URLSearchParams({
    current_artifact_version_id: currentArtifactVersionId,
    include_history: String(options.includeHistory ?? true),
    include_resolved: String(options.includeResolved ?? true),
  });
  const payload = await api.get<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/comment-threads?${search.toString()}`,
    { headers: tenantHeaders(organizationId) },
  );
  return parseCommentThreadBundles(payload);
}

export async function createCommentThread(
  organizationId: string,
  projectId: string,
  artifactId: string,
  input: {
    artifactVersionId: string;
    designNodeId?: string | null;
    body: string;
  },
): Promise<CommentThreadBundle> {
  const payload = await api.post<unknown>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactId)}/comment-threads`,
    {
      artifact_version_id: input.artifactVersionId,
      ...(input.designNodeId ? { design_node_id: input.designNodeId } : {}),
      body: input.body,
      mention_user_ids: [],
    },
    { headers: tenantHeaders(organizationId) },
  );
  const values = parseCommentThreadBundles([payload]);
  const first = values[0];
  if (!first) throw new Error("COLLABORATION_THREAD_CREATE_INVALID");
  return first;
}

export async function addThreadComment(
  organizationId: string,
  threadId: string,
  body: string,
): Promise<CollaborationComment> {
  const payload = await api.post<unknown>(
    `/api/v1/comment-threads/${encodeURIComponent(threadId)}/comments`,
    { body, mention_user_ids: [] },
    { headers: tenantHeaders(organizationId) },
  );
  return parseComment(payload);
}

export async function setCommentThreadStatus(
  organizationId: string,
  threadId: string,
  status: ThreadStatus,
): Promise<CommentThread> {
  const payload = await api.patch<unknown>(
    `/api/v1/comment-threads/${encodeURIComponent(threadId)}/status`,
    { status },
    { headers: tenantHeaders(organizationId) },
  );
  return parseThread(payload);
}
