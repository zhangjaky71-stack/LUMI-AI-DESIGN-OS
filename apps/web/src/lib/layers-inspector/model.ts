import type { CanvasRuntimeSnapshot } from "@lumi/canvas-sdk";
import type { DesignDocument, DesignNode, JsonValue } from "@lumi/design-ir";
import type { CanvasSyncState } from "@/lib/infinite-canvas/types";
import type {
  CanvasEditorState,
  InspectorNodeSnapshot,
  InspectorTextSnapshot,
  InspectorTransformSnapshot,
  LayerTreeNode,
} from "./types";

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function metadataValue(node: DesignNode, key: string): JsonValue | undefined {
  return node.metadata?.[key];
}

function nodeName(node: DesignNode): string {
  return typeof node.name === "string" && node.name.trim() ? node.name.trim() : `${node.kind} · ${node.id}`;
}

function transformSnapshot(node: DesignNode): InspectorTransformSnapshot {
  return {
    x: numberValue(node.transform?.x),
    y: numberValue(node.transform?.y),
    width: Math.max(0, numberValue(node.transform?.width)),
    height: Math.max(0, numberValue(node.transform?.height)),
    rotation_deg: numberValue(node.transform?.rotation_deg),
  };
}

function textSnapshot(node: DesignNode): InspectorTextSnapshot | null {
  if (node.kind !== "TEXT") return null;
  const align = stringValue(metadataValue(node, "text_align"), "left");
  return {
    content: stringValue(node.content),
    font_size: Math.max(1, numberValue(metadataValue(node, "font_size"), 16)),
    line_height: Math.max(0.1, numberValue(metadataValue(node, "line_height"), 1.2)),
    letter_spacing: numberValue(metadataValue(node, "letter_spacing"), 0),
    text_align: align === "center" || align === "right" ? align : "left",
  };
}

export function inspectorNode(
  runtime: CanvasRuntimeSnapshot,
  nodeId: string,
): InspectorNodeSnapshot | null {
  const node = runtime.document.nodes[nodeId];
  if (!node) return null;
  const scene = runtime.scene.nodes.get(nodeId);
  const fill = metadataValue(node, "fill");
  return {
    id: node.id,
    name: nodeName(node),
    kind: node.kind,
    parent_id: node.parent_id,
    visible: node.visible ?? true,
    effective_visible: scene?.visible ?? (node.visible ?? true),
    locked: node.locked ?? false,
    effective_locked: scene?.locked ?? (node.locked ?? false),
    opacity: Math.max(0, Math.min(1, numberValue(node.opacity, 1))),
    blend_mode: typeof node.blend_mode === "string" ? node.blend_mode : "normal",
    fill: typeof fill === "string" ? fill : null,
    asset_id: typeof node.asset_id === "string" ? node.asset_id : null,
    transform: transformSnapshot(node),
    text: textSnapshot(node),
  };
}

export function buildLayerTree(runtime: CanvasRuntimeSnapshot): LayerTreeNode[] {
  const selected = new Set(runtime.selection.ids);
  const primary = runtime.selection.primary_id;

  const build = (nodeId: string, depth: number): LayerTreeNode | null => {
    const node = runtime.document.nodes[nodeId];
    if (!node) return null;
    const scene = runtime.scene.nodes.get(nodeId);
    const children = [...node.children]
      .reverse()
      .map((childId) => build(childId, depth + 1))
      .filter((child): child is LayerTreeNode => child !== null);
    return {
      id: node.id,
      name: nodeName(node),
      kind: node.kind,
      parent_id: node.parent_id,
      depth,
      children,
      visible: node.visible ?? true,
      effective_visible: scene?.visible ?? (node.visible ?? true),
      locked: node.locked ?? false,
      effective_locked: scene?.locked ?? (node.locked ?? false),
      selected: selected.has(node.id),
      primary: primary === node.id,
    };
  };

  const root = runtime.document.nodes[runtime.document.root_id];
  if (!root) return [];
  return [...root.children]
    .reverse()
    .map((id) => build(id, 0))
    .filter((child): child is LayerTreeNode => child !== null);
}

function canGroupSelection(document: DesignDocument, selectedIds: readonly string[]): boolean {
  if (selectedIds.length < 2) return false;
  const nodes = selectedIds.map((id) => document.nodes[id]).filter((node): node is DesignNode => Boolean(node));
  if (nodes.length !== selectedIds.length) return false;
  const parentId = nodes[0]?.parent_id ?? null;
  if (!parentId || nodes.some((node) => node.parent_id !== parentId || node.locked)) return false;
  const selected = new Set(selectedIds);
  return nodes.every((node) => {
    let parent = node.parent_id;
    while (parent) {
      if (selected.has(parent)) return false;
      parent = document.nodes[parent]?.parent_id ?? null;
    }
    return true;
  });
}

function canUngroupSelection(document: DesignDocument, selectedIds: readonly string[]): boolean {
  if (selectedIds.length !== 1) return false;
  const node = document.nodes[selectedIds[0]!];
  if (!node || node.kind !== "GROUP" || !node.parent_id || node.locked) return false;
  return numberValue(node.transform?.rotation_deg) === 0;
}

export function buildCanvasEditorState(
  runtime: CanvasRuntimeSnapshot,
  serverDocumentVersion: number,
  syncState: CanvasSyncState,
): CanvasEditorState {
  const selectedNodes = runtime.selection.ids
    .map((id) => inspectorNode(runtime, id))
    .filter((node): node is InspectorNodeSnapshot => node !== null);
  const localVersion = runtime.document.metadata.document_version;
  return {
    document_id: runtime.document.document_id,
    server_document_version: serverDocumentVersion,
    local_document_version:
      typeof localVersion === "number" && Number.isInteger(localVersion) ? localVersion : 0,
    sync_state: syncState,
    selected_ids: [...runtime.selection.ids],
    primary_id: runtime.selection.primary_id,
    layers: buildLayerTree(runtime),
    selected_nodes: selectedNodes,
    can_group: canGroupSelection(runtime.document, runtime.selection.ids),
    can_ungroup: canUngroupSelection(runtime.document, runtime.selection.ids),
  };
}
