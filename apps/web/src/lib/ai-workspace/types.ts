import type { ProjectReference } from "@/lib/projects/types";

export type AgentRunStatus =
  | "IDLE"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELED";

export type AgentTaskStatus = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED";
export type AgentTaskCategory = "AGENT" | "GENERATION" | "APPROVAL" | "ERROR";

export type WorkspaceMessageKind =
  | "USER"
  | "STATUS"
  | "ANSWER"
  | "ARTIFACT"
  | "APPROVAL"
  | "WARNING"
  | "ERROR";

export type ApprovalState =
  | "PENDING"
  | "APPROVED"
  | "REJECTED"
  | "CHANGES_REQUESTED"
  | "STALE";

export type ApprovalDecision = "APPROVE" | "REJECT" | "REQUEST_CHANGES";

export interface CanvasSelectionOption {
  readonly node_id: string;
  readonly label: string;
  readonly kind: "frame" | "text" | "image" | "shape" | "group";
  readonly locked_identity: boolean;
}

export interface CanvasDocumentSummary {
  readonly document_id: string;
  readonly version: number;
  readonly title: string;
  readonly width: number;
  readonly height: number;
  readonly selection_options: readonly CanvasSelectionOption[];
}

export interface WorkspaceBrandBinding {
  readonly brand_profile_id: string;
  readonly brand_name: string;
  readonly policy: "CURRENT_PUBLISHED" | "PINNED";
  readonly resolved_rule_set_version: string | null;
}

export interface WorkspaceArtifact {
  readonly artifact_id: string;
  readonly version_id: string;
  readonly version: number;
  readonly title: string;
  readonly media_type: string;
  readonly preview_label: string;
  readonly created_at: string;
}

export interface WorkspaceApproval {
  readonly approval_id: string;
  readonly run_id: string;
  readonly expected_run_version: number;
  readonly state: ApprovalState;
  readonly title: string;
  readonly description: string;
  readonly impact: string | null;
  readonly estimated_cost_microusd: string | null;
  readonly artifact_version_ids: readonly string[];
  readonly expires_at: string | null;
}

export interface WorkspaceMessage {
  readonly id: string;
  readonly kind: WorkspaceMessageKind;
  readonly created_at: string;
  readonly text: string;
  readonly run_id: string | null;
  readonly artifact_version_id: string | null;
  readonly approval_id: string | null;
  readonly warning_code: string | null;
}

/**
 * Safe, user-facing observability only. Raw tool args/results, prompts, secrets,
 * stack traces and private reasoning are deliberately absent from this model.
 */
export interface AgentToolSummary {
  readonly id: string;
  readonly label: string;
}

export interface AgentTaskErrorSummary {
  readonly code: string;
  readonly safe_message: string;
  readonly retrying: boolean;
  readonly request_id: string | null;
  readonly provider_fallback: string | null;
}

export interface AgentCostSummary {
  readonly estimated_microusd: string | null;
  readonly actual_microusd: string | null;
  readonly credits: string | null;
  readonly budget_warning: boolean;
}

export interface AgentTaskSummary {
  readonly task_id: string;
  readonly label: string;
  readonly status: AgentTaskStatus;
  readonly retryable: boolean;
  readonly category?: AgentTaskCategory;
  readonly safe_summary?: string | null;
  readonly started_at?: string | null;
  readonly finished_at?: string | null;
  readonly completed_units?: number | null;
  readonly total_units?: number | null;
  readonly artifact_version_ids?: readonly string[];
  readonly approval_id?: string | null;
  readonly tool_summaries?: readonly AgentToolSummary[];
  readonly error?: AgentTaskErrorSummary | null;
  readonly cost_summary?: AgentCostSummary | null;
}

export interface AgentRunSnapshot {
  readonly run_id: string;
  readonly version: number;
  readonly status: AgentRunStatus;
  readonly last_event_id: string | null;
  readonly started_at: string;
  readonly completed_at: string | null;
  readonly selected_node_ids: readonly string[];
  readonly document_version: number;
  readonly tasks: readonly AgentTaskSummary[];
  readonly brand_rule_set_version?: string | null;
  readonly safe_summary?: string | null;
  readonly cost_summary?: AgentCostSummary | null;
}

export interface AIWorkspaceSnapshot {
  readonly project_id: string;
  readonly project_name: string;
  readonly brand_name: string | null;
  readonly brand_binding?: WorkspaceBrandBinding | null;
  readonly document: CanvasDocumentSummary;
  readonly references: readonly ProjectReference[];
  readonly run: AgentRunSnapshot | null;
  readonly messages: readonly WorkspaceMessage[];
  readonly artifacts: readonly WorkspaceArtifact[];
  readonly approvals: readonly WorkspaceApproval[];
}

export interface StartRunInput {
  readonly project_id: string;
  readonly prompt: string;
  readonly selected_node_ids: readonly string[];
  readonly document_version: number;
  readonly reference_asset_ids: readonly string[];
  readonly reference_artifact_version_ids: readonly string[];
  readonly brand_rule_set_version?: string | null;
}

export interface RunControlInput {
  readonly run_id: string;
  readonly expected_run_version: number;
}

export interface RetryTaskInput extends RunControlInput {
  readonly task_id: string;
}

export interface ApprovalDecisionInput {
  readonly approval_id: string;
  readonly run_id: string;
  readonly expected_run_version: number;
  readonly decision: ApprovalDecision;
  readonly request_changes_note: string | null;
}

export interface PlaceArtifactInput {
  readonly project_id: string;
  readonly document_id: string;
  readonly expected_document_version: number;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
}

export type WorkspaceEvent =
  | {
      readonly id: string;
      readonly sequence: number;
      readonly run_id: string;
      readonly type: "run.status";
      readonly run: AgentRunSnapshot;
    }
  | {
      readonly id: string;
      readonly sequence: number;
      readonly run_id: string;
      readonly type: "message.created";
      readonly message: WorkspaceMessage;
    }
  | {
      readonly id: string;
      readonly sequence: number;
      readonly run_id: string;
      readonly type: "artifact.created";
      readonly artifact: WorkspaceArtifact;
      readonly message: WorkspaceMessage;
    }
  | {
      readonly id: string;
      readonly sequence: number;
      readonly run_id: string;
      readonly type: "approval.required";
      readonly approval: WorkspaceApproval;
      readonly message: WorkspaceMessage;
    };

export interface WorkspaceReducerState {
  readonly snapshot: AIWorkspaceSnapshot;
  readonly seen_event_ids: readonly string[];
}

export interface DeterministicWorkspaceSeed {
  readonly snapshot: AIWorkspaceSnapshot;
  readonly stale_approval_id: string;
}

export interface AIWorkspaceBootstrap {
  readonly mode: "http" | "e2e";
  readonly seed: DeterministicWorkspaceSeed | null;
}
