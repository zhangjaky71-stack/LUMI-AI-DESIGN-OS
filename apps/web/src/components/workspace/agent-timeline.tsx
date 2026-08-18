"use client";

import { useMemo, useState, type ReactNode } from "react";

import {
  canonicalTimelineItem,
  timelineVisibleSummary,
  type TimelineItemType,
  type WorkspaceTimelineItem,
} from "@/lib/workspace/timeline";
import type { ExactArtifactRef, RunControlSnapshot } from "@/lib/workspace/types";

export type AgentTimelineFilter = "all" | "agent" | "artifact" | "attention";

export function AgentTimeline({ control, items, onOpenArtifact }: {
  control: RunControlSnapshot | null;
  items: readonly WorkspaceTimelineItem[];
  onOpenArtifact: (artifact: ExactArtifactRef) => void;
}) {
  const [filter, setFilter] = useState<AgentTimelineFilter>("all");
  const canonical = useMemo(() => canonicalTimelineItem(control), [control]);
  const filtered = useMemo(() => items.filter((item) => visibleForFilter(item, filter)), [filter, items]);
  const approval = control?.interrupts.find((item) => item.kind === "approval" || item.kind === "review") ?? null;

  return (
    <div className="agent-timeline" aria-label="Agent run timeline">
      <div className="agent-timeline-current" aria-live="polite">
        <span className="timeline-section-label">Current stage</span>
        {canonical ? (
          <TimelineCard item={canonical} current onOpenArtifact={onOpenArtifact}>
            {canonical.type === "approval" && approval ? (
              <div className="timeline-approval-governance-note" role="status">
                This run is waiting for a formal Approval decision. Review the exact artifact in the Approval panel; the timeline cannot bypass governance by resuming the graph directly.
              </div>
            ) : null}
          </TimelineCard>
        ) : <div className="timeline-current-empty">Start a run to see canonical progress.</div>}
      </div>

      <div className="agent-timeline-history-header">
        <span className="timeline-section-label">Run activity</span>
        <div className="timeline-filters" aria-label="Timeline filters">
          {(["all", "agent", "artifact", "attention"] as const).map((value) => (
            <button key={value} type="button" className={filter === value ? "is-active" : ""} aria-pressed={filter === value} onClick={() => setFilter(value)}>{filterLabel(value)}</button>
          ))}
        </div>
      </div>

      <div className="agent-timeline-items" aria-live="polite" aria-relevant="additions text">
        {filtered.length ? filtered.map((item) => <TimelineCard key={item.id} item={item} onOpenArtifact={onOpenArtifact} />) : (
          <div className="timeline-history-empty">{items.length ? "No activity matches this filter." : "Durable safe events will appear here as the run progresses."}</div>
        )}
      </div>

      <div className="agent-timeline-safety-note">
        Timeline shows public task/domain events and canonical run state only. Private reasoning, raw tool payloads, secrets and stack traces are never rendered.
      </div>
    </div>
  );
}

function TimelineCard({ item, current = false, onOpenArtifact, children }: {
  item: WorkspaceTimelineItem;
  current?: boolean;
  onOpenArtifact: (artifact: ExactArtifactRef) => void;
  children?: ReactNode;
}) {
  const summary = timelineVisibleSummary(item);
  return (
    <article className={`timeline-card timeline-${item.type} status-${item.status}${current ? " is-current" : ""}`}>
      <div className="timeline-rail" aria-hidden="true"><span>{timelineGlyph(item.type)}</span></div>
      <div className="timeline-card-body">
        <div className="timeline-card-title-row"><div><span className="timeline-type-label">{timelineTypeLabel(item.type)}</span><h3>{item.label}</h3></div><span className={`timeline-status status-${item.status}`}>{statusLabel(item.status)}</span></div>
        {summary ? <p>{summary}</p> : null}
        {item.progress ? <div className="timeline-count-progress" aria-label={`${item.progress.current} of ${item.progress.total}`}><div><span>Completed</span><strong>{item.progress.current}/{item.progress.total}</strong></div><progress value={item.progress.current} max={item.progress.total} /></div> : null}
        <div className="timeline-meta">
          {item.taskId ? <span title={item.taskId}>Task {shortId(item.taskId)}</span> : null}
          {item.node ? <span>{humanize(item.node)}</span> : null}
          {item.errorCode ? <code>{item.errorCode}</code> : null}
          {item.occurredAt ? <time dateTime={item.occurredAt}>{formatTime(item.occurredAt)}</time> : null}
        </div>
        {item.artifact ? <button className="timeline-artifact-link" type="button" onClick={() => onOpenArtifact(item.artifact!)}>Open exact artifact {item.artifact.versionNumber ? `v${item.artifact.versionNumber}` : shortId(item.artifact.artifactVersionId)} in Canvas</button> : null}
        {children ? <div className="timeline-actions">{children}</div> : null}
      </div>
    </article>
  );
}

function visibleForFilter(item: WorkspaceTimelineItem, filter: AgentTimelineFilter): boolean {
  if (filter === "all") return true;
  if (filter === "artifact") return item.type === "artifact";
  if (filter === "attention") return item.type === "approval" || item.type === "error" || item.status === "failed" || item.status === "cancelled";
  return ["task", "tool", "progress", "status", "run"].includes(item.type);
}
function filterLabel(filter: AgentTimelineFilter): string { if (filter === "agent") return "Agent"; if (filter === "artifact") return "Artifacts"; if (filter === "attention") return "Attention"; return "All"; }
function timelineGlyph(type: TimelineItemType): string { if (type === "approval") return "!"; if (type === "artifact") return "A"; if (type === "error") return "×"; if (type === "tool") return "T"; if (type === "progress") return "↗"; if (type === "task") return "•"; if (type === "run") return "R"; return "·"; }
function timelineTypeLabel(type: TimelineItemType): string { if (type === "approval") return "Approval"; if (type === "artifact") return "Artifact"; if (type === "error") return "Issue"; if (type === "tool") return "Action"; if (type === "progress") return "Progress"; if (type === "task") return "Task"; if (type === "run") return "Run"; return "Update"; }
function statusLabel(status: WorkspaceTimelineItem["status"]): string { if (status === "running") return "In progress"; if (status === "waiting") return "Waiting"; if (status === "completed") return "Done"; if (status === "failed") return "Failed"; if (status === "cancelled") return "Cancelled"; return "Info"; }
function formatTime(value: string): string { const date = new Date(value); if (Number.isNaN(date.getTime())) return value; return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date); }
function shortId(value: string): string { return value.length <= 14 ? value : `${value.slice(0, 6)}…${value.slice(-4)}`; }
function humanize(value: string): string { return value.replace(/[._/-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase()); }
