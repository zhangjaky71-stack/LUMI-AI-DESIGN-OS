import type {
  ExactArtifactRef,
  RunControlSnapshot,
  SafeRunEvent,
} from "@/lib/workspace/types";

export type TimelineItemType =
  | "run"
  | "task"
  | "tool"
  | "progress"
  | "approval"
  | "artifact"
  | "error"
  | "status";

export type TimelineItemStatus =
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "info";

export type WorkspaceTimelineItem = {
  id: string;
  type: TimelineItemType;
  status: TimelineItemStatus;
  label: string;
  safeSummary?: string;
  occurredAt?: string;
  taskId?: string;
  node?: string;
  artifact?: ExactArtifactRef;
  errorCode?: string;
  progress?: { current: number; total: number };
  costSummary?: string;
  retrySummary?: string;
};

export function eventTimelineItem(event: SafeRunEvent): WorkspaceTimelineItem | null {
  const payload = event.payload;
  const base = { id: event.eventId, occurredAt: event.occurredAt };
  const taskId = publicString(payload.task_id ?? payload.taskId);
  const node = publicString(payload.node ?? payload.node_name ?? payload.nodeName);

  switch (event.eventType) {
    case "run.started":
      return { ...base, type: "run", status: "running", label: "Run started", safeSummary: publicSummary(payload) ?? "Agent execution started." };
    case "node.started":
      return { ...base, type: "task", status: "running", label: humanize(node ?? "Next task"), safeSummary: publicSummary(payload), ...(taskId ? { taskId } : {}), ...(node ? { node } : {}) };
    case "agent.status": {
      const status = publicString(payload.status);
      return { ...base, type: statusLooksError(status) ? "error" : "status", status: statusLooksError(status) ? "failed" : "info", label: status ? humanize(status) : "Agent status", safeSummary: publicSummary(payload), ...(taskId ? { taskId } : {}), ...(publicErrorCode(payload) ? { errorCode: publicErrorCode(payload)! } : {}), ...(retrySummary(payload) ? { retrySummary: retrySummary(payload)! } : {}) };
    }
    case "agent.delta": {
      const summary = publicString(payload.text ?? payload.delta);
      return summary ? { ...base, type: "status", status: "info", label: "Agent update", safeSummary: summary, ...(taskId ? { taskId } : {}) } : null;
    }
    case "tool.call": {
      const tool = publicString(payload.tool_name ?? payload.tool);
      return { ...base, type: "tool", status: "completed", label: toolAction(tool), safeSummary: publicSummary(payload), ...(taskId ? { taskId } : {}), ...(costSummary(payload) ? { costSummary: costSummary(payload)! } : {}), ...(retrySummary(payload) ? { retrySummary: retrySummary(payload)! } : {}) };
    }
    case "task.progress": {
      const progress = progressCounts(payload);
      const label = publicString(payload.label ?? payload.stage) ?? (node ? humanize(node) : "Task progress");
      return { ...base, type: "progress", status: "running", label, safeSummary: publicSummary(payload), ...(taskId ? { taskId } : {}), ...(node ? { node } : {}), ...(progress ? { progress } : {}), ...(costSummary(payload) ? { costSummary: costSummary(payload)! } : {}), ...(retrySummary(payload) ? { retrySummary: retrySummary(payload)! } : {}) };
    }
    case "approval.required":
      return { ...base, type: "approval", status: "waiting", label: "Approval required", safeSummary: publicSummary(payload) ?? "The run is waiting for a user decision.", ...(taskId ? { taskId } : {}), ...(node ? { node } : {}) };
    case "artifact.created": {
      const artifact = exactArtifactFromPayload(payload);
      return { ...base, type: "artifact", status: artifact ? "completed" : "failed", label: artifact ? (artifact.label ?? "Artifact created") : "Artifact event incomplete", safeSummary: artifact ? `Created exact artifact version ${artifact.versionNumber ? `v${artifact.versionNumber}` : shortId(artifact.artifactVersionId)}.` : "The event did not contain an exact artifact version, so no Canvas link is shown.", ...(taskId ? { taskId } : {}), ...(artifact ? { artifact } : {}) };
    }
    case "run.completed":
      return { ...base, type: "run", status: "completed", label: "Run complete", safeSummary: publicSummary(payload) ?? "Agent execution completed.", ...(costSummary(payload) ? { costSummary: costSummary(payload)! } : {}) };
    case "run.cancelled":
      return { ...base, type: "run", status: "cancelled", label: "Run cancelled", safeSummary: "The run stopped. External side effects already accepted by providers may still require reconciliation." };
    case "run.waiting_external":
      return { ...base, type: "task", status: "waiting", label: "Waiting for external work", safeSummary: publicSummary(payload) ?? "A provider or background job has not finished yet.", ...(taskId ? { taskId } : {}), ...(retrySummary(payload) ? { retrySummary: retrySummary(payload)! } : {}) };
    default:
      return null;
  }
}

