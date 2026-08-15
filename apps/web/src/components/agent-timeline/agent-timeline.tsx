"use client";

import { useMemo, useState } from "react";
import { isApprovalActionable } from "@/lib/ai-workspace/contracts";
import type {
  AIWorkspaceSnapshot,
  ApprovalDecision,
  WorkspaceApproval,
} from "@/lib/ai-workspace/types";
import { projectAgentTimeline, timelineCategoryLabel } from "@/lib/agent-timeline/projector";
import type { TimelineFilter, TimelineItem } from "@/lib/agent-timeline/types";
import styles from "./agent-timeline.module.css";

interface Props {
  readonly snapshot: AIWorkspaceSnapshot;
  readonly busy: boolean;
  readonly artifactReferenceIds: readonly string[];
  readonly approvalNotes: Readonly<Record<string, string>>;
  readonly onApprovalNoteChange: (approvalId: string, note: string) => void;
  readonly onDecideApproval: (approval: WorkspaceApproval, decision: ApprovalDecision) => void;
  readonly onPlaceArtifact: (artifactId: string, versionId: string) => void;
  readonly onToggleArtifactReference: (versionId: string) => void;
  readonly onRetryTask: (taskId: string) => void;
  readonly onJumpToCanvas: (artifactVersionId: string) => void;
}

const FILTER_LABEL: Readonly<Record<TimelineFilter, string>> = {
  ALL: "All",
  AGENT: "Agent",
  GENERATION: "Generation",
  APPROVAL: "Approval",
  ERROR: "Error",
};

function money(microusd: string | null): string | null {
  if (!microusd) return null;
  const value = Number(microusd) / 1_000_000;
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : null;
}

function statusLabel(item: TimelineItem): string {
  if (item.status === "WAITING_USER") return "WAITING USER";
  if (item.status === "SUCCEEDED") return "DONE";
  if (item.status === "RUNNING") return "RUNNING";
  if (item.status === "PENDING" || item.status === "QUEUED") return "QUEUED";
  if (item.status === "FAILED") return "FAILED";
  if (item.status === "CANCELED") return "CANCELED";
  if (item.status === "PAUSED") return "PAUSED";
  if (item.status === "WARNING") return "WARNING";
  return String(item.status);
}

