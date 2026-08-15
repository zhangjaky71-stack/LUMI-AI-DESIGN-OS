"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useShell } from "@/components/app-shell/shell-context";
import { applyWorkspaceEvent, isApprovalActionable } from "@/lib/ai-workspace/contracts";
import { getAIWorkspaceGateway } from "@/lib/ai-workspace/workspace-gateway";
import type {
  AIWorkspaceBootstrap,
  AIWorkspaceSnapshot,
  ApprovalDecision,
  WorkspaceApproval,
  WorkspaceReducerState,
} from "@/lib/ai-workspace/types";
import styles from "./ai-workspace.module.css";

const RUN_LABEL: Readonly<Record<string, string>> = {
  IDLE: "待开始",
  QUEUED: "排队中",
  RUNNING: "运行中",
  PAUSED: "已暂停",
  SUCCEEDED: "已完成",
  FAILED: "失败",
  CANCELED: "已停止",
};

function uiError(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "AI Workspace 操作失败，请重试。";
}

function money(microusd: string | null): string | null {
  if (!microusd) return null;
  const value = Number(microusd) / 1_000_000;
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : null;
}

export function AIWorkspace({
  projectId,
  bootstrap,
}: Readonly<{ projectId: string; bootstrap: AIWorkspaceBootstrap }>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getAIWorkspaceGateway(api, bootstrap), [api, bootstrap]);
  const [snapshot, setSnapshot] = useState<AIWorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[]>([]);
  const [artifactReferenceIds, setArtifactReferenceIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [streamState, setStreamState] = useState<"idle" | "connected" | "reconnecting" | "offline">("idle");
  const [mobilePanel, setMobilePanel] = useState<"agent" | "canvas" | "context">("agent");
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});
  const streamAbortRef = useRef<AbortController | null>(null);
  const reducerRef = useRef<WorkspaceReducerState | null>(null);

  const refreshCanonical = useCallback(async () => {
    const next = await queryCache.fetchQuery(
      ["ai-workspace", projectId],
      (signal) => gateway.getWorkspace(activeOrganization.id, projectId, signal),
      0,
    );
    reducerRef.current = { snapshot: next, seen_event_ids: [] };
    setSnapshot(next);
    return next;
  }, [activeOrganization.id, gateway, projectId, queryCache]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void refreshCanonical()
      .catch((loadError) => {
        if (!cancelled) setError(uiError(loadError));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      streamAbortRef.current?.abort();
    };
  }, [refreshCanonical]);

  const connectRun = useCallback(
    async (runId: string, initialLastEventId: string | null) => {
      let lastEventId = initialLastEventId;
      for (let attempt = 0; attempt < 4; attempt += 1) {
        const controller = new AbortController();
        streamAbortRef.current?.abort();
        streamAbortRef.current = controller;
        setStreamState(attempt === 0 ? "connected" : "reconnecting");
        try {
          await gateway.streamRun(activeOrganization.id, projectId, runId, {
            last_event_id: lastEventId,
            signal: controller.signal,
            on_event: (event) => {
              const current = reducerRef.current;
              if (!current) return;
              const next = applyWorkspaceEvent(current, event);
              reducerRef.current = next;
              lastEventId = next.snapshot.run?.last_event_id ?? event.id;
              setSnapshot(next.snapshot);
            },
          });
          await refreshCanonical();
          setStreamState("idle");
          return;
        } catch (streamError) {
          if (controller.signal.aborted) return;
          if (attempt === 3) {
            setStreamState("offline");
            setError(`实时连接中断：${uiError(streamError)}。页面中的状态可能不是最新值。`);
            return;
          }
        }
      }
    },
    [activeOrganization.id, gateway, projectId, refreshCanonical],
  );

  const startRun = async () => {
    if (!snapshot || !prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.startRun(activeOrganization.id, {
        project_id: projectId,
        prompt,
        selected_node_ids: selectedNodeIds,
        document_version: snapshot.document.version,
        reference_asset_ids: selectedReferenceIds,
        reference_artifact_version_ids: artifactReferenceIds,
      });
      setPrompt("");
      reducerRef.current = { snapshot: next, seen_event_ids: [] };
      setSnapshot(next);
      if (next.run) void connectRun(next.run.run_id, next.run.last_event_id);
    } catch (runError) {
      setError(uiError(runError));
    } finally {
      setBusy(false);
    }
  };

  const updateRun = async (action: "pause" | "resume" | "stop") => {
    if (!snapshot?.run || busy) return;
    setBusy(true);
    setError(null);
    const current = snapshot.run;
    if (action !== "resume") streamAbortRef.current?.abort();
    try {
      const input = { run_id: current.run_id, expected_run_version: current.version };
      const run =
        action === "pause"
          ? await gateway.pauseRun(activeOrganization.id, input)
          : action === "resume"
            ? await gateway.resumeRun(activeOrganization.id, input)
            : await gateway.stopRun(activeOrganization.id, input);
      const next = { ...snapshot, run };
      reducerRef.current = { snapshot: next, seen_event_ids: reducerRef.current?.seen_event_ids ?? [] };
      setSnapshot(next);
      if (action === "resume") void connectRun(run.run_id, run.last_event_id);
    } catch (runError) {
      setError(uiError(runError));
      queryCache.clear();
      void refreshCanonical();
    } finally {
      setBusy(false);
    }
  };

  const retryTask = async (taskId: string) => {
    if (!snapshot?.run || busy) return;
    setBusy(true);
    try {
      const run = await gateway.retryTask(activeOrganization.id, {
        run_id: snapshot.run.run_id,
        expected_run_version: snapshot.run.version,
        task_id: taskId,
      });
      const next = { ...snapshot, run };
      setSnapshot(next);
      reducerRef.current = { snapshot: next, seen_event_ids: reducerRef.current?.seen_event_ids ?? [] };
      void connectRun(run.run_id, run.last_event_id);
    } catch (retryError) {
      setError(uiError(retryError));
      void refreshCanonical();
    } finally {
      setBusy(false);
    }
  };

  const decideApproval = async (approval: WorkspaceApproval, decision: ApprovalDecision) => {
    if (!snapshot?.run || busy || !isApprovalActionable(approval, snapshot.run)) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.decideApproval(activeOrganization.id, {
        approval_id: approval.approval_id,
        run_id: approval.run_id,
        expected_run_version: approval.expected_run_version,
        decision,
        request_changes_note: decision === "REQUEST_CHANGES" ? approvalNotes[approval.approval_id] ?? null : null,
      });
      reducerRef.current = { snapshot: next, seen_event_ids: reducerRef.current?.seen_event_ids ?? [] };
      setSnapshot(next);
    } catch (approvalError) {
      setError(uiError(approvalError));
      queryCache.clear();
      void refreshCanonical();
    } finally {
      setBusy(false);
    }
  };

  const placeArtifact = async (artifactId: string, versionId: string) => {
    if (!snapshot || busy) return;
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.placeArtifact(activeOrganization.id, {
        project_id: projectId,
        document_id: snapshot.document.document_id,
        expected_document_version: snapshot.document.version,
        artifact_id: artifactId,
        artifact_version_id: versionId,
      });
      reducerRef.current = { snapshot: next, seen_event_ids: reducerRef.current?.seen_event_ids ?? [] };
      setSnapshot(next);
    } catch (placementError) {
      setError(uiError(placementError));
      queryCache.clear();
      void refreshCanonical();
    } finally {
      setBusy(false);
    }
  };

  const toggleNode = (nodeId: string) => {
    setSelectedNodeIds((current) =>
      current.includes(nodeId) ? current.filter((value) => value !== nodeId) : [...current, nodeId],
    );
  };

  const toggleReference = (assetId: string) => {
    setSelectedReferenceIds((current) =>
      current.includes(assetId) ? current.filter((value) => value !== assetId) : [...current, assetId],
    );
  };

  const toggleArtifactReference = (versionId: string) => {
    setArtifactReferenceIds((current) =>
      current.includes(versionId) ? current.filter((value) => value !== versionId) : [...current, versionId],
    );
  };

  if (loading) return <div className={styles.loading}>正在加载 AI Workspace…</div>;
  if (!snapshot) {
    return (
      <div className={styles.loading} role="alert">
        <p>{error ?? "无法打开 AI Workspace。"}</p>
        <Link href={`/app/projects/${encodeURIComponent(projectId)}`}>返回项目</Link>
      </div>
    );
  }

  const selectedNodes = snapshot.document.selection_options.filter((node) => selectedNodeIds.includes(node.node_id));
  const run = snapshot.run;
  const runLabel = run ? RUN_LABEL[run.status] ?? run.status : "待开始";

  const agentPanel = (
    <section className={styles.agentPanel} aria-label="Agent 对话与运行">
      <div className={styles.panelHeader}>
        <div><span className={styles.eyebrow}>LUMI AGENT</span><h2>Design Copilot</h2></div>
        <span className={styles.connection} data-state={streamState}>{streamState === "offline" ? "Offline" : streamState === "reconnecting" ? "Reconnecting" : "Live"}</span>
      </div>

      <div className={styles.runBar}>
        <strong>{runLabel}</strong>
        {run ? <span>Run v{run.version}</span> : null}
        <div className={styles.runActions}>
          {run?.status === "RUNNING" ? <button type="button" onClick={() => void updateRun("pause")} disabled={busy}>暂停</button> : null}
          {run?.status === "PAUSED" ? <button type="button" onClick={() => void updateRun("resume")} disabled={busy}>Resume</button> : null}
          {run && ["RUNNING", "PAUSED", "QUEUED"].includes(run.status) ? <button type="button" onClick={() => void updateRun("stop")} disabled={busy}>Stop</button> : null}
        </div>
      </div>

      <div className={styles.messages} aria-live="polite">
        {snapshot.messages.map((message) => (
          <article key={message.id} className={styles.message} data-kind={message.kind}>
            <span>{message.kind}</span>
            <p>{message.text}</p>
          </article>
        ))}

        {snapshot.artifacts.map((artifact) => (
          <article key={artifact.version_id} className={styles.artifactCard}>
            <div className={styles.artifactPreview}>{artifact.preview_label}</div>
            <div>
              <span className={styles.eyebrow}>ARTIFACT · v{artifact.version}</span>
              <h3>{artifact.title}</h3>
              <p>绑定精确版本 {artifact.version_id}</p>
              <div className={styles.cardActions}>
                <button type="button" onClick={() => void placeArtifact(artifact.artifact_id, artifact.version_id)} disabled={busy}>放到 Canvas</button>
                <button type="button" onClick={() => toggleArtifactReference(artifact.version_id)} aria-pressed={artifactReferenceIds.includes(artifact.version_id)}>作为参考</button>
                <button type="button" disabled title="NODE-59 Artifact compare">Compare</button>
              </div>
            </div>
          </article>
        ))}

        {snapshot.approvals.map((approval) => {
          const actionable = isApprovalActionable(approval, run);
          const stale = !actionable && approval.state !== "APPROVED" && approval.state !== "REJECTED" && approval.state !== "CHANGES_REQUESTED";
          return (
            <article key={approval.approval_id} className={styles.approvalCard}>
              <div className={styles.approvalHeading}>
                <div><span className={styles.eyebrow}>APPROVAL</span><h3>{approval.title}</h3></div>
                <strong>{stale ? "已过期" : approval.state}</strong>
              </div>
              <p>{approval.description}</p>
              {approval.impact ? <p className={styles.muted}>{approval.impact}</p> : null}
              {money(approval.estimated_cost_microusd) ? <p>预计增量成本 {money(approval.estimated_cost_microusd)}</p> : null}
              {stale ? <p className={styles.staleNote}>旧审批不会被提交；请以当前 Run 的 canonical state 为准。</p> : null}
              {approval.state === "PENDING" ? (
                <>
                  <textarea
                    aria-label={`${approval.title} 修改意见`}
                    placeholder="需要修改时填写具体要求"
                    value={approvalNotes[approval.approval_id] ?? ""}
                    onChange={(event) => setApprovalNotes((current) => ({ ...current, [approval.approval_id]: event.target.value }))}
                    disabled={!actionable}
                  />
                  <div className={styles.cardActions}>
                    <button type="button" onClick={() => void decideApproval(approval, "APPROVE")} disabled={!actionable || busy}>Approve</button>
                    <button type="button" onClick={() => void decideApproval(approval, "REJECT")} disabled={!actionable || busy}>Reject</button>
                    <button type="button" onClick={() => void decideApproval(approval, "REQUEST_CHANGES")} disabled={!actionable || busy}>Request Changes</button>
                  </div>
                </>
              ) : null}
            </article>
          );
        })}
      </div>

      {run?.tasks.some((task) => task.status === "FAILED" && task.retryable) ? (
        <div className={styles.retryList}>
          {run.tasks.filter((task) => task.status === "FAILED" && task.retryable).map((task) => (
            <button key={task.task_id} type="button" onClick={() => void retryTask(task.task_id)}>Retry {task.label}</button>
          ))}
        </div>
      ) : null}

      <div className={styles.composer}>
        <div className={styles.contextChips}>
          <span>{selectedNodeIds.length} selected</span>
          <span>Document v{snapshot.document.version}</span>
          {selectedNodes.map((node) => <span key={node.node_id}>{node.label}{node.locked_identity ? " · locked identity" : ""}</span>)}
          {selectedReferenceIds.length ? <span>{selectedReferenceIds.length} references</span> : null}
          {artifactReferenceIds.length ? <span>{artifactReferenceIds.length} artifact refs</span> : null}
        </div>
        <textarea
          aria-label="给 LUMI Agent 的指令"
          placeholder="例如：只改选中的标题与构图，产品身份保持不变…"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") void startRun();
          }}
        />
        <div className={styles.composerFooter}>
          <span>⌘/Ctrl + Enter 发送 · 不展示内部推理</span>
          <button type="button" className={styles.primary} onClick={() => void startRun()} disabled={!prompt.trim() || busy}>Send</button>
        </div>
      </div>
    </section>
  );

  const canvasPanel = (
    <section className={styles.canvasPanel} aria-label="Canvas preview">
      <div className={styles.panelHeader}>
        <div><span className={styles.eyebrow}>CANVAS</span><h2>{snapshot.document.title}</h2></div>
        <span>Document v{snapshot.document.version}</span>
      </div>
      <div className={styles.canvasStage}>
        <div className={styles.artboard} style={{ aspectRatio: `${snapshot.document.width}/${snapshot.document.height}` }}>
          <span className={styles.artboardLabel}>Summer / Product Launch</span>
          {snapshot.document.selection_options.map((node, index) => (
            <button
              key={node.node_id}
              type="button"
              className={styles.canvasNode}
              data-selected={selectedNodeIds.includes(node.node_id)}
              style={{ top: `${18 + index * 23}%`, left: `${16 + (index % 2) * 18}%` }}
              aria-pressed={selectedNodeIds.includes(node.node_id)}
              onClick={() => toggleNode(node.node_id)}
            >
              {node.label}{node.locked_identity ? " · locked identity" : ""}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.canvasFooter}>NODE-54 提供选择、上下文和 Artifact placement；Infinite Canvas 编辑能力在 NODE-55。</div>
    </section>
  );

  const contextPanel = (
    <aside className={styles.contextPanel} aria-label="Inspector 与 Context">
      <div className={styles.panelHeader}><div><span className={styles.eyebrow}>CONTEXT</span><h2>Inspector</h2></div></div>
      <section className={styles.inspectorSection}>
        <h3>Selection</h3>
        <p>{selectedNodeIds.length} selected · Document v{snapshot.document.version}</p>
        {selectedNodes.map((node) => (
          <div key={node.node_id} className={styles.contextRow}>
            <strong>{node.label}</strong><span>{node.kind}{node.locked_identity ? " · locked identity" : ""}</span>
          </div>
        ))}
      </section>
      <section className={styles.inspectorSection}>
        <h3>Project context</h3>
        <p>Brand Kit: {snapshot.brand_name ?? "未绑定"}</p>
        {snapshot.references.map((reference) => (
          <label key={reference.id} className={styles.referenceRow}>
            <input
              type="checkbox"
              checked={selectedReferenceIds.includes(reference.asset_id)}
              onChange={() => toggleReference(reference.asset_id)}
              disabled={reference.scan_status !== "READY"}
            />
            <span><strong>{reference.file_name}</strong><small>{reference.role} · {reference.scan_status}</small></span>
          </label>
        ))}
      </section>
      <section className={styles.inspectorSection}>
        <h3>Context transparency</h3>
        <p>本次命令会明确携带选中 node IDs、Document version、READY reference IDs 与精确 ArtifactVersion IDs。</p>
        <p className={styles.privacy}>界面只展示安全的计划/进展摘要，不会暴露 system prompt 或内部 chain-of-thought。</p>
      </section>
    </aside>
  );

  return (
    <div className={styles.workspace}>
      <header className={styles.workspaceHeader}>
        <div>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}`}>← Project Brief</Link>
          <h1>{snapshot.project_name}</h1>
          <p>{snapshot.brand_name ?? "No Brand Kit"} · Chat + Canvas + Approval</p>
        </div>
        {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      </header>

      <nav className={styles.mobileTabs} aria-label="移动工作区面板">
        <button type="button" data-active={mobilePanel === "agent"} onClick={() => setMobilePanel("agent")}>Agent</button>
        <button type="button" data-active={mobilePanel === "canvas"} onClick={() => setMobilePanel("canvas")}>Canvas</button>
        <button type="button" data-active={mobilePanel === "context"} onClick={() => setMobilePanel("context")}>Context</button>
      </nav>

      <main className={styles.desktopGrid}>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "agent"}>{agentPanel}</div>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "canvas"}>{canvasPanel}</div>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "context"}>{contextPanel}</div>
      </main>
    </div>
  );
}