export function canonicalTimelineItem(control: RunControlSnapshot | null): WorkspaceTimelineItem | null {
  if (!control) return null;
  const status = control.status.toLowerCase();
  const interrupt = control.interrupts.find((item) => item.kind === "approval" || item.kind === "review") ?? control.interrupts[0];
  const next = control.nextNodes[0];
  const taskFields = control.taskId ? { taskId: control.taskId } : {};
  if (control.errorCode || status === "failed") {
    return {
      id: `canonical:${control.agentRunId}:${control.resumeVersion}:error`,
      type: "error",
      status: "failed",
      label: "Run needs attention",
      safeSummary: control.errorCode ? `The run stopped with error code ${control.errorCode}.` : "The run failed.",
      errorCode: control.errorCode ?? undefined,
      occurredAt: control.updatedAt,
      ...taskFields,
    };
  }
  if (interrupt) {
    return {
      id: `canonical:${control.agentRunId}:${control.resumeVersion}:waiting`,
      type: "approval",
      status: "waiting",
      label: interrupt.kind === "approval" || interrupt.kind === "review" ? "Waiting for approval" : "Waiting for user input",
      safeSummary: interrupt.node ? `Paused at ${humanize(interrupt.node)}.` : "The run is paused for user input.",
      node: interrupt.node ?? undefined,
      occurredAt: control.updatedAt,
      ...taskFields,
    };
  }
  if (status === "succeeded" || status === "completed") {
    return { id: `canonical:${control.agentRunId}:${control.resumeVersion}:complete`, type: "run", status: "completed", label: "Run complete", safeSummary: `${control.artifactRefs.length} artifact reference${control.artifactRefs.length === 1 ? "" : "s"} recorded.`, occurredAt: control.updatedAt, ...taskFields };
  }
  if (status === "cancelled" || status === "canceled") {
    return { id: `canonical:${control.agentRunId}:${control.resumeVersion}:cancelled`, type: "run", status: "cancelled", label: "Run cancelled", occurredAt: control.updatedAt, ...taskFields };
  }
  if (status.includes("waiting") || status.includes("external")) {
    return { id: `canonical:${control.agentRunId}:${control.resumeVersion}:external`, type: "task", status: "waiting", label: "Waiting for external work", safeSummary: control.route ? `Current route: ${humanize(control.route)}.` : undefined, occurredAt: control.updatedAt, ...taskFields };
  }
  return {
    id: `canonical:${control.agentRunId}:${control.resumeVersion}:active`,
    type: "task",
    status: "running",
    label: next ? humanize(next) : "Agent working",
    safeSummary: control.repairIteration > 0 ? `Repair pass ${control.repairIteration} of ${Math.max(control.maxRepairIterations, control.repairIteration)}.` : control.route ? `Current route: ${humanize(control.route)}.` : "Canonical run state is active.",
    node: next,
    occurredAt: control.updatedAt,
    ...taskFields,
  };
}

