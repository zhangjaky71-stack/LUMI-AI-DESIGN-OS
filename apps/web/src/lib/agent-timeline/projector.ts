import type {
  AIWorkspaceSnapshot,
  AgentCostSummary,
  AgentTaskCategory,
  AgentTaskSummary,
  WorkspaceMessage,
} from "@/lib/ai-workspace/types";
import type {
  AgentTimelineProjection,
  TimelineCategory,
  TimelineCostSummary,
  TimelineFilter,
  TimelineItem,
  TimelineItemStatus,
  TimelineProgress,
} from "./types";
import { TIMELINE_FILTERS } from "./types";

const PRIVATE_EXECUTION_PATTERNS = [
  /chain[- ]?of[- ]?thought/i,
  /system\s+prompt/i,
  /raw\s+tool\s+(payload|result|args?)/i,
  /authorization\s*:\s*bearer/i,
  /api[_\s-]?key\s*[:=]/i,
  /stack\s+trace/i,
  /BEGIN\s+PRIVATE/i,
];

export function sanitizeTimelineText(value: string | null | undefined): string | null {
  if (!value) return null;
  const compact = value.replace(/\s+/g, " ").trim().slice(0, 800);
  if (!compact) return null;
  return PRIVATE_EXECUTION_PATTERNS.some((pattern) => pattern.test(compact))
    ? "内部执行细节已隐藏。"
    : compact;
}

function cost(value: AgentCostSummary | null | undefined): TimelineCostSummary | null {
  if (!value) return null;
  return {
    estimated_microusd: value.estimated_microusd ?? null,
    actual_microusd: value.actual_microusd ?? null,
    credits: value.credits ?? null,
    budget_warning: Boolean(value.budget_warning),
  };
}

function taskCategory(task: AgentTaskSummary): TimelineCategory {
  if (task.category) return task.category;
  const label = task.label.toLowerCase();
  if (/生成|generation|visual|image|video|render|repair|quality/.test(label)) return "GENERATION";
  if (task.status === "FAILED") return "ERROR";
  return "AGENT";
}

function progress(task: AgentTaskSummary): TimelineProgress | null {
  const completed = task.completed_units;
  const total = task.total_units;
  if (
    typeof completed !== "number" ||
    typeof total !== "number" ||
    !Number.isFinite(completed) ||
    !Number.isFinite(total) ||
    total <= 0
  ) {
    return null;
  }
  const safeCompleted = Math.max(0, Math.min(Math.floor(completed), Math.floor(total)));
  const safeTotal = Math.max(1, Math.floor(total));
  return { completed: safeCompleted, total: safeTotal, label: `${safeCompleted}/${safeTotal}` };
}

function taskItem(task: AgentTaskSummary): TimelineItem {
  const error = task.status === "FAILED" && task.error
    ? {
        code: task.error.code,
        safe_message: sanitizeTimelineText(task.error.safe_message) ?? "任务执行失败。",
        retrying: Boolean(task.error.retrying),
        request_id: task.error.request_id ?? null,
        provider_fallback: sanitizeTimelineText(task.error.provider_fallback),
      }
    : null;
  return {
    id: `task:${task.task_id}`,
    type: "TASK",
    category: error ? "ERROR" : taskCategory(task),
    status: task.status,
    label: sanitizeTimelineText(task.label) ?? "Agent task",
    safe_summary: sanitizeTimelineText(task.safe_summary),
    started_at: task.started_at ?? null,
    finished_at: task.finished_at ?? null,
    task_id: task.task_id,
    artifact_version_ids: task.artifact_version_ids ?? [],
    approval_id: task.approval_id ?? null,
    progress: progress(task),
    tool_actions: (task.tool_summaries ?? []).map((tool) => ({
      id: tool.id,
      label: sanitizeTimelineText(tool.label) ?? "已执行安全工具动作",
    })),
    error,
    cost: cost(task.cost_summary),
    artifact: null,
    approval: null,
    sticky: false,
  };
}

function messageCategory(message: WorkspaceMessage): TimelineCategory {
  if (message.kind === "ERROR") return "ERROR";
  if (message.kind === "WARNING" && message.warning_code === "PROVIDER_FALLBACK") return "GENERATION";
  return "AGENT";
}

function messageStatus(message: WorkspaceMessage): TimelineItemStatus {
  if (message.kind === "ERROR") return "FAILED";
  if (message.kind === "WARNING") return "WARNING";
  return "INFO";
}

