"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CanvasController,
  type OperationDescriptor,
  type TransformSession,
} from "@lumi/canvas-sdk";
import type { DesignNode } from "@lumi/design-ir";

import { ApiError } from "@/lib/api/problem";
import { getArtifactCanvas, getCanvasHead } from "@/lib/canvas/api";
import { SvgCanvasRenderer } from "@/lib/canvas/svg-renderer";
import type { CanvasProjection, CanvasSaveState } from "@/lib/canvas/types";
import { useCanvasAutosave } from "@/lib/canvas/use-autosave";
import { newUuid7 } from "@/lib/canvas/uuid7";
import type { CanvasSelectionContext } from "@/lib/workspace/types";

const FRAME_PRESETS = [
  { label: "1:1", width: 1080, height: 1080 },
  { label: "4:5", width: 1080, height: 1350 },
  { label: "9:16", width: 1080, height: 1920 },
  { label: "16:9", width: 1920, height: 1080 },
  { label: "A4", width: 1240, height: 1754 },
] as const;

type Gesture =
  | { kind: "pan"; x: number; y: number }
  | { kind: "move"; x: number; y: number; session: TransformSession }
  | null;

export function InfiniteCanvas({
  organizationId,
  artifactVersionId,
  onSelectionChange,
  onSaveStateChange,
}: {
  organizationId: string;
  artifactVersionId: string;
  onSelectionChange?: (selection: CanvasSelectionContext | null) => void;
  onSaveStateChange?: (state: CanvasSaveState) => void;
}) {
  const [projection, setProjection] = useState<CanvasProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setProjection(null);
    void getArtifactCanvas(organizationId, artifactVersionId)
      .then((value) => {
        if (!controller.signal.aborted) setProjection(value);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setError("This exact artifact version has no editable DesignDocument projection.");
        } else {
          setError(reason instanceof Error ? reason.message : "Canvas could not be loaded.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [artifactVersionId, organizationId]);

  if (loading) {
    return <CanvasStatus title="Loading canvas…" detail="Resolving the exact DesignDocumentVersion." />;
  }
  if (!projection) {
    return <CanvasStatus title="Canvas unavailable" detail={error ?? "No editable document is attached."} />;
  }
  return (
    <CanvasEditor
      key={`${artifactVersionId}:${projection.designDocumentVersionId}`}
      organizationId={organizationId}
      initialProjection={projection}
      onSelectionChange={onSelectionChange}
      onSaveStateChange={onSaveStateChange}
    />
  );
}

function CanvasEditor({
  organizationId,
  initialProjection,
  onSelectionChange,
  onSaveStateChange,
}: {
  organizationId: string;
  initialProjection: CanvasProjection;
  onSelectionChange?: (selection: CanvasSelectionContext | null) => void;
  onSaveStateChange?: (state: CanvasSaveState) => void;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const controllerRef = useRef<CanvasController | null>(null);
  const rendererRef = useRef<SvgCanvasRenderer | null>(null);
  const gestureRef = useRef<Gesture>(null);
  const spaceRef = useRef(false);
  const enqueueRef = useRef<(descriptors: readonly OperationDescriptor[]) => boolean>(() => false);
  const [projection, setProjection] = useState(initialProjection);
  const [selectionIds, setSelectionIds] = useState<readonly string[]>([]);
  const [zoom, setZoom] = useState(1);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);
  const [localNotice, setLocalNotice] = useState<string | null>(null);

  const adoptCanonical = useCallback((next: CanvasProjection, queueDrained: boolean) => {
    setProjection(next);
    if (queueDrained) {
      controllerRef.current?.replaceDocument(next.document);
      controllerRef.current?.renderNow();
    }
  }, []);

  const autosave = useCanvasAutosave({
    organizationId,
    initialProjection,
    onCanonicalProjection: adoptCanonical,
  });
  enqueueRef.current = autosave.enqueue;

  useEffect(() => {
    onSaveStateChange?.(autosave.saveState);
    if (autosave.saveState !== "saved" || selectionIds.length === 0) {
      onSelectionChange?.(null);
      return;
    }
    onSelectionChange?.({
      documentVersion: projection.revision,
      nodeIds: selectionIds,
    });
  }, [autosave.saveState, onSaveStateChange, onSelectionChange, projection.revision, selectionIds]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const renderer = new SvgCanvasRenderer(svg);
    rendererRef.current = renderer;
    const controller = new CanvasController(initialProjection.document, renderer, {
      viewport: { width: Math.max(1, svg.clientWidth), height: Math.max(1, svg.clientHeight), dpr: window.devicePixelRatio || 1 },
      onOperationCommitted: (descriptors) => {
        if (!enqueueRef.current(descriptors)) {
          setLocalNotice("Canvas queue is paused. Reload or reconnect before making more edits.");
        }
      },
    });
    controllerRef.current = controller;
    void controller.mount().then(() => {
      controller.fitAll();
      setZoom(controller.camera.state.zoom);
    });
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      controller.setViewport({ width: Math.max(1, width), height: Math.max(1, height), dpr: window.devicePixelRatio || 1 });
    });
    observer.observe(svg);
    return () => {
      observer.disconnect();
      controller.destroy();
      controllerRef.current = null;
      rendererRef.current = null;
    };
  }, [initialProjection]);

  const syncSelection = useCallback(() => {
    const controller = controllerRef.current;
    if (!controller) return;
    setSelectionIds([...controller.selection.ids]);
  }, []);

  const commit = useCallback((descriptor: OperationDescriptor): boolean => {
    const controller = controllerRef.current;
    if (!controller || !autosave.canEdit) return false;
    const result = controller.commit(descriptor);
    if (!result.ok) {
      setLocalNotice(result.error?.message ?? "Canvas operation was rejected locally.");
      return false;
    }
    setLocalNotice(null);
    syncSelection();
    return true;
  }, [autosave.canEdit, syncSelection]);

  const createFrame = useCallback((preset: (typeof FRAME_PRESETS)[number]) => {
    const controller = controllerRef.current;
    if (!controller || !autosave.canEdit) return;
    const viewport = controller.camera.viewport;
    const center = controller.camera.screenToWorld({ x: viewport.width / 2, y: viewport.height / 2 });
    const id = newUuid7();
    const node: DesignNode = {
      id,
      kind: "FRAME",
      name: `${preset.label} Frame`,
      parent_id: projection.activePageId,
      children: [],
      visible: true,
      locked: false,
      opacity: 1,
      transform: {
        x: center.x - preset.width / 2,
        y: center.y - preset.height / 2,
        width: preset.width,
        height: preset.height,
        rotation_deg: 0,
        scale_x: 1,
        scale_y: 1,
      },
      semantic: { tags: ["frame"] },
      metadata: { source_kind: "frame" },
    };
    if (commit({
      type: "CREATE_NODE",
      targetIds: [],
      payload: { node },
      reason: `create ${preset.label} frame`,
    })) {
      controller.selection.set([id]);
      controller.renderNow();
      syncSelection();
    }
  }, [autosave.canEdit, commit, projection.activePageId, syncSelection]);

  const reloadCanonical = useCallback(async () => {
    try {
      const latest = await getCanvasHead(organizationId, projection.designDocumentId);
      autosave.adoptProjection(latest);
      setProjection(latest);
      controllerRef.current?.replaceDocument(latest.document);
      controllerRef.current?.selection.clear();
      controllerRef.current?.fitAll();
      setSelectionIds([]);
      setLocalNotice("Canonical document reloaded. Unsaved local edits were discarded by explicit choice.");
    } catch (error) {
      setLocalNotice(error instanceof Error ? error.message : "Could not reload canonical document.");
    }
  }, [autosave, organizationId, projection.designDocumentId]);

  const onPointerDown = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
    const controller = controllerRef.current;
    if (!controller) return;
    setContextMenu(null);
    const point = localPoint(event);
    if (event.button === 1 || spaceRef.current) {
      event.currentTarget.setPointerCapture(event.pointerId);
      gestureRef.current = { kind: "pan", x: event.clientX, y: event.clientY };
      return;
    }
    if (event.button !== 0) return;
    const selected = controller.selectAt(point, { shift: event.shiftKey });
    syncSelection();
    if (!selected || event.shiftKey || !autosave.canEdit) return;
    const ids = controller.selection.transformable(controller.scene);
    if (!ids.length) return;
    try {
      const session = controller.beginTransform("move", ids);
      event.currentTarget.setPointerCapture(event.pointerId);
      gestureRef.current = { kind: "move", x: event.clientX, y: event.clientY, session };
    } catch (error) {
      setLocalNotice(error instanceof Error ? error.message : "Selection cannot be moved.");
    }
  }, [autosave.canEdit, syncSelection]);

  const onPointerMove = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
    const controller = controllerRef.current;
    const gesture = gestureRef.current;
    if (!controller || !gesture) return;
    if (gesture.kind === "pan") {
      const dx = event.clientX - gesture.x;
      const dy = event.clientY - gesture.y;
      controller.pan(dx, dy);
      gestureRef.current = { kind: "pan", x: event.clientX, y: event.clientY };
      return;
    }
    const zoomValue = controller.camera.state.zoom;
    const preview = gesture.session.update({
      dx: (event.clientX - gesture.x) / zoomValue,
      dy: (event.clientY - gesture.y) / zoomValue,
    });
    rendererRef.current?.previewBounds(preview.bounds, controller.camera.state);
  }, []);

  const finishPointer = useCallback((event: React.PointerEvent<SVGSVGElement>) => {
    const controller = controllerRef.current;
    const gesture = gestureRef.current;
    if (!controller || !gesture) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (gesture.kind === "move") {
      const result = gesture.session.commit();
      controller.syncAfterExternalCommit();
      if (!result.ok) setLocalNotice(result.error?.message ?? "Move was rejected.");
      syncSelection();
    }
    gestureRef.current = null;
  }, [syncSelection]);

  const onWheel = useCallback((event: React.WheelEvent<SVGSVGElement>) => {
    const controller = controllerRef.current;
    if (!controller) return;
    event.preventDefault();
    const point = localPoint(event);
    const next = controller.camera.state.zoom * Math.exp(-event.deltaY * 0.0015);
    controller.zoomToCursor(point, next);
    setZoom(controller.camera.state.zoom);
  }, []);

  const onKeyDown = useCallback((event: React.KeyboardEvent<SVGSVGElement>) => {
    const controller = controllerRef.current;
    if (!controller) return;
    if (event.code === "Space") {
      spaceRef.current = true;
      event.preventDefault();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "0") {
      event.preventDefault();
      controller.fitAll();
      setZoom(controller.camera.state.zoom);
      return;
    }
    if (event.key === "Escape") {
      controller.selection.clear();
      controller.renderNow();
      syncSelection();
      setContextMenu(null);
      return;
    }
    if ((event.key === "Delete" || event.key === "Backspace") && autosave.canEdit) {
      const ids = [...controller.selection.ids];
      if (!ids.length) return;
      event.preventDefault();
      if (commit({ type: "DELETE_NODE", targetIds: ids, payload: {}, reason: "canvas delete" })) {
        controller.selection.clear();
        syncSelection();
      }
      return;
    }
    if (event.key.toLowerCase() === "l" && autosave.canEdit && controller.selection.ids.size) {
      const selected = [...controller.selection.ids];
      const shouldLock = selected.some((id) => controller.scene.nodes.get(id)?.locked !== true);
      commit({
        type: "SET_PROPERTY",
        targetIds: selected,
        payload: { property: "locked", value: shouldLock },
        reason: shouldLock ? "lock selection" : "unlock selection",
      });
    }
  }, [autosave.canEdit, commit, syncSelection]);

  const onContextMenu = useCallback((event: React.MouseEvent<SVGSVGElement>) => {
    event.preventDefault();
    const controller = controllerRef.current;
    if (!controller) return;
    controller.selectAt(localPoint(event), { shift: false });
    syncSelection();
    setContextMenu({ x: event.nativeEvent.offsetX, y: event.nativeEvent.offsetY });
  }, [syncSelection]);

  const selectedLocked = useMemo(() => {
    const controller = controllerRef.current;
    if (!controller || !selectionIds.length) return false;
    return selectionIds.every((id) => controller.scene.nodes.get(id)?.locked === true);
  }, [selectionIds]);

  return (
    <div className="infinite-canvas" data-save-state={autosave.saveState}>
      <div className="canvas-toolbar" aria-label="Canvas toolbar">
        <div className="canvas-toolbar-group">
          {FRAME_PRESETS.map((preset) => (
            <button key={preset.label} type="button" onClick={() => createFrame(preset)} disabled={!autosave.canEdit}>
              + {preset.label}
            </button>
          ))}
        </div>
        <div className="canvas-toolbar-group canvas-toolbar-group-right">
          <span className={`canvas-save-badge save-${autosave.saveState}`}>
            {saveLabel(autosave.saveState, autosave.pendingCount)}
          </span>
          <button type="button" onClick={() => controllerRef.current?.fitAll()}>Fit</button>
          <span className="canvas-zoom">{Math.round(zoom * 100)}%</span>
        </div>
      </div>

      {(autosave.message || localNotice) ? (
        <div className="canvas-inline-notice" role="status">
          <span>{autosave.message ?? localNotice}</span>
          {autosave.saveState === "conflict" ? (
            <button type="button" onClick={reloadCanonical}>Reload canonical</button>
          ) : autosave.saveState === "offline" || autosave.saveState === "error" ? (
            <button type="button" onClick={autosave.retry}>Retry save</button>
          ) : null}
        </div>
      ) : null}

      <div className="canvas-viewport-wrap">
        <svg
          ref={svgRef}
          className="canvas-svg"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={finishPointer}
          onPointerCancel={finishPointer}
          onWheel={onWheel}
          onKeyDown={onKeyDown}
          onKeyUp={(event) => { if (event.code === "Space") spaceRef.current = false; }}
          onBlur={() => { spaceRef.current = false; }}
          onContextMenu={onContextMenu}
        />
        {contextMenu ? (
          <div className="canvas-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }} role="menu">
            <button
              type="button"
              role="menuitem"
              disabled={!selectionIds.length || !autosave.canEdit}
              onClick={() => {
                const controller = controllerRef.current;
                if (!controller) return;
                commit({
                  type: "SET_PROPERTY",
                  targetIds: selectionIds,
                  payload: { property: "locked", value: !selectedLocked },
                  reason: selectedLocked ? "unlock selection" : "lock selection",
                });
                setContextMenu(null);
              }}
            >
              {selectedLocked ? "Unlock" : "Lock"}
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={!selectionIds.length || !autosave.canEdit || selectedLocked}
              onClick={() => {
                if (commit({ type: "DELETE_NODE", targetIds: selectionIds, payload: {}, reason: "context delete" })) {
                  controllerRef.current?.selection.clear();
                  syncSelection();
                }
                setContextMenu(null);
              }}
            >
              Delete
            </button>
            <button type="button" role="menuitem" onClick={() => setContextMenu(null)}>
              Use selection in AI
            </button>
          </div>
        ) : null}
      </div>

      <footer className="canvas-statusbar">
        <span>{selectionIds.length ? `${selectionIds.length} selected` : "No selection"}</span>
        <span>document v{projection.revision} · saved version {projection.versionNumber}</span>
        <span>Space/middle drag to pan · wheel to zoom · L lock · Delete remove</span>
      </footer>
    </div>
  );
}

function CanvasStatus({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="canvas-status-card" role="status">
      <span className="workspace-artifact-mark">CAN</span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function localPoint(event: { clientX: number; clientY: number; currentTarget: SVGSVGElement }) {
  const rect = event.currentTarget.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function saveLabel(state: CanvasSaveState, pending: number): string {
  if (state === "saved") return "Saved";
  if (state === "saving") return `Saving ${pending}`;
  if (state === "dirty") return `${pending} unsaved`;
  if (state === "offline") return `Offline · ${pending} queued`;
  if (state === "conflict") return "Conflict";
  return "Save error";
}
