import type { CollaborationBootstrap, CollaborationWorkspaceSnapshot } from "./types";

export function deterministicCollaborationWorkspace(projectId: string): CollaborationWorkspaceSnapshot {
  const owner = {
    actor_id: "user-owner",
    display_name: "Mika Chen",
    actor_type: "USER" as const,
    role: "OWNER" as const,
    agent_run_id: null,
  };
  const editor = {
    actor_id: "user-editor",
    display_name: "Noah Lee",
    actor_type: "USER" as const,
    role: "EDITOR" as const,
    agent_run_id: null,
  };
  const viewer = {
    actor_id: "user-viewer",
    display_name: "Avery Wang",
    actor_type: "USER" as const,
    role: "VIEWER" as const,
    agent_run_id: null,
  };
  const clientPersona = {
    actor_id: "user-client",
    display_name: "Client Review",
    actor_type: "USER" as const,
    role: "VIEWER" as const,
    agent_run_id: null,
  };
  const agent = {
    actor_id: "agent-lumi",
    display_name: "LUMI Agent",
    actor_type: "AGENT" as const,
    role: "EDITOR" as const,
    agent_run_id: "collaboration-e2e-agent-run-61",
  };
  return {
    organization_id: "org-lumi-design",
    project_id: projectId,
    document_id: "design-doc-summer-launch",
    canonical_version_id: "design-summer-launch-v4",
    artifact_version_id: "artifact-summer-launch-design-v4",
    current_user: owner,
    members: [owner, editor, viewer, clientPersona, agent],
    presence: [
      {
        actor: owner,
        document_id: "design-doc-summer-launch",
        selection_ids: ["hero-title"],
        active_frame_id: "frame-instagram",
        cursor: [312, 226],
        last_seen: "2026-08-15T06:30:00.000Z",
      },
      {
        actor: editor,
        document_id: "design-doc-summer-launch",
        selection_ids: ["cta"],
        active_frame_id: "frame-instagram",
        cursor: [518, 404],
        last_seen: "2026-08-15T06:30:01.000Z",
      },
    ],
    threads: [
      {
        thread_id: "thread-current-hero",
        anchor: {
          project_id: projectId,
          artifact_version_id: "artifact-summer-launch-design-v4",
          design_document_version_id: "design-summer-launch-v4",
          node_id: "hero-title",
          frame_id: "frame-instagram",
          historical: false,
        },
        status: "OPEN",
        messages: [
          {
            comment_id: "comment-current-1",
            actor: editor,
            body: "Can we make the headline feel more premium without changing the brand lockup? @LUMI",
            mention_actor_ids: ["agent-lumi"],
            created_at: "2026-08-15T06:20:00.000Z",
            edited_at: null,
            deleted_at: null,
          },
          {
            comment_id: "comment-current-2",
            actor: agent,
            body: "I can propose a text-only revision while preserving protected brand constraints.",
            mention_actor_ids: [],
            created_at: "2026-08-15T06:20:08.000Z",
            edited_at: null,
            deleted_at: null,
          },
        ],
        created_at: "2026-08-15T06:20:00.000Z",
      },
      {
        thread_id: "thread-historical-node",
        anchor: {
          project_id: projectId,
          artifact_version_id: "artifact-summer-launch-design-v2",
          design_document_version_id: "design-summer-launch-v2",
          node_id: "legacy-price-chip",
          frame_id: "frame-instagram",
          historical: true,
        },
        status: "RESOLVED",
        messages: [{
          comment_id: "comment-history-1",
          actor: viewer,
          body: "Resolved on v2. The node was later removed, but this review context remains attached to that snapshot.",
          mention_actor_ids: [],
          created_at: "2026-08-14T03:12:00.000Z",
          edited_at: null,
          deleted_at: null,
        }],
        created_at: "2026-08-14T03:12:00.000Z",
      },
    ],
    notifications: [
      {
        notification_id: "notification-mention-1",
        kind: "MENTION",
        thread_id: "thread-current-hero",
        safe_summary: "Noah Lee mentioned LUMI Agent in a review thread.",
        created_at: "2026-08-15T06:20:00.000Z",
        read: false,
      },
    ],
    realtime: {
      transport: "WEBSOCKET",
      presence_is_ephemeral: true,
      canonical_write_transport: "HTTP_DESIGN_OPERATION_API",
    },
  };
}

export function getCollaborationBootstrap(projectId: string): CollaborationBootstrap {
  if (process.env.NODE_ENV !== "production" && process.env.LUMI_COLLABORATION_E2E === "1") {
    return { mode: "DETERMINISTIC", workspace: deterministicCollaborationWorkspace(projectId) };
  }
  return { mode: "HTTP" };
}