export function timelineVisibleSummary(item: WorkspaceTimelineItem): string | null {
  const pieces = [item.safeSummary, item.progress ? `${item.progress.current}/${item.progress.total}` : null, item.retrySummary, item.costSummary].filter((value): value is string => Boolean(value));
  return pieces.length ? pieces.join(" · ") : null;
}

function publicSummary(payload: Readonly<Record<string, unknown>>): string | null {
  return publicString(payload.safe_summary ?? payload.safeSummary ?? payload.message ?? payload.summary ?? payload.action);
}

function progressCounts(payload: Readonly<Record<string, unknown>>): { current: number; total: number } | null {
  const current = publicInteger(payload.current ?? payload.completed ?? payload.done);
  const total = publicInteger(payload.total ?? payload.target);
  if (current !== null && total !== null && total > 0 && current >= 0 && current <= total) return { current, total };
  return null;
}

function retrySummary(payload: Readonly<Record<string, unknown>>): string | null {
  const attempt = publicInteger(payload.retry_attempt ?? payload.attempt);
  const provider = publicString(payload.fallback_provider ?? payload.provider_fallback ?? payload.provider);
  const retrying = payload.retrying === true || (attempt !== null && attempt > 1);
  if (retrying && provider) return `Retry ${attempt ?? ""} using ${humanize(provider)}`.trim();
  if (retrying) return attempt ? `Retry attempt ${attempt}` : "Retrying automatically";
  if (publicString(payload.fallback_provider ?? payload.provider_fallback)) return `Switched provider to ${humanize(provider!)}`;
  return null;
}

function costSummary(payload: Readonly<Record<string, unknown>>): string | null {
  const credits = publicNumber(payload.credits_used ?? payload.credits);
  const cost = publicNumber(payload.cost_usd ?? payload.actual_cost_usd ?? payload.estimated_cost_usd);
  if (cost !== null && cost >= 0) return `$${cost.toFixed(cost < 1 ? 4 : 2)}`;
  if (credits !== null && credits >= 0) return `${credits} credits`;
  return null;
}

function publicErrorCode(payload: Readonly<Record<string, unknown>>): string | null {
  return publicString(payload.error_code ?? payload.errorCode ?? payload.reason_code);
}

function exactArtifactFromPayload(payload: Readonly<Record<string, unknown>>): ExactArtifactRef | null {
  const artifactId = publicString(payload.artifact_id ?? payload.artifactId);
  const artifactVersionId = publicString(payload.artifact_version_id ?? payload.artifactVersionId);
  if (!artifactId || !artifactVersionId) return null;
  const version = publicInteger(payload.version_number ?? payload.versionNumber);
  const label = publicString(payload.label);
  const previewRef = publicString(payload.preview_ref ?? payload.previewRef);
  return { artifactId, artifactVersionId, ...(version && version > 0 ? { versionNumber: version } : {}), ...(label ? { label } : {}), ...(previewRef ? { previewRef } : {}) };
}

function toolAction(tool: string | null): string {
  if (!tool) return "Used a tool";
  const normalized = tool.toLowerCase();
  if (normalized.includes("search")) return "Searched sources";
  if (normalized.includes("read") || normalized.includes("fetch")) return "Read source material";
  if (normalized.includes("image") || normalized.includes("generate")) return "Generated creative output";
  if (normalized.includes("quality") || normalized.includes("validate") || normalized.includes("check")) return "Checked output quality";
  if (normalized.includes("export")) return "Prepared export";
  return `Used ${humanize(tool)}`;
}

function statusLooksError(status: string | null): boolean {
  return Boolean(status && ["failed", "error", "blocked"].some((part) => status.toLowerCase().includes(part)));
}

function publicString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  return text ? text.slice(0, 1200) : null;
}
function publicInteger(value: unknown): number | null { return Number.isInteger(value) ? value as number : null; }
function publicNumber(value: unknown): number | null { return typeof value === "number" && Number.isFinite(value) ? value : null; }
function humanize(value: string): string { return value.replace(/[._/-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()); }
function shortId(value: string): string { return value.length <= 12 ? value : `${value.slice(0, 6)}…${value.slice(-4)}`; }