"use client";

/* eslint-disable react-hooks/exhaustive-deps -- CanvasController is an imperative runtime; global shortcut and observer bridges intentionally read current refs. */

import {
  CanvasController,
  invertOperations,
  screenToWorld,
  type CanvasRuntimeSnapshot,
  type CanvasSceneNode,
  type CanvasTransformSession,
} from "@lumi/canvas-sdk";
import {
  executeOperations,
  getDocumentVersion,
  type DesignDocument,
  type DesignNode,
  type DesignOperation,
} from "@lumi/design-ir";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { useShell } from "@/components/app-shell/shell-context";
import type { WorkspaceArtifact } from "@/lib/ai-workspace/types";
import { LumiApiError } from "@/lib/app-shell/api-client";
import type { ProjectReference } from "@/lib/projects/types";
import { CanvasAutosaveBuffer, rebaseOperationsVersion } from "@/lib/infinite-canvas/autosave";
import { getInfiniteCanvasGateway } from "@/lib/infinite-canvas/canvas-gateway";
import { cullSceneNodes } from "@/lib/infinite-canvas/viewport";
import type {
  CanvasSelectionContext,
  CanvasSyncState,
  FramePreset,
  InfiniteCanvasBootstrap,
} from "@/lib/infinite-canvas/types";
import styles from "./infinite-canvas.module.css";

const PRESETS: readonly FramePreset[] = [
  { id: "1:1", width: 1080, height: 1080, label: "Square" },
  { id: "4:5", width: 1080, height: 1350, label: "Feed" },
  { id: "9:16", width: 1080, height: 1920, label: "Story" },
  { id: "16:9", width: 1920, height: 1080, label: "Wide" },
  { id: "A4", width: 2480, height: 3508, label: "A4" },
];

type Tool = "select" | "hand";

interface HistoryEntry {
  readonly forward: readonly DesignOperation[];
  readonly inverse: readonly DesignOperation[];
}

interface DragSession {
  readonly pointerId: number;
  readonly startX: number;
  readonly startY: number;
  readonly transform: CanvasTransformSession;
  readonly before: DesignDocument;
  readonly nodeIds: readonly string[];
}

interface PanSession {
  readonly pointerId: number;
  readonly x: number;
  readonly y: number;
}

interface ContextMenuState {
  readonly x: number;
  readonly y: number;
  readonly nodeId: string;
}

interface Props {
  readonly projectId: string;
  readonly bootstrap: InfiniteCanvasBootstrap;
  readonly references: readonly ProjectReference[];
  readonly artifacts: readonly WorkspaceArtifact[];
  readonly onContextChange: (context: CanvasSelectionContext) => void;
  readonly onAIEdit: (nodeIds: readonly string[]) => void;
}

function errorMessage(error: unknown): string {
  if (error instanceof LumiApiError) return error.problem.code;
  return error instanceof Error ? error.message : "CANVAS_OPERATION_FAILED";
}

function isConflict(error: unknown): boolean {
  return error instanceof LumiApiError && error.problem.code === "DOCUMENT_VERSION_CONFLICT";
}

function metaString(node: CanvasSceneNode, key: string): string | null {
  const value = node.metadata[key];
  return typeof value === "string" ? value : null;
}