function messageItem(message: WorkspaceMessage): TimelineItem | null {
  if (!["STATUS", "WARNING", "ERROR"].includes(message.kind)) return null;
  return {
    id: `message:${message.id}`,
    type: message.kind === "WARNING" ? "WARNING" : "MESSAGE",
    category: messageCategory(message),
    status: messageStatus(message),
    label:
      message.kind === "WARNING"
        ? message.warning_code === "PROVIDER_FALLBACK"
          ? "Provider fallback"
          : "运行警告"
        : message.kind === "ERROR"
          ? "任务错误"
          : "Agent update",
    safe_summary: sanitizeTimelineText(message.text),
    started_at: message.created_at,
    finished_at: message.created_at,
    task_id: null,
    artifact_version_ids: message.artifact_version_id ? [message.artifact_version_id] : [],
    approval_id: message.approval_id,
    progress: null,
    tool_actions: [],
    error:
      message.kind === "ERROR"
        ? {
            code: message.warning_code ?? "AGENT_TASK_FAILED",
            safe_message: sanitizeTimelineText(message.text) ?? "任务执行失败。",
            retrying: false,
            request_id: null,
            provider_fallback: null,
          }
        : null,
    cost: null,
    artifact: null,
    approval: null,
    sticky: false,
  };
}

export function projectAgentTimeline(
  snapshot: AIWorkspaceSnapshot,
  filter: TimelineFilter = "ALL",
): AgentTimelineProjection {
  const run = snapshot.run;
  const items: TimelineItem[] = [];

  if (run) {
    items.push({
      id: `run:${run.run_id}`,
      type: "RUN",
      category: run.status === "FAILED" ? "ERROR" : "AGENT",
      status: run.status,
      label: "Agent run",
      safe_summary: sanitizeTimelineText(run.safe_summary) ?? `Run ${run.status.toLowerCase()}`,
      started_at: run.started_at,
      finished_at: run.completed_at,
      task_id: null,
      artifact_version_ids: [],
      approval_id: null,
      progress: null,
      tool_actions: [],
      error: null,
      cost: cost(run.cost_summary),
      artifact: null,
      approval: null,
      sticky: false,
    });
    items.push(...run.tasks.map(taskItem));
  }

  for (const message of snapshot.messages) {
    if (message.run_id && run && message.run_id !== run.run_id && message.kind !== "WARNING") continue;
    const item = messageItem(message);
    if (item) items.push(item);
  }

  for (const artifact of snapshot.artifacts) {
    items.push({
      id: `artifact:${artifact.version_id}`,
      type: "ARTIFACT",
      category: "GENERATION",
      status: "SUCCEEDED",
      label: artifact.title,
      safe_summary: sanitizeTimelineText(artifact.preview_label),
      started_at: artifact.created_at,
      finished_at: artifact.created_at,
      task_id: null,
      artifact_version_ids: [artifact.version_id],
      approval_id: null,
      progress: null,
      tool_actions: [],
      error: null,
      cost: null,
      artifact,
      approval: null,
      sticky: false,
    });
  }

  for (const approval of snapshot.approvals) {
    const current = run?.run_id === approval.run_id;
    const waiting = current && approval.state === "PENDING";
    items.push({
      id: `approval:${approval.approval_id}`,
      type: "APPROVAL",
      category: "APPROVAL",
      status: waiting ? "WAITING_USER" : "INFO",
      label: approval.title,
      safe_summary: sanitizeTimelineText(approval.description),
      started_at: null,
      finished_at: approval.state === "PENDING" ? null : run?.completed_at ?? null,
      task_id: null,
      artifact_version_ids: approval.artifact_version_ids,
      approval_id: approval.approval_id,
      progress: null,
      tool_actions: [],
      error: null,
      cost: approval.estimated_cost_microusd
        ? {
            estimated_microusd: approval.estimated_cost_microusd,
            actual_microusd: null,
            credits: null,
            budget_warning: false,
          }
        : null,
      artifact: null,
      approval,
      sticky: waiting,
    });
  }

  const visible = filter === "ALL" ? items : items.filter((item) => item.category === filter);
  return {
    run_id: run?.run_id ?? null,
    run_status: run?.status ?? null,
    items,
    visible_items: visible,
    filters: TIMELINE_FILTERS,
    has_waiting_user: items.some((item) => item.status === "WAITING_USER"),
    has_error: items.some((item) => item.category === "ERROR"),
    cost: cost(run?.cost_summary),
  };
}

export function timelineCategoryLabel(category: AgentTaskCategory | TimelineCategory): string {
  if (category === "GENERATION") return "Generation";
  if (category === "APPROVAL") return "Approval";
  if (category === "ERROR") return "Error";
  return "Agent";
}
