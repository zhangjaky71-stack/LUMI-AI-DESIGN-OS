import type {
  AgentRunStatus,
  AgentTaskStatus,
  WorkspaceApproval,
  WorkspaceArtifact,
} from "@/lib/ai-workspace/types";

export type TimelineCategory = "AGENT" | "GENERATION" | "APPROVAL" | "ERROR";
export type TimelineFilter = "ALL" | TimelineCategory;
export type TimelineItemType = "RUN" | "TASK" | "MESSAGE" | "ARTIFACT" | "APPROVAL" | "WARNING";
export type TimelineItemStatus = AgentTaskStatus | AgentRunStatus | "WAITING_USER" | "WARNING" | "INFO";

export interface TimelineProgress {
  readonly completed: number;
  readonly total: number;
  readonly label: string;
}

export interface TimelineToolAction {
  readonly id: string;
  readonly label: string;
}

export interface TimelineErrorSummary {
  readonly code: string;
  readonly safe_message: string;
  readonly retrying: boolean;
  readonly request_id: string | null;
  readonly provider_fallback: string | null;
}

export interface TimelineCostSummary {
  readonly estimated_microusd: string | null;
  readonly actual_microusd: string | null;
  readonly credits: string | null;
  readonly budget_warning: boolean;
}

export interface TimelineItem {
  readonly id: string;
  readonly type: TimelineItemType;
  readonly category: TimelineCategory;
  readonly status: TimelineItemStatus;
  readonly label: string;
  readonly safe_summary: string | null;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  readonly task_id: string | null;
  readonly artifact_version_ids: readonly string[];
  readonly approval_id: string | null;
  readonly progress: TimelineProgress | null;
  readonly tool_actions: readonly TimelineToolAction[];
  readonly error: TimelineErrorSummary | null;
  readonly cost: TimelineCostSummary | null;
  readonly artifact: WorkspaceArtifact | null;
  readonly approval: WorkspaceApproval | null;
  readonly sticky: boolean;
}

export interface AgentTimelineProjection {
  readonly run_id: string | null;
  readonly run_status: AgentRunStatus | null;
  readonly items: readonly TimelineItem[];
  readonly visible_items: readonly TimelineItem[];
  readonly filters: readonly TimelineFilter[];
  readonly has_waiting_user: boolean;
  readonly has_error: boolean;
  readonly cost: TimelineCostSummary | null;
}

export const TIMELINE_FILTERS: readonly TimelineFilter[] = [
  "ALL",
  "AGENT",
  "GENERATION",
  "APPROVAL",
  "ERROR",
];