function time(value: string | null): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function AgentTimeline({
  snapshot,
  busy,
  artifactReferenceIds,
  approvalNotes,
  onApprovalNoteChange,
  onDecideApproval,
  onPlaceArtifact,
  onToggleArtifactReference,
  onRetryTask,
  onJumpToCanvas,
}: Props) {
  const [filter, setFilter] = useState<TimelineFilter>("ALL");
  const [costOpen, setCostOpen] = useState(false);
  const projection = useMemo(() => projectAgentTimeline(snapshot, filter), [snapshot, filter]);
  const sticky = projection.visible_items.filter((item) => item.sticky);
  const normal = projection.visible_items.filter((item) => !item.sticky);

  const renderItem = (item: TimelineItem) => {
    const artifact = item.artifact;
    const approval = item.approval;
    const actionable = approval ? isApprovalActionable(approval, snapshot.run) : false;
    const stale = Boolean(
      approval &&
      !actionable &&
      !["APPROVED", "REJECTED", "CHANGES_REQUESTED"].includes(approval.state),
    );

    return (
      <article
        key={item.id}
        className={styles.item}
        data-type={item.type}
        data-status={item.status}
        data-sticky={item.sticky}
      >
        <div className={styles.rail} aria-hidden="true"><span /></div>
        <div className={styles.itemBody}>
          <div className={styles.itemHeader}>
            <div>
              <span className={styles.category}>{timelineCategoryLabel(item.category)}</span>
              <h3>{item.label}</h3>
            </div>
            <div className={styles.statusBlock}>
              <strong>{statusLabel(item)}</strong>
              {time(item.started_at) ? <small>{time(item.started_at)}</small> : null}
            </div>
          </div>

          {item.safe_summary ? <p className={styles.summary}>{item.safe_summary}</p> : null}

          {item.progress ? (
            <div className={styles.progress} aria-label={`${item.label} progress ${item.progress.label}`}>
              <div><span style={{ width: `${Math.round((item.progress.completed / item.progress.total) * 100)}%` }} /></div>
              <strong>{item.progress.label}</strong>
            </div>
          ) : null}

          {item.tool_actions.length ? (
            <div className={styles.tools} aria-label="Safe tool actions">
              {item.tool_actions.map((tool) => <span key={tool.id}>✓ {tool.label}</span>)}
            </div>
          ) : null}

          {item.error ? (
            <div className={styles.errorBox}>
              <div><strong>{item.error.code}</strong><span>{item.error.safe_message}</span></div>
              {item.error.provider_fallback ? <p>Fallback: {item.error.provider_fallback}</p> : null}
              {item.error.request_id ? <p>Request {item.error.request_id}</p> : null}
              {item.error.retrying ? <p>正在自动重试。</p> : null}
              {item.task_id && snapshot.run?.tasks.find((task) => task.task_id === item.task_id)?.retryable ? (
                <button type="button" onClick={() => onRetryTask(item.task_id!)} disabled={busy}>Retry {item.label}</button>
              ) : null}
            </div>
          ) : null}

          {artifact ? (
            <div className={styles.artifactCard}>
              <div className={styles.artifactPreview}>{artifact.preview_label}</div>
              <div>
                <span className={styles.micro}>ARTIFACT · v{artifact.version}</span>
                <h3>{artifact.title}</h3>
                <p>精确版本 {artifact.version_id}</p>
                <div className={styles.actions}>
                  <button type="button" onClick={() => onPlaceArtifact(artifact.artifact_id, artifact.version_id)} disabled={busy}>放到 Canvas</button>
                  <button
                    type="button"
                    onClick={() => onToggleArtifactReference(artifact.version_id)}
                    aria-pressed={artifactReferenceIds.includes(artifact.version_id)}
                  >作为参考</button>
                  <button type="button" onClick={() => onJumpToCanvas(artifact.version_id)}>查看 Canvas</button>
                </div>
              </div>
            </div>
          ) : null}

          {approval ? (
            <div className={styles.approvalCard} data-actionable={actionable}>
              <div className={styles.approvalHeading}>
                <div><span className={styles.micro}>APPROVAL</span><h3>{approval.title}</h3></div>
                <strong>{stale ? "已过期" : approval.state}</strong>
              </div>
              <p>{approval.description}</p>
              {approval.impact ? <p className={styles.muted}>{approval.impact}</p> : null}
              {money(approval.estimated_cost_microusd) ? <p>预计增量成本 {money(approval.estimated_cost_microusd)}</p> : null}
              {stale ? <p className={styles.stale}>旧审批不会被提交；请以当前 Run 的 canonical state 为准。</p> : null}
              {approval.state === "PENDING" ? (
                <>
                  <textarea
                    aria-label={`${approval.title} 修改意见`}
                    placeholder="需要修改时填写具体要求"
                    value={approvalNotes[approval.approval_id] ?? ""}
                    onChange={(event) => onApprovalNoteChange(approval.approval_id, event.target.value)}
                    disabled={!actionable}
                  />
                  <div className={styles.actions}>
                    <button type="button" onClick={() => onDecideApproval(approval, "APPROVE")} disabled={!actionable || busy}>Approve</button>
                    <button type="button" onClick={() => onDecideApproval(approval, "REJECT")} disabled={!actionable || busy}>Reject</button>
                    <button type="button" onClick={() => onDecideApproval(approval, "REQUEST_CHANGES")} disabled={!actionable || busy}>Request Changes</button>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}

          {item.cost && item.type !== "APPROVAL" ? (
            <details className={styles.itemCost}>
              <summary>Cost</summary>
              <span>estimated {money(item.cost.estimated_microusd) ?? "—"}</span>
              <span>actual {money(item.cost.actual_microusd) ?? "—"}</span>
              {item.cost.credits ? <span>{item.cost.credits} credits</span> : null}
            </details>
          ) : null}
        </div>
      </article>
    );
  };

  return (
    <div className={styles.timeline} aria-label="Agent Timeline">
      <div className={styles.timelineHeader}>
        <div>
          <span className={styles.micro}>RUN OBSERVABILITY</span>
          <strong>{projection.run_id ? `Run ${projection.run_status}` : "Ready"}</strong>
        </div>
        {projection.cost ? (
          <button type="button" className={styles.costToggle} onClick={() => setCostOpen((value) => !value)} aria-expanded={costOpen}>
            Cost {money(projection.cost.actual_microusd) ?? money(projection.cost.estimated_microusd) ?? "—"}
          </button>
        ) : null}
      </div>

      {costOpen && projection.cost ? (
        <div className={styles.costPanel}>
          <span>Estimated <strong>{money(projection.cost.estimated_microusd) ?? "—"}</strong></span>
          <span>Actual <strong>{money(projection.cost.actual_microusd) ?? "—"}</strong></span>
          {projection.cost.credits ? <span>Credits <strong>{projection.cost.credits}</strong></span> : null}
          {projection.cost.budget_warning ? <strong className={styles.budgetWarning}>Budget warning</strong> : null}
        </div>
      ) : null}

      <div className={styles.filters} aria-label="Timeline filters">
        {projection.filters.map((value) => (
          <button key={value} type="button" data-active={filter === value} onClick={() => setFilter(value)}>
            {FILTER_LABEL[value]}
          </button>
        ))}
      </div>

      {sticky.length ? (
        <div className={styles.waiting} aria-label="Waiting for user">
          <span>需要你的确认后 Agent 才会继续</span>
          {sticky.map(renderItem)}
        </div>
      ) : null}

      <div className={styles.items} aria-live="polite">
        {normal.length ? normal.map(renderItem) : <p className={styles.empty}>当前筛选下没有 Timeline 事件。</p>}
      </div>

      <p className={styles.safety}>Timeline 只展示 TaskGraph / Run / safe tool summaries；不展示 system prompt、内部 chain-of-thought、secret tool payload 或 stack trace。</p>
    </div>
  );
}
