export type CollaborationActorType = "USER" | "AGENT";
export type CollaborationRole = "OWNER" | "ADMIN" | "EDITOR" | "VIEWER" | "BILLING";
export type CollaborationThreadStatus = "OPEN" | "RESOLVED" | "REOPENED";

export interface CollaborationActorSummary {
  readonly actor_id: string;
  readonly display_name: string;
  readonly actor_type: CollaborationActorType;
  readonly role: CollaborationRole;
  readonly agent_run_id: string | null;
}

export interface CollaborationPresence {
  readonly actor: CollaborationActorSummary;
  readonly document_id: string;
  readonly selection_ids: readonly string[];
  readonly active_frame_id: string | null;
  readonly cursor: readonly [number, number] | null;
  readonly last_seen: string;
}

export interface CollaborationCommentAnchor {
  readonly project_id: string;
  readonly artifact_version_id: string;
  readonly design_document_version_id: string;
  readonly node_id: string | null;
  readonly frame_id: string | null;
  readonly historical: boolean;
}

export interface CollaborationCommentMessage {
  readonly comment_id: string;
  readonly actor: CollaborationActorSummary;
  readonly body: string;
  readonly mention_actor_ids: readonly string[];
  readonly created_at: string;
  readonly edited_at: string | null;
  readonly deleted_at: string | null;
}

export interface CollaborationThread {
  readonly thread_id: string;
  readonly anchor: CollaborationCommentAnchor;
  readonly status: CollaborationThreadStatus;
  readonly messages: readonly CollaborationCommentMessage[];
  readonly created_at: string;
}

export interface CollaborationNotification {
  readonly notification_id: string;
  readonly kind: "MENTION" | "COMMENT_REPLY" | "APPROVAL_REQUEST" | "ARTIFACT_READY";
  readonly thread_id: string | null;
  readonly safe_summary: string;
  readonly created_at: string;
  readonly read: boolean;
}

export interface CollaborationOperation {
  readonly operation_id: string;
  readonly node_id: string;
  readonly property_name: string;
  readonly value: unknown;
}

export interface CollaborationConflict {
  readonly local_operation: CollaborationOperation;
  readonly remote_operation_id: string;
  readonly remote_actor_id: string;
  readonly remote_actor_type: CollaborationActorType;
  readonly remote_result_version_id: string;
  readonly node_id: string;
  readonly property_name: string;
}

export interface CollaborationOperationResult {
  readonly base_version_id: string;
  readonly canonical_version_before: string;
  readonly canonical_version_after: string;
  readonly accepted_operation_ids: readonly string[];
  readonly conflicts: readonly CollaborationConflict[];
  readonly rebased: boolean;
}

export interface CollaborationWorkspaceSnapshot {
  readonly organization_id: string;
  readonly project_id: string;
  readonly document_id: string;
  readonly canonical_version_id: string;
  readonly artifact_version_id: string;
  readonly current_user: CollaborationActorSummary;
  readonly members: readonly CollaborationActorSummary[];
  readonly presence: readonly CollaborationPresence[];
  readonly threads: readonly CollaborationThread[];
  readonly notifications: readonly CollaborationNotification[];
  readonly realtime: {
    readonly transport: "WEBSOCKET";
    readonly presence_is_ephemeral: true;
    readonly canonical_write_transport: "HTTP_DESIGN_OPERATION_API";
  };
}

export interface CreateCollaborationThreadInput {
  readonly body: string;
  readonly mention_actor_ids: readonly string[];
  readonly anchor: Omit<CollaborationCommentAnchor, "project_id" | "historical">;
}

export interface ReplyCollaborationThreadInput {
  readonly body: string;
  readonly mention_actor_ids: readonly string[];
}

export interface CollaborationOperationInput {
  readonly base_version_id: string;
  readonly operations: readonly CollaborationOperation[];
}

export type CollaborationRealtimeEvent =
  | { readonly type: "CONNECTED" }
  | { readonly type: "RECONNECTING" }
  | { readonly type: "OFFLINE" }
  | { readonly type: "PRESENCE_SNAPSHOT"; readonly presence: readonly CollaborationPresence[] }
  | { readonly type: "AWARENESS_UPDATE"; readonly presence: CollaborationPresence }
  | { readonly type: "WRITE_REJECTED"; readonly code: string };

export interface CollaborationBootstrap {
  readonly mode: "HTTP" | "DETERMINISTIC";
  readonly workspace?: CollaborationWorkspaceSnapshot;
}