function metaNumber(node: CanvasSceneNode, key: string): number | null {
  const value = node.metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function frameParentAt(snapshot: CanvasRuntimeSnapshot, x: number, y: number): string {
  const hit = [...snapshot.scene.frame_ids]
    .reverse()
    .map((id) => snapshot.scene.nodes.get(id))
    .find((node) => {
      if (!node) return false;
      const b = node.world_bounds;
      return x >= b.x && x <= b.x + b.width && y >= b.y && y <= b.y + b.height;
    });
  return hit?.id ?? snapshot.document.root_id;
}

function duplicateOperations(
  document: DesignDocument,
  sourceIds: readonly string[],
  version: number,
): DesignOperation[] {
  const selected = new Set(sourceIds);
  const roots = sourceIds.filter((id) => {
    if (!document.nodes[id] || id === document.root_id) return false;
    let parent = document.nodes[id]?.parent_id ?? null;
    while (parent) {
      if (selected.has(parent)) return false;
      parent = document.nodes[parent]?.parent_id ?? null;
    }
    return true;
  });
  const suffix = crypto.randomUUID().slice(0, 8);
  const mapping = new Map<string, string>();
  const indexTree = (id: string): void => {
    const node = document.nodes[id];
    if (!node) return;
    mapping.set(id, `${id}-copy-${suffix}-${mapping.size}`);
    node.children.forEach(indexTree);
  };
  roots.forEach(indexTree);

  const operations: DesignOperation[] = [];
  let sequence = 0;
  const cloneNode = (id: string, parentOverride?: string): void => {
    const source = document.nodes[id];
    const nextId = mapping.get(id);
    if (!source || !nextId) return;
    const parentId = parentOverride ?? source.parent_id;
    if (!parentId) return;
    const sourceTransform = source.transform ?? {};
    const node: DesignNode = {
      ...structuredClone(source),
      id: nextId,
      parent_id: parentId,
      children: [],
      transform: {
        ...sourceTransform,
        x: (sourceTransform.x ?? 0) + (roots.includes(id) ? 36 : 0),
        y: (sourceTransform.y ?? 0) + (roots.includes(id) ? 36 : 0),
      },
    };
    operations.push({
      operation_id: `duplicate-${suffix}-${sequence++}`,
      type: "CREATE_NODE",
      target_ids: [nextId],
      expected_document_version: version,
      payload: { node, parent_id: parentId },
      reason: "canvas-duplicate",
    });
    source.children.forEach((childId) => cloneNode(childId, nextId));
  };
  roots.forEach((id) => cloneNode(id));
  return operations;
}

export function InfiniteCanvasProduct({
  projectId,
  bootstrap,
  references,
  artifacts,
  onContextChange,
  onAIEdit,
}: Props) {
  const { activeOrganization, api } = useShell();
  const gateway = useMemo(() => getInfiniteCanvasGateway(api, bootstrap), [api, bootstrap]);
  const controllerRef = useRef<CanvasController | null>(null);
  const autosaveRef = useRef(new CanvasAutosaveBuffer());
  const serverVersionRef = useRef(0);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushingRef = useRef(false);
  const historyRef = useRef<HistoryEntry[]>([]);
  const redoRef = useRef<HistoryEntry[]>([]);
  const clipboardRef = useRef<readonly string[]>([]);
  const dragRef = useRef<DragSession | null>(null);
  const panRef = useRef<PanSession | null>(null);
  const spaceHeldRef = useRef(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const scheduleFlushRef = useRef<() => void>(() => undefined);

  const [runtime, setRuntime] = useState<CanvasRuntimeSnapshot | null>(null);
  const [syncState, setSyncState] = useState<CanvasSyncState>("SAVED");
  const [pendingCount, setPendingCount] = useState(0);
  const [online, setOnline] = useState(true);
  const [grid, setGrid] = useState(true);
  const [tool, setTool] = useState<Tool>("select");
  const [dragDelta, setDragDelta] = useState({ x: 0, y: 0 });
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [frameMenuOpen, setFrameMenuOpen] = useState(false);
  const [trayOpen, setTrayOpen] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const syncRuntime = useCallback(() => {
    if (controllerRef.current) setRuntime(controllerRef.current.snapshot());
  }, []);

  const emitContext = useCallback(
    (state: CanvasSyncState) => {
      const snapshot = controllerRef.current?.snapshot();
      onContextChange({
        selected_node_ids: snapshot?.selection.ids ?? [],
        document_version: serverVersionRef.current,
        sync_state: state,
      });
    },
    [onContextChange],
  );

  const flushPending = useCallback(async () => {
    if (flushingRef.current || !online) return;
    const controller = controllerRef.current;
    const batch = autosaveRef.current.snapshot();
    if (!controller || !batch) return;
    flushingRef.current = true;
    setSyncState("SAVING");
    emitContext("SAVING");
    try {
      const saved = await gateway.saveOperations(activeOrganization.id, {
        project_id: projectId,
        document_id: controller.snapshot().document.document_id,
        expected_document_version: batch.base_document_version,
        operations: batch.operations,
      });
      const nextServerVersion = getDocumentVersion(saved.document);
      serverVersionRef.current = nextServerVersion;
      autosaveRef.current.acknowledge(batch.count, nextServerVersion);

      let localDocument = saved.document;
      const remaining = autosaveRef.current.snapshot();
      if (remaining) {
        const replay = executeOperations(saved.document, remaining.operations);
        if (replay.ok) localDocument = replay.document;
      }
      controller.replaceDocument(localDocument, false);
      setPendingCount(autosaveRef.current.size);
      const nextState: CanvasSyncState = autosaveRef.current.size ? "DIRTY" : "SAVED";
      setSyncState(nextState);
      syncRuntime();
      emitContext(nextState);
      if (autosaveRef.current.size) scheduleFlushRef.current();
    } catch (error) {
      const nextState: CanvasSyncState = isConflict(error) ? "CONFLICT" : online ? "DIRTY" : "OFFLINE";
      setSyncState(nextState);
      setNotice(
        isConflict(error)
          ? "检测到服务器 Document version 已前进。请选择 Rebase 或 Reload；不会静默覆盖。"
          : `Autosave failed: ${errorMessage(error)}`,
      );
      emitContext(nextState);
    } finally {
      flushingRef.current = false;
    }
  }, [activeOrganization.id, emitContext, gateway, online, projectId, syncRuntime]);

  const scheduleFlush = useCallback(() => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => void flushPending(), 800);
  }, [flushPending]);
  scheduleFlushRef.current = scheduleFlush;

  const enqueue = useCallback(
    (operations: readonly DesignOperation[]) => {
      if (!operations.length) return;
      autosaveRef.current.append(serverVersionRef.current, operations);
      setPendingCount(autosaveRef.current.size);
      const state: CanvasSyncState = online ? "DIRTY" : "OFFLINE";
      setSyncState(state);
      emitContext(state);
      if (online) scheduleFlush();
    },
    [emitContext, online, scheduleFlush],
  );

  const recordHistory = useCallback((before: DesignDocument, forward: readonly DesignOperation[]) => {
    if (!forward.length) return;
    historyRef.current.push({ forward: structuredClone(forward), inverse: invertOperations(before, forward) });
    if (historyRef.current.length > 100) historyRef.current.shift();
    redoRef.current = [];
  }, []);

  const applyLocalOperations = useCallback(
    (label: string, operations: readonly DesignOperation[]) => {
      const controller = controllerRef.current;
      if (!controller || !operations.length) return false;
      const before = controller.snapshot().document;
      const prepared = rebaseOperationsVersion(operations, getDocumentVersion(before), `local-${label}`);
      const result = executeOperations(before, prepared);
      if (!result.ok) {
        setNotice(result.failures[0]?.message ?? "Design operation rejected");
        return false;
      }
      recordHistory(before, prepared);
      controller.replaceDocument(result.document, false);
      enqueue(prepared);
      syncRuntime();
      return true;
    },
    [enqueue, recordHistory, syncRuntime],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void gateway
      .getDocument(activeOrganization.id, projectId)
      .then((snapshot) => {
        if (cancelled) return;
        serverVersionRef.current = getDocumentVersion(snapshot.document);
        const controller = new CanvasController(snapshot.document, {
          initial_viewport: { width: 1100, height: 760 },
        });
        controllerRef.current?.destroy();
        controllerRef.current = controller;
        controller.fitAll(72);
        autosaveRef.current.clear();
        setPendingCount(0);
        setSyncState("SAVED");
        setRuntime(controller.snapshot());
        onContextChange({ selected_node_ids: [], document_version: serverVersionRef.current, sync_state: "SAVED" });
      })
      .catch((error) => setNotice(`Canvas load failed: ${errorMessage(error)}`))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      controllerRef.current?.destroy();
      controllerRef.current = null;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [activeOrganization.id, gateway, onContextChange, projectId]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport || loading) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      const controller = controllerRef.current;
      if (!entry || !controller) return;
      controller.setViewport(
        { width: Math.max(1, entry.contentRect.width), height: Math.max(1, entry.contentRect.height) },
        window.devicePixelRatio,
      );
      syncRuntime();
    });
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [loading, syncRuntime]);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      const state: CanvasSyncState = autosaveRef.current.size ? "DIRTY" : "SAVED";
      setSyncState(state);
      emitContext(state);
      if (autosaveRef.current.size) scheduleFlushRef.current();
    };
    const handleOffline = () => {
      setOnline(false);
      setSyncState("OFFLINE");
      emitContext("OFFLINE");
    };
    setOnline(navigator.onLine);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [emitContext]);

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (autosaveRef.current.size) event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

  const updateSelection = useCallback(
    (ids: readonly string[], primary: string | null = ids[0] ?? null) => {
      const controller = controllerRef.current;
      if (!controller) return;
      controller.selection.set(ids, primary);
      syncRuntime();
      emitContext(syncState);
    },
    [emitContext, syncRuntime, syncState],
  );

  const selectNode = (nodeId: string, additive: boolean) => {
    const current = controllerRef.current?.selection.snapshot().ids ?? [];
    const next = additive
      ? current.includes(nodeId)
        ? current.filter((id) => id !== nodeId)
        : [...current, nodeId]
      : [nodeId];
    updateSelection(next, nodeId);
  };

  const beginNodeDrag = (event: ReactPointerEvent<HTMLDivElement>, node: CanvasSceneNode) => {
    if (event.button !== 0 || tool !== "select" || node.locked) return;
    event.stopPropagation();
    const controller = controllerRef.current;
    if (!controller) return;
    if (!controller.selection.snapshot().ids.includes(node.id)) controller.selection.set([node.id], node.id);
    const transform = controller.beginTransform(`product-drag-${Date.now()}`);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      transform,
      before: controller.snapshot().document,
      nodeIds: transform.ids,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragDelta({ x: 0, y: 0 });
    syncRuntime();
    emitContext(syncState);
  };

  const moveNodeDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const controller = controllerRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !controller) return;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    setDragDelta({ x: dx, y: dy });
    drag.transform.previewMove(dx / controller.snapshot().camera.zoom, dy / controller.snapshot().camera.zoom);
  };

  const endNodeDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    const controller = controllerRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !controller) return;
    const operations = drag.transform.operations();
    const result = controller.commitTransform(drag.transform, "product-drag");
    if (result.accepted && operations.length) {
      recordHistory(drag.before, operations);
      enqueue(operations);
    } else if (!result.accepted) {
      setNotice("当前约束不允许移动该对象，预览已回滚。");
    }
    dragRef.current = null;
    setDragDelta({ x: 0, y: 0 });
    syncRuntime();
  };

  const beginPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const background = event.target === event.currentTarget || target.dataset.canvasWorld === "true";
    if (!background) return;
    if (tool === "select" && !spaceHeldRef.current && event.button === 0) updateSelection([]);
    if (event.button !== 1 && tool !== "hand" && !spaceHeldRef.current) return;
    panRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const movePan = (event: ReactPointerEvent<HTMLDivElement>) => {
    const pan = panRef.current;
    const controller = controllerRef.current;
    if (!pan || pan.pointerId !== event.pointerId || !controller) return;
    controller.pan({ x: event.clientX - pan.x, y: event.clientY - pan.y });
    panRef.current = { pointerId: pan.pointerId, x: event.clientX, y: event.clientY };
    syncRuntime();
  };

  const endPan = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (panRef.current?.pointerId === event.pointerId) panRef.current = null;
  };

  const wheelZoom = (event: ReactWheelEvent<HTMLDivElement>) => {
    const controller = controllerRef.current;
    const viewport = viewportRef.current;
    if (!controller || !viewport) return;
    const rect = viewport.getBoundingClientRect();
    controller.wheelZoom({ x: event.clientX - rect.left, y: event.clientY - rect.top }, event.deltaY);
    syncRuntime();
  };

  const createFrame = (preset: FramePreset) => {
    const controller = controllerRef.current;
    if (!controller) return;
    const snapshot = controller.snapshot();
    const center = screenToWorld(
      { x: snapshot.viewport.width / 2, y: snapshot.viewport.height / 2 },
      snapshot.camera,
    );
    const id = `frame-${preset.id.replace(":", "x")}-${crypto.randomUUID().slice(0, 8)}`;
    const operation: DesignOperation = {
      operation_id: `create-${id}`,
      type: "CREATE_NODE",
      target_ids: [id],
      expected_document_version: getDocumentVersion(snapshot.document),
      payload: {
        parent_id: snapshot.document.root_id,
        node: {
          id,
          kind: "FRAME",
          name: `${preset.label} / ${preset.id}`,
          parent_id: snapshot.document.root_id,
          children: [],
          transform: {
            x: center.x - preset.width / 2,
            y: center.y - preset.height / 2,
            width: preset.width,
            height: preset.height,
          },
          metadata: { preset: preset.id, fill: "#f0ece4" },
        },
      },
      reason: "frame-preset",
    };
    if (applyLocalOperations("frame", [operation])) {
      setFrameMenuOpen(false);
      updateSelection([id], id);
    }
  };

  const setLock = (nodeId: string, locked: boolean) => {
    const document = controllerRef.current?.snapshot().document;
    if (!document) return;
    applyLocalOperations("lock", [{
      operation_id: `lock-${nodeId}-${Date.now()}`,
      type: "SET_PROPERTY",
      target_ids: [nodeId],
      expected_document_version: getDocumentVersion(document),
      payload: { path: "locked", value: locked },
      reason: "canvas-lock",
    }]);
    setContextMenu(null);
  };

  const arrange = (nodeId: string, direction: "forward" | "back") => {
    const document = controllerRef.current?.snapshot().document;
    const node = document?.nodes[nodeId];
    if (!document || !node?.parent_id) return;
    const siblings = document.nodes[node.parent_id]?.children ?? [];
    const current = siblings.indexOf(nodeId);
    const next = direction === "forward" ? Math.min(siblings.length - 1, current + 1) : Math.max(0, current - 1);
    if (current === next) return;
    applyLocalOperations("arrange", [{
      operation_id: `arrange-${nodeId}-${Date.now()}`,
      type: "REORDER_NODE",
      target_ids: [nodeId],
      expected_document_version: getDocumentVersion(document),
      payload: { index: next },
      reason: "canvas-arrange",
    }]);
    setContextMenu(null);
  };

  const duplicate = (ids?: readonly string[]) => {
    const controller = controllerRef.current;
    if (!controller) return;
    const snapshot = controller.snapshot();
    applyLocalOperations(
      "duplicate",
      duplicateOperations(snapshot.document, ids ?? snapshot.selection.ids, getDocumentVersion(snapshot.document)),
    );
    setContextMenu(null);
  };

  const removeSelection = () => {
    const controller = controllerRef.current;
    if (!controller) return;
    const snapshot = controller.snapshot();
    const ids = snapshot.selection.ids.filter((id) => !snapshot.scene.nodes.get(id)?.locked);
    if (!ids.length) return;
    const version = getDocumentVersion(snapshot.document);
    const operations: DesignOperation[] = ids.map((id, index) => ({
      operation_id: `delete-${Date.now()}-${index}`,
      type: "DELETE_NODE",
      target_ids: [id],
      expected_document_version: version,
      payload: {},
      reason: "canvas-delete",
    }));
    if (applyLocalOperations("delete", operations)) updateSelection([]);
  };

  const undo = () => {
    const controller = controllerRef.current;
    const entry = historyRef.current.pop();
    if (!controller || !entry) return;
    const document = controller.snapshot().document;
    const operations = rebaseOperationsVersion(entry.inverse, getDocumentVersion(document), "undo");
    const result = executeOperations(document, operations);
    if (!result.ok) {
      historyRef.current.push(entry);
      setNotice("Undo 被当前文档约束拒绝。");
      return;
    }
    redoRef.current.push(entry);
    controller.replaceDocument(result.document, false);
    enqueue(operations);
    syncRuntime();
  };

  const redo = () => {
    const controller = controllerRef.current;
    const entry = redoRef.current.pop();
    if (!controller || !entry) return;
    const document = controller.snapshot().document;
    const operations = rebaseOperationsVersion(entry.forward, getDocumentVersion(document), "redo");
    const result = executeOperations(document, operations);
    if (!result.ok) {
      redoRef.current.push(entry);
      setNotice("Redo 被当前文档约束拒绝。");
      return;
    }
    historyRef.current.push(entry);
    controller.replaceDocument(result.document, false);
    enqueue(operations);
    syncRuntime();
  };

  const copy = () => {
    clipboardRef.current = controllerRef.current?.selection.snapshot().ids ?? [];
    setNotice(clipboardRef.current.length ? `已复制 ${clipboardRef.current.length} 个对象。` : "没有可复制的对象。");
  };
  const paste = () => duplicate(clipboardRef.current);

  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input,textarea,[contenteditable=true]")) return;
      if (event.code === "Space") {
        spaceHeldRef.current = true;
        event.preventDefault();
        return;
      }
      const meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === "c") {
        event.preventDefault();
        copy();
      } else if (meta && event.key.toLowerCase() === "v") {
        event.preventDefault();
        paste();
      } else if (meta && event.key.toLowerCase() === "z") {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        removeSelection();
      } else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
        const controller = controllerRef.current;
        if (!controller) return;
        const step = event.shiftKey ? 10 : 1;
        const dx = event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0;
        const dy = event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0;
        const before = controller.snapshot().document;
        const session = controller.beginTransform(`nudge-${Date.now()}`);
        session.previewMove(dx, dy);
        const operations = session.operations();
        const result = controller.commitTransform(session, "keyboard-nudge");
        if (result.accepted && operations.length) {
          recordHistory(before, operations);
          enqueue(operations);
          syncRuntime();
        }
      }
    };
    const keyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") spaceHeldRef.current = false;
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
    };
  });

  const rebasePending = async () => {
    const pending = autosaveRef.current.snapshot();
    if (!pending) return;
    try {
      const canonical = await gateway.getDocument(activeOrganization.id, projectId);
      const version = getDocumentVersion(canonical.document);
      const operations = rebaseOperationsVersion(pending.operations, version, "explicit-rebase");
      const replay = executeOperations(canonical.document, operations);
      if (!replay.ok) {
        setNotice(`Rebase failed: ${replay.failures[0]?.message ?? "operation rejected"}`);
        return;
      }
      autosaveRef.current.clear();
      autosaveRef.current.append(version, operations);
      serverVersionRef.current = version;
      controllerRef.current?.replaceDocument(replay.document, false);
      setPendingCount(autosaveRef.current.size);
      setSyncState("DIRTY");
      setNotice("Local commands 已基于最新 canonical version 重放，准备重新保存。");
      syncRuntime();
      emitContext("DIRTY");
      scheduleFlush();
    } catch (error) {
      setNotice(`Rebase failed: ${errorMessage(error)}`);
    }
  };

  const reloadCanonical = async () => {
    try {
      const canonical = await gateway.getDocument(activeOrganization.id, projectId);
      serverVersionRef.current = getDocumentVersion(canonical.document);
      autosaveRef.current.clear();
      historyRef.current = [];
      redoRef.current = [];
      controllerRef.current?.replaceDocument(canonical.document, true);
      setPendingCount(0);
      setSyncState("SAVED");
      setNotice("已丢弃未提交本地 commands，并重新加载 canonical document。");
      syncRuntime();
      emitContext("SAVED");
    } catch (error) {
      setNotice(`Reload failed: ${errorMessage(error)}`);
    }
  };

  const dropPayload = (event: ReactDragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const controller = controllerRef.current;
    const viewport = viewportRef.current;
    if (!controller || !viewport) return;
    if (event.dataTransfer.files.length) {
      setNotice(`${event.dataTransfer.files.length} 个系统文件必须先进入 Asset lifecycle；未伪造为已上传资源。`);
      return;
    }
    const rect = viewport.getBoundingClientRect();
    const snapshot = controller.snapshot();
    const point = screenToWorld({ x: event.clientX - rect.left, y: event.clientY - rect.top }, snapshot.camera);
    const parentId = frameParentAt(snapshot, point.x, point.y);
    const parentScene = snapshot.scene.nodes.get(parentId);
    const x = parentScene ? point.x - parentScene.world_bounds.x : point.x;
    const y = parentScene ? point.y - parentScene.world_bounds.y : point.y;
    const assetRaw = event.dataTransfer.getData("application/x-lumi-asset");
    const artifactRaw = event.dataTransfer.getData("application/x-lumi-artifact");
    let assetId: string | null = null;
    let artifactVersionId: string | null = null;
    let label = "Dropped media";
    try {
      if (assetRaw) {
        const payload = JSON.parse(assetRaw) as { asset_id?: string; file_name?: string };
        assetId = payload.asset_id ?? null;
        label = payload.file_name ?? label;
      } else if (artifactRaw) {
        const payload = JSON.parse(artifactRaw) as { artifact_version_id?: string; title?: string };
        artifactVersionId = payload.artifact_version_id ?? null;
        label = payload.title ?? label;
      }
    } catch {
      setNotice("拖放 payload 无法解析。");
      return;
    }
    if (!assetId && !artifactVersionId) return;
    const id = `drop-${crypto.randomUUID().slice(0, 10)}`;
    const operation: DesignOperation = {
      operation_id: `create-${id}`,
      type: "CREATE_NODE",
      target_ids: [id],
      expected_document_version: getDocumentVersion(snapshot.document),
      payload: {
        parent_id: parentId,
        node: {
          id,
          kind: "IMAGE",
          name: label,
          parent_id: parentId,
          children: [],
          ...(assetId ? { asset_id: assetId } : {}),
          transform: { x: x - 160, y: y - 200, width: 320, height: 400 },
          metadata: artifactVersionId
            ? { artifact_version_id: artifactVersionId, source: "artifact" }
            : { source: "asset" },
        },
      },
      reason: artifactVersionId ? "artifact-drop" : "asset-drop",
    };
    if (applyLocalOperations("drop", [operation])) updateSelection([id], id);
  };

  if (loading || !runtime) return <div className={styles.loading}>正在启动 Infinite Canvas runtime…</div>;

  const selectedSet = new Set(runtime.selection.ids);
  const sceneNodes = runtime.scene.paint_order
    .map((id) => runtime.scene.nodes.get(id))
    .filter((node): node is CanvasSceneNode => Boolean(node));
  const visible = cullSceneNodes(sceneNodes, runtime.camera, runtime.viewport, selectedSet);
  const primary = runtime.selection.primary_id ? runtime.scene.nodes.get(runtime.selection.primary_id) ?? null : null;
  const draggingIds = new Set(dragRef.current?.nodeIds ?? []);
  const zoomPercent = Math.round(runtime.camera.zoom * 100);

  return (
    <div className={styles.productCanvas}>
      <div className={styles.topToolbar}>
        <div className={styles.toolGroup}>
          <button type="button" data-active={tool === "select"} onClick={() => setTool("select")} title="Select">↖</button>
          <button type="button" data-active={tool === "hand"} onClick={() => setTool("hand")} title="Pan">✋</button>
          <div className={styles.menuAnchor}>
            <button type="button" onClick={() => setFrameMenuOpen((value) => !value)}>+ Frame</button>
            {frameMenuOpen ? (
              <div className={styles.frameMenu}>
                {PRESETS.map((preset) => (
                  <button key={preset.id} type="button" onClick={() => createFrame(preset)}>
                    <strong>{preset.id}</strong><span>{preset.label} · {preset.width}×{preset.height}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
        <div className={styles.toolGroup}>
          <button type="button" onClick={undo} disabled={!historyRef.current.length}>↶</button>
          <button type="button" onClick={redo} disabled={!redoRef.current.length}>↷</button>
          <button type="button" onClick={() => setGrid((value) => !value)} data-active={grid}>Grid</button>
          <button type="button" onClick={() => { controllerRef.current?.fitSelection(72); syncRuntime(); }} disabled={!runtime.selection.ids.length}>Fit selection</button>
          <button type="button" onClick={() => { controllerRef.current?.fitAll(72); syncRuntime(); }}>Fit all</button>
        </div>
        <div className={styles.toolGroup}>
          <button type="button" onClick={() => { const c = controllerRef.current; if (c) { const s = c.snapshot(); c.setCamera({ ...s.camera, zoom: Math.max(0.05, s.camera.zoom / 1.2) }); syncRuntime(); } }}>−</button>
          <span className={styles.zoomLabel}>{zoomPercent}%</span>
          <button type="button" onClick={() => { const c = controllerRef.current; if (c) { const s = c.snapshot(); c.setCamera({ ...s.camera, zoom: Math.min(8, s.camera.zoom * 1.2) }); syncRuntime(); } }}>+</button>
          <span className={styles.syncBadge} data-state={syncState}>{online ? syncState : "OFFLINE"}{pendingCount ? ` · ${pendingCount}` : ""}</span>
        </div>
      </div>

      {primary ? (
        <div className={styles.contextToolbar}>
          <strong>{runtime.document.nodes[primary.id]?.name ?? primary.id}</strong>
          <span>X {Math.round(primary.world_bounds.x)}</span><span>Y {Math.round(primary.world_bounds.y)}</span>
          <span>W {Math.round(primary.world_bounds.width)}</span><span>H {Math.round(primary.world_bounds.height)}</span>
          <button type="button" onClick={() => setLock(primary.id, !primary.locked)}>{primary.locked ? "Unlock" : "Lock"}</button>
          <button type="button" onClick={() => arrange(primary.id, "back")} disabled={!primary.parent_id}>Back</button>
          <button type="button" onClick={() => arrange(primary.id, "forward")} disabled={!primary.parent_id}>Forward</button>
          <button type="button" onClick={() => onAIEdit(runtime.selection.ids)}>AI Edit</button>
        </div>
      ) : null}

      {syncState === "CONFLICT" ? (
        <div className={styles.conflictBar} role="alert">
          <span>Document version conflict：未提交 commands 保留在内存中，不会覆盖服务器版本。</span>
          <button type="button" onClick={() => void rebasePending()}>Rebase local commands</button>
          <button type="button" onClick={() => void reloadCanonical()}>Reload canonical</button>
        </div>
      ) : null}
      {notice ? <button type="button" className={styles.notice} onClick={() => setNotice(null)}>{notice}</button> : null}

      <div className={styles.canvasBody}>
        <button type="button" className={styles.trayToggle} onClick={() => setTrayOpen((value) => !value)}>Assets</button>
        {trayOpen ? (
          <aside className={styles.assetTray} aria-label="Canvas drag sources">
            <div className={styles.trayHeader}><strong>Sources</strong><span>drag → canvas</span></div>
            {references.map((reference) => (
              <div
                key={reference.id}
                className={styles.trayItem}
                draggable={reference.scan_status === "READY"}
                data-ready={reference.scan_status === "READY"}
                onDragStart={(event) => {
                  event.dataTransfer.setData("application/x-lumi-asset", JSON.stringify({ asset_id: reference.asset_id, file_name: reference.file_name }));
                  event.dataTransfer.effectAllowed = "copy";
                }}
              >
                <span>ASSET</span><strong>{reference.file_name}</strong><small>{reference.scan_status}</small>
              </div>
            ))}
            {artifacts.map((artifact) => (
              <div
                key={artifact.version_id}
                className={styles.trayItem}
                draggable
                onDragStart={(event) => {
                  event.dataTransfer.setData("application/x-lumi-artifact", JSON.stringify({ artifact_version_id: artifact.version_id, title: artifact.title }));
                  event.dataTransfer.effectAllowed = "copy";
                }}
              >
                <span>ARTIFACT v{artifact.version}</span><strong>{artifact.title}</strong><small>{artifact.version_id}</small>
              </div>
            ))}
          </aside>
        ) : null}

        <div
          ref={viewportRef}
          className={styles.viewport}
          data-grid={grid}
          data-tool={tool}
          onWheel={wheelZoom}
          onPointerDown={beginPan}
          onPointerMove={movePan}
          onPointerUp={endPan}
          onPointerCancel={endPan}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }}
          onDrop={dropPayload}
          onContextMenu={(event) => event.preventDefault()}
        >
          <div
            className={styles.world}
            data-canvas-world="true"
            style={{ transform: `translate(${-runtime.camera.x * runtime.camera.zoom}px, ${-runtime.camera.y * runtime.camera.zoom}px) scale(${runtime.camera.zoom})` }}
          >
            {visible.map((node) => {
              const documentNode = runtime.document.nodes[node.id];
              const selected = selectedSet.has(node.id);
              const dragging = draggingIds.has(node.id);
              const fill = metaString(node, "fill");
              const fontSize = metaNumber(node, "font_size");
              const label = metaString(node, "label");
              const fillStyle = fill
                ? node.kind === "TEXT"
                  ? { color: fill }
                  : { background: fill }
                : {};
              return (
                <div
                  key={node.id}
                  role="button"
                  tabIndex={0}
                  aria-label={documentNode?.name ?? node.id}
                  aria-pressed={selected}
                  className={styles.sceneNode}
                  data-kind={node.kind}
                  data-selected={selected}
                  data-locked={node.locked}
                  style={{
                    left: node.world_bounds.x,
                    top: node.world_bounds.y,
                    width: Math.max(1, node.world_bounds.width),
                    height: Math.max(1, node.world_bounds.height),
                    zIndex: node.paint_order + 1,
                    ...fillStyle,
                    ...(dragging ? { transform: `translate(${dragDelta.x / runtime.camera.zoom}px, ${dragDelta.y / runtime.camera.zoom}px)` } : {}),
                  }}
                  onClick={(event) => { event.stopPropagation(); selectNode(node.id, event.shiftKey); }}
                  onPointerDown={(event) => beginNodeDrag(event, node)}
                  onPointerMove={moveNodeDrag}
                  onPointerUp={endNodeDrag}
                  onPointerCancel={endNodeDrag}
                  onContextMenu={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    selectNode(node.id, false);
                    const rect = viewportRef.current?.getBoundingClientRect();
                    setContextMenu({ nodeId: node.id, x: event.clientX - (rect?.left ?? 0), y: event.clientY - (rect?.top ?? 0) });
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") selectNode(node.id, event.shiftKey);
                  }}
                >
                  {node.kind === "FRAME" ? <span className={styles.frameName}>{documentNode?.name ?? node.id}</span> : null}
                  {node.kind === "TEXT" ? <span className={styles.textNode} style={fontSize ? { fontSize } : undefined}>{node.content}</span> : null}
                  {node.kind === "IMAGE" ? <span className={styles.imageNode}><b>{node.asset_id ? "ASSET" : "ARTIFACT"}</b><small>{documentNode?.name ?? node.id}</small></span> : null}
                  {node.kind === "SHAPE" && label ? <span className={styles.shapeLabel}>{label}</span> : null}
                  {node.locked ? <span className={styles.lockBadge}>LOCK</span> : null}
                </div>
              );
            })}
          </div>

          {contextMenu ? (
            <div className={styles.contextMenu} style={{ left: contextMenu.x, top: contextMenu.y }}>
              <button type="button" onClick={copy}>Copy</button>
              <button type="button" onClick={paste} disabled={!clipboardRef.current.length}>Paste</button>
              <button type="button" onClick={() => duplicate([contextMenu.nodeId])}>Duplicate</button>
              <button type="button" onClick={() => setLock(contextMenu.nodeId, !Boolean(runtime.scene.nodes.get(contextMenu.nodeId)?.locked))}>{runtime.scene.nodes.get(contextMenu.nodeId)?.locked ? "Unlock" : "Lock"}</button>
              <button type="button" onClick={() => arrange(contextMenu.nodeId, "forward")}>Bring forward</button>
              <button type="button" onClick={() => arrange(contextMenu.nodeId, "back")}>Send backward</button>
              <button type="button" onClick={() => { onAIEdit([contextMenu.nodeId]); setContextMenu(null); }}>AI Edit</button>
              <button type="button" disabled={Boolean(runtime.scene.nodes.get(contextMenu.nodeId)?.locked)} onClick={() => { updateSelection([contextMenu.nodeId]); removeSelection(); setContextMenu(null); }}>Delete</button>
            </div>
          ) : null}

          <div className={styles.frameNavigator}>
            {runtime.scene.frame_ids.map((frameId) => (
              <button key={frameId} type="button" onClick={() => { controllerRef.current?.fitFrame(frameId, 72); syncRuntime(); }}>
                {runtime.document.nodes[frameId]?.name ?? frameId}
              </button>
            ))}
          </div>
          <div className={styles.versionHud}>
            <span>Server v{serverVersionRef.current}</span>
            <span>Local v{getDocumentVersion(runtime.document)}</span>
            <span>{visible.length}/{sceneNodes.length} visible</span>
          </div>
        </div>
      </div>
    </div>
  );
}
