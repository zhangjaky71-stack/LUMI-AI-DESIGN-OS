"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentTimeline } from "@/components/agent-timeline/agent-timeline";
import { useShell } from "@/components/app-shell/shell-context";
import { InfiniteCanvasProduct } from "@/components/infinite-canvas/infinite-canvas";
import { LayersInspector } from "@/components/layers-inspector/layers-inspector";
import { applyWorkspaceEvent, isApprovalActionable } from "@/lib/ai-workspace/contracts";
import { getAIWorkspaceGateway } from "@/lib/ai-workspace/workspace-gateway";
import type {
  AIWorkspaceBootstrap,
  AIWorkspaceSnapshot,
  ApprovalDecision,
  WorkspaceApproval,
  WorkspaceReducerState,
} from "@/lib/ai-workspace/types";
import type {
  CanvasSelectionContext,
  CanvasSyncState,
  InfiniteCanvasBootstrap,
} from "@/lib/infinite-canvas/types";
import type { CanvasEditorApi, CanvasEditorState } from "@/lib/layers-inspector/types";
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

export function AIWorkspace({
  projectId,
  bootstrap,
  canvasBootstrap,
}: Readonly<{
  projectId: string;
  bootstrap: AIWorkspaceBootstrap;
  canvasBootstrap: InfiniteCanvasBootstrap;
}>) {
  const { activeOrganization, api, queryCache } = useShell();
  const gateway = useMemo(() => getAIWorkspaceGateway(api, bootstrap), [api, bootstrap]);
  const [snapshot, setSnapshot] = useState<AIWorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [canvasDocumentVersion, setCanvasDocumentVersion] = useState(0);
  const [canvasSyncState, setCanvasSyncState] = useState<CanvasSyncState>("SAVED");
  const [canvasEditorState, setCanvasEditorState] = useState<CanvasEditorState | null>(null);
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[]>([]);
  const [artifactReferenceIds, setArtifactReferenceIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [streamState, setStreamState] = useState<"idle" | "connected" | "reconnecting" | "offline">("idle");
  const [mobilePanel, setMobilePanel] = useState<"agent" | "canvas" | "context">("agent");
  const [approvalNotes, setApprovalNotes] = useState<Record<string, string>>({});
  const streamAbortRef = useRef<AbortController | null>(null);
  const reducerRef = useRef<WorkspaceReducerState | null>(null);
  const canvasEditorRef = useRef<CanvasEditorApi | null>(null);

  const refreshCanonical = useCallback(async () => {
    const next = await queryCache.fetchQuery(
      ["ai-workspace", projectId],
      (signal) => gateway.getWorkspace(activeOrganization.id, projectId, signal),
      0,
    );
    reducerRef.current = { snapshot: next, seen_event_ids: [] };
    setSnapshot(next);
    setCanvasDocumentVersion((current) => current || next.document.version);
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
    if (canvasSyncState !== "SAVED") {
      setError(`Canvas 当前为 ${canvasSyncState}。请先完成 autosave / conflict 处理，再启动 AI Edit。`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await gateway.startRun(activeOrganization.id, {
        project_id: projectId,
        prompt,
        selected_node_ids: selectedNodeIds,
        document_version: canvasDocumentVersion || snapshot.document.version,
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
    setError(null);
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
      setCanvasDocumentVersion(next.document.version);
    } catch (placementError) {
      setError(uiError(placementError));
      queryCache.clear();
      void refreshCanonical();
    } finally {
      setBusy(false);
    }
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

  const handleCanvasContext = useCallback((context: CanvasSelectionContext) => {
    setSelectedNodeIds([...context.selected_node_ids]);
    setCanvasDocumentVersion(context.document_version);
    setCanvasSyncState(context.sync_state);
  }, []);

  const handleEditorState = useCallback((state: CanvasEditorState) => {
    setCanvasEditorState(state);
  }, []);

  const handleAIEdit = useCallback((nodeIds: readonly string[]) => {
    setSelectedNodeIds([...nodeIds]);
    setPrompt((current) => current || "针对当前选中对象进行 AI Edit：");
    setMobilePanel("agent");
  }, []);

  const handleJumpToCanvas = useCallback((artifactVersionId: string) => {
    setArtifactReferenceIds((current) =>
      current.includes(artifactVersionId) ? current : [...current, artifactVersionId],
    );
    setMobilePanel("canvas");
    canvasEditorRef.current?.fitSelection();
  }, []);

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
  const knownNodeIds = new Set(selectedNodes.map((node) => node.node_id));
  const unknownSelectedNodeIds = selectedNodeIds.filter((nodeId) => !knownNodeIds.has(nodeId));
  const effectiveDocumentVersion = canvasDocumentVersion || snapshot.document.version;
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

      <AgentTimeline
        snapshot={snapshot}
        busy={busy}
        artifactReferenceIds={artifactReferenceIds}
        approvalNotes={approvalNotes}
        onApprovalNoteChange={(approvalId, note) => setApprovalNotes((current) => ({ ...current, [approvalId]: note }))}
        onDecideApproval={(approval, decision) => void decideApproval(approval, decision)}
        onPlaceArtifact={(artifactId, versionId) => void placeArtifact(artifactId, versionId)}
        onToggleArtifactReference={toggleArtifactReference}
        onRetryTask={(taskId) => void retryTask(taskId)}
        onJumpToCanvas={handleJumpToCanvas}
      />

      <div className={styles.composer}>
        <div className={styles.contextChips}>
          <span>{selectedNodeIds.length} selected</span>
          <span>Document v{effectiveDocumentVersion}</span>
          <span>Canvas {canvasSyncState}</span>
          {selectedNodes.map((node) => <span key={node.node_id}>{node.label}{node.locked_identity ? " · locked identity" : ""}</span>)}
          {unknownSelectedNodeIds.map((nodeId) => <span key={nodeId}>{nodeId}</span>)}
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
          <span>⌘/Ctrl + Enter 发送 · Canvas 必须先完成保存 · 不展示内部推理</span>
          <button
            type="button"
            className={styles.primary}
            onClick={() => void startRun()}
            disabled={!prompt.trim() || busy || canvasSyncState !== "SAVED"}
          >
            Send
          </button>
        </div>
      </div>
    </section>
  );

  const canvasPanel = (
    <section className={styles.canvasPanel} aria-label="Canvas preview">
      <InfiniteCanvasProduct
        projectId={projectId}
        bootstrap={canvasBootstrap}
        references={snapshot.references}
        artifacts={snapshot.artifacts}
        editorRef={canvasEditorRef}
        onContextChange={handleCanvasContext}
        onEditorStateChange={handleEditorState}
        onAIEdit={handleAIEdit}
      />
    </section>
  );

  const contextPanel = (
    <LayersInspector
      state={canvasEditorState}
      editorRef={canvasEditorRef}
      brandName={snapshot.brand_name}
      references={snapshot.references}
      selectedReferenceIds={selectedReferenceIds}
      onToggleReference={toggleReference}
      onAIEdit={handleAIEdit}
    />
  );

  return (
    <div className={styles.workspace}>
      <header className={styles.workspaceHeader}>
        <div>
          <Link href={`/app/projects/${encodeURIComponent(projectId)}`}>← Project Brief</Link>
          <h1>{snapshot.project_name}</h1>
          <p>{snapshot.brand_name ?? "No Brand Kit"} · Timeline + Infinite Canvas + Layers / Inspector</p>
        </div>
        {error ? <p role="alert" className={styles.error}>{error}</p> : null}
      </header>

      <nav className={styles.mobileTabs} aria-label="移动工作区面板">
        <button type="button" data-active={mobilePanel === "agent"} onClick={() => setMobilePanel("agent")}>Agent</button>
        <button type="button" data-active={mobilePanel === "canvas"} onClick={() => setMobilePanel("canvas")}>Canvas</button>
        <button type="button" data-active={mobilePanel === "context"} onClick={() => setMobilePanel("context")}>Inspector</button>
      </nav>

      <main className={styles.desktopGrid}>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "agent"}>{agentPanel}</div>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "canvas"}>{canvasPanel}</div>
        <div className={styles.mobilePanel} data-mobile-active={mobilePanel === "context"}>{contextPanel}</div>
      </main>
    </div>
  );
}
