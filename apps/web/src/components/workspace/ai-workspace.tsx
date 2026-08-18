"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { InfiniteCanvas } from "@/components/canvas/infinite-canvas";
import { ApiError } from "@/lib/api/problem";
import type { CanvasSaveState } from "@/lib/canvas/types";
import {
  cancelAgentRun,
  createAgentRun,
  getAgentRun,
  getRunControl,
  resumeAgentRun,
} from "@/lib/workspace/api";
import {
  initialWorkspaceRuntimeState,
  reduceWorkspaceEvent,
  replaceCanonicalControl,
  type WorkspaceRuntimeState,
} from "@/lib/workspace/reducer";
import {
  connectRunEventStream,
  type WorkspaceConnectionState,
} from "@/lib/workspace/stream";
import type {
  AgentRunResource,
  CanvasSelectionContext,
  ExactArtifactRef,
} from "@/lib/workspace/types";

export type WorkspaceProject = {
  id: string;
  name: string;
  objective?: string | null;
  deliverables: readonly string[];
  constraints: readonly string[];
};

export function AiWorkspace({
  organizationId,
  project,
  initialRunId,
}: {
  organizationId: string;
  project: WorkspaceProject;
  initialRunId?: string | null;
}) {
  const router = useRouter();
  const [runId, setRunId] = useState(initialRunId ?? null);
  const [run, setRun] = useState<AgentRunResource | null>(null);
  const [runtime, setRuntime] = useState<WorkspaceRuntimeState>(() =>
    initialWorkspaceRuntimeState(),
  );
  const [connection, setConnection] = useState<WorkspaceConnectionState>("disconnected");
  const [goal, setGoal] = useState("");
  const [lastSubmittedGoal, setLastSubmittedGoal] = useState<string | null>(null);
  const [pending, setPending] = useState<"send" | "stop" | "approve" | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<ExactArtifactRef | null>(null);
  const [canvasSelection, setCanvasSelection] = useState<CanvasSelectionContext | null>(null);
  const [canvasSaveState, setCanvasSaveState] = useState<CanvasSaveState>("saved");
  const mounted = useRef(true);

  const refreshCanonical = useCallback(async () => {
    if (!runId) return;
    const [resourceResult, controlResult] = await Promise.allSettled([
      getAgentRun(organizationId, runId),
      getRunControl(organizationId, runId),
    ]);
    if (!mounted.current) return;
    if (resourceResult.status === "fulfilled") setRun(resourceResult.value);
    if (controlResult.status === "fulfilled") {
      setRuntime((current) => replaceCanonicalControl(current, controlResult.value));
      setNotice(null);
    } else if (
      controlResult.reason instanceof ApiError &&
      controlResult.reason.status === 503
    ) {
      setNotice(
        "Live control/event replay is not composed in this deployment. Durable run status is still refreshed from Project Core.",
      );
    }
  }, [organizationId, runId]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setRuntime(initialWorkspaceRuntimeState());
      setConnection("disconnected");
      return;
    }
    const controller = new AbortController();
    void refreshCanonical();
    void connectRunEventStream({
      organizationId,
      agentRunId: runId,
      signal: controller.signal,
      initialLastEventId: runtime.lastEventId,
      onState: (state) => mounted.current && setConnection(state),
      onEvent: (event) => {
        if (!mounted.current) return;
        setRuntime((current) => reduceWorkspaceEvent(current, event));
      },
      onStreamEnd: async () => {
        await refreshCanonical();
      },
    });
    const poll = window.setInterval(() => void refreshCanonical(), 10_000);
    return () => {
      controller.abort();
      window.clearInterval(poll);
    };
    // lastEventId intentionally excluded: reconnect owns the cursor for this run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId, runId, refreshCanonical]);

  useEffect(() => {
    if (!selectedArtifact && runtime.artifacts.length > 0) {
      setSelectedArtifact(runtime.artifacts[runtime.artifacts.length - 1] ?? null);
    }
  }, [runtime.artifacts, selectedArtifact]);

  useEffect(() => {
    setCanvasSelection(null);
    setCanvasSaveState("saved");
  }, [selectedArtifact?.artifactVersionId]);

  const approval = useMemo(
    () => runtime.control?.interrupts.find((item) => item.kind === "approval" || item.kind === "review") ?? null,
    [runtime.control],
  );
  const status = runtime.control?.status ?? run?.status ?? (runId ? "loading" : "idle");
  const terminal = ["succeeded", "failed", "cancelled"].includes(status.toLowerCase());
  const canStop = runId !== null && !terminal;
  const canvasContextReady = selectedArtifact === null || canvasSaveState === "saved";

  async function submitGoal(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const command = goal.trim();
    if (!command || pending || !canvasContextReady) return;
    setPending("send");
    setNotice(null);
    try {
      const created = await createAgentRun(
        organizationId,
        project.id,
        { goal: command, selection: canvasSelection },
        crypto.randomUUID(),
      );
      setLastSubmittedGoal(command);
      setGoal("");
      setRun(created);
      setRunId(created.id);
      setRuntime(initialWorkspaceRuntimeState());
      router.replace(
        `/workspace?project=${encodeURIComponent(project.id)}&run=${encodeURIComponent(created.id)}`,
      );
    } catch (error) {
      setNotice(userMessage(error, "Could not start the agent run."));
    } finally {
      setPending(null);
    }
  }

  async function stopRun() {
    if (!runId || pending) return;
    setPending("stop");
    setNotice(null);
    try {
      await cancelAgentRun(organizationId, runId, crypto.randomUUID());
      await refreshCanonical();
      setNotice(
        "Cancellation requested. Provider work already accepted externally may still require reconciliation.",
      );
    } catch (error) {
      setNotice(userMessage(error, "Could not stop this run."));
    } finally {
      setPending(null);
    }
  }

  async function approve() {
    if (!runId || !approval || !runtime.control || pending) return;
    const expectedResumeVersion = runtime.control.resumeVersion;
    const expectedInterruptId = approval.id;
    setPending("approve");
    setNotice(null);
    try {
      const fresh = await getRunControl(organizationId, runId);
      const stillCurrent =
        fresh.resumeVersion === expectedResumeVersion &&
        fresh.interrupts.some((item) => item.id === expectedInterruptId && item.resumable);
      if (!stillCurrent) {
        setRuntime((current) => replaceCanonicalControl(current, fresh));
        setNotice("This approval became stale. The latest run state has been loaded.");
        return;
      }
      const resumed = await resumeAgentRun(organizationId, runId, {
        operationId: crypto.randomUUID(),
        resumeVersion: expectedResumeVersion,
        interruptId: expectedInterruptId,
        kind: "approval",
        value: { action: "approve" },
      });
      setRuntime((current) => replaceCanonicalControl(current, resumed));
    } catch (error) {
      setNotice(userMessage(error, "Approval could not be applied. The run may have changed."));
      await refreshCanonical();
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="ai-workspace" data-run-status={status}>
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AI Workspace</p>
          <h1>{project.name}</h1>
        </div>
        <div className="workspace-run-meta" aria-live="polite">
          <ConnectionBadge state={connection} />
          <span className="workspace-status-pill">{statusLabel(status)}</span>
          {selectedArtifact ? (
            <span className={`workspace-status-pill canvas-context-${canvasSaveState}`}>
              Canvas {canvasSaveState}
            </span>
          ) : null}
          {canStop ? (
            <button className="workspace-ghost-button" type="button" onClick={stopRun} disabled={pending !== null}>
              {pending === "stop" ? "Stopping…" : "Stop"}
            </button>
          ) : null}
        </div>
      </header>

      {notice ? <div className="workspace-notice" role="status">{notice}</div> : null}

      <div className="workspace-grid">
        <section className="workspace-chat-panel" aria-label="Agent conversation and progress">
          <div className="workspace-panel-heading">
            <div>
              <p className="eyebrow">Agent</p>
              <h2>Design run</h2>
            </div>
            {runId ? <code className="workspace-run-id">{shortId(runId)}</code> : null}
          </div>

          <div className="workspace-timeline" aria-live="polite" aria-relevant="additions text">
            {!runId && runtime.timeline.length === 0 ? (
              <WorkspaceWelcome project={project} />
            ) : null}
            {lastSubmittedGoal ? (
              <article className="workspace-message workspace-message-user">
                <span>You</span>
                <p>{lastSubmittedGoal}</p>
              </article>
            ) : null}
            {runtime.timeline.map((item) => (
              <article className={`workspace-event event-${item.kind}`} key={item.id}>
                <span>{timelineLabel(item.kind)}</span>
                <p>{item.text}</p>
              </article>
            ))}
            {approval && runtime.control ? (
              <ApprovalCard
                node={approval.node}
                resumeVersion={runtime.control.resumeVersion}
                pending={pending === "approve"}
                onApprove={approve}
              />
            ) : null}
          </div>

          <form className="workspace-composer" onSubmit={submitGoal}>
            {canvasSelection && canvasSelection.nodeIds.length ? (
              <div className="workspace-context-chip">
                {canvasSelection.nodeIds.length} selected · document v{canvasSelection.documentVersion}
              </div>
            ) : selectedArtifact && canvasSaveState !== "saved" ? (
              <div className="workspace-context-chip workspace-context-chip-warning">
                Save or resolve Canvas {canvasSaveState} before using selection in AI
              </div>
            ) : (
              <div className="workspace-context-chip workspace-context-chip-muted">
                No canvas selection
              </div>
            )}
            <label htmlFor="workspace-command" className="sr-only">Tell LUMI what to design</label>
            <textarea
              id="workspace-command"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder="Describe what you want to create or change…"
              rows={4}
              maxLength={20_000}
              disabled={pending !== null || canStop}
            />
            <div className="workspace-composer-footer">
              <span>
                {canStop
                  ? "Stop the current run before starting another command."
                  : !canvasContextReady
                    ? "Canvas changes must be saved before the selection can enter an Agent command."
                    : "Project and saved Canvas context are attached automatically."}
              </span>
              <button
                className="primary-button"
                type="submit"
                disabled={!goal.trim() || pending !== null || canStop || !canvasContextReady}
              >
                {pending === "send" ? "Starting…" : "Run agent"}
              </button>
            </div>
          </form>
        </section>

        <section className="workspace-canvas-panel" aria-label="Artifact canvas">
          <div className="workspace-panel-heading">
            <div>
              <p className="eyebrow">Canvas</p>
              <h2>{selectedArtifact ? selectedArtifact.label ?? "Artifact" : "Working surface"}</h2>
            </div>
            {selectedArtifact ? (
              <span className="workspace-version-badge">
                {selectedArtifact.versionNumber ? `artifact v${selectedArtifact.versionNumber}` : "exact artifact"}
              </span>
            ) : null}
          </div>
          <div className="workspace-stage">
            {selectedArtifact ? (
              <InfiniteCanvas
                organizationId={organizationId}
                artifactVersionId={selectedArtifact.artifactVersionId}
                onSelectionChange={setCanvasSelection}
                onSaveStateChange={setCanvasSaveState}
              />
            ) : (
              <div className="workspace-stage-empty">
                <span className="workspace-artifact-mark">+</span>
                <h3>Artifacts will appear here.</h3>
                <p>Only `artifact.created` events with an exact artifact version are admitted to the editable stage.</p>
              </div>
            )}
          </div>
          {runtime.artifacts.length ? (
            <div className="workspace-artifact-strip" aria-label="Run artifacts">
              {runtime.artifacts.map((artifact) => (
                <button
                  type="button"
                  key={artifact.artifactVersionId}
                  className={selectedArtifact?.artifactVersionId === artifact.artifactVersionId ? "is-selected" : ""}
                  onClick={() => setSelectedArtifact(artifact)}
                >
                  <span>{artifact.label ?? "Artifact"}</span>
                  <small>{artifact.versionNumber ? `v${artifact.versionNumber}` : shortId(artifact.artifactVersionId)}</small>
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <aside className="workspace-inspector" aria-label="Project and run context">
          <section>
            <p className="eyebrow">Project context</p>
            <h2>Brief</h2>
            <p>{project.objective || "No explicit objective recorded."}</p>
          </section>
          <InspectorList title="Deliverables" values={project.deliverables} />
          <InspectorList title="Constraints" values={project.constraints} />
          <section className="workspace-run-details">
            <p className="eyebrow">Run control</p>
            <dl>
              <div><dt>Status</dt><dd>{statusLabel(status)}</dd></div>
              <div><dt>Resume version</dt><dd>{runtime.control?.resumeVersion ?? "—"}</dd></div>
              <div><dt>Budget remaining</dt><dd>{runtime.control?.budgetRemaining ?? "—"}</dd></div>
              <div><dt>Artifacts</dt><dd>{runtime.artifacts.length}</dd></div>
              <div><dt>Canvas</dt><dd>{selectedArtifact ? canvasSaveState : "—"}</dd></div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}

function ApprovalCard({
  node,
  resumeVersion,
  pending,
  onApprove,
}: {
  node?: string | null;
  resumeVersion: number;
  pending: boolean;
  onApprove: () => void;
}) {
  return (
    <article className="workspace-approval-card">
      <span>Approval required</span>
      <h3>Review before the agent continues.</h3>
      <p>
        {node ? `Paused at ${node}. ` : "The run is paused. "}
        This decision is fenced to resume version {resumeVersion}; stale approvals are rejected and refreshed.
      </p>
      <button className="primary-button" type="button" onClick={onApprove} disabled={pending}>
        {pending ? "Approving…" : "Approve & continue"}
      </button>
    </article>
  );
}

function WorkspaceWelcome({ project }: { project: WorkspaceProject }) {
  return (
    <div className="workspace-welcome">
      <span className="workspace-artifact-mark">AI</span>
      <h3>Start from the project brief.</h3>
      <p>
        Give one clear instruction. LUMI will stream safe progress updates here; private reasoning is never displayed.
      </p>
      {project.objective ? <blockquote>{project.objective}</blockquote> : null}
    </div>
  );
}

function InspectorList({ title, values }: { title: string; values: readonly string[] }) {
  return (
    <section>
      <p className="eyebrow">{title}</p>
      {values.length ? (
        <ul className="workspace-inspector-list">
          {values.map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}
        </ul>
      ) : (
        <p className="workspace-muted">None recorded.</p>
      )}
    </section>
  );
}

function ConnectionBadge({ state }: { state: WorkspaceConnectionState }) {
  return <span className={`workspace-connection connection-${state}`}>{state}</span>;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function timelineLabel(kind: string): string {
  if (kind === "delta") return "Agent";
  if (kind === "approval") return "Approval";
  if (kind === "artifact") return "Artifact";
  if (kind === "warning") return "Warning";
  return "Progress";
}

function shortId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
}

function userMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.detail || error.title || fallback;
  return error instanceof Error ? error.message : fallback;
}
