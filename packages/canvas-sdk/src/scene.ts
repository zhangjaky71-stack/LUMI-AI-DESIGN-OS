import type { DesignDocument, DesignNode } from "../../design-ir/src/index";
import { CANVAS_RENDER_KINDS, type CanvasDiagnostic, type CanvasRenderKind, type Rect, type RenderNodeSnapshot, type SceneSnapshot } from "./types";

const supported = new Set<string>(CANVAS_RENDER_KINDS);
function numberValue(value: unknown, fallback: number): number { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
function stringValue(value: unknown): string | undefined { return typeof value === "string" && value.length > 0 ? value : undefined; }

export function nodeRect(node: DesignNode): Rect | null {
  const transform = node.transform ?? {};
  const bounds = node.bounds ?? {};
  const width = numberValue(transform.width, numberValue(bounds.width, 0));
  const height = numberValue(transform.height, numberValue(bounds.height, 0));
  const x = numberValue(transform.x, numberValue(bounds.x, 0));
  const y = numberValue(transform.y, numberValue(bounds.y, 0));
  if (width < 0 || height < 0 || ![x, y, width, height].every(Number.isFinite)) return null;
  return { x, y, width, height };
}

function snapshot(node: DesignNode, zOrder: number): { node: RenderNodeSnapshot; diagnostics: CanvasDiagnostic[] } {
  const diagnostics: CanvasDiagnostic[] = [];
  const rect = nodeRect(node);
  let kind: CanvasRenderKind | "PLACEHOLDER" = supported.has(node.kind) ? node.kind as CanvasRenderKind : "PLACEHOLDER";
  if (!rect) {
    kind = "PLACEHOLDER";
    diagnostics.push({ code: "CANVAS_NODE_GEOMETRY_INVALID", message: `Node ${node.id} has invalid geometry.`, severity: "error", nodeId: node.id });
  }
  if (node.kind.startsWith("custom:") || (!supported.has(node.kind) && node.kind !== "DOCUMENT_ROOT")) {
    diagnostics.push({ code: "CANVAS_NODE_KIND_UNSUPPORTED", message: `Node ${node.id} uses unsupported kind ${node.kind}.`, severity: "warning", nodeId: node.id });
  }
  const assetId = stringValue(node.asset_id);
  const text = typeof node.content === "string" ? node.content : undefined;
  const diagnosticCodes = diagnostics.map((item) => item.code);
  return {
    node: {
      id: node.id,
      kind,
      sourceKind: node.kind,
      parentId: node.parent_id,
      childIds: [...node.children],
      bounds: rect ?? { x: 0, y: 0, width: 40, height: 40 },
      rotationDeg: numberValue(node.transform?.rotation_deg, 0),
      visible: node.visible !== false,
      locked: node.locked === true,
      opacity: Math.max(0, Math.min(1, numberValue(node.opacity, 1))),
      zOrder,
      ...(node.role ? { role: node.role } : {}),
      ...(assetId ? { assetId } : {}),
      ...(text !== undefined ? { text } : {}),
      styleRefs: [...(node.style_refs ?? [])],
      diagnosticCodes,
    },
    diagnostics,
  };
}

export function buildScene(document: DesignDocument): SceneSnapshot {
  const diagnostics: CanvasDiagnostic[] = [];
  const nodes = new Map<string, RenderNodeSnapshot>();
  const orderedIds: string[] = [];
  const visited = new Set<string>();
  let z = 0;
  const walk = (id: string): void => {
    if (visited.has(id)) return;
    visited.add(id);
    const raw = document.nodes[id];
    if (!raw) {
      diagnostics.push({ code: "CANVAS_NODE_REFERENCE_MISSING", message: `Scene reference ${id} is missing.`, severity: "error", nodeId: id });
      return;
    }
    if (raw.kind !== "DOCUMENT_ROOT") {
      try {
        const result = snapshot(raw, z++);
        nodes.set(id, result.node);
        orderedIds.push(id);
        diagnostics.push(...result.diagnostics);
      } catch (error) {
        diagnostics.push({ code: "CANVAS_NODE_ISOLATED", message: `Node ${id} failed scene conversion: ${error instanceof Error ? error.message : "unknown"}.`, severity: "error", nodeId: id });
      }
    }
    for (const childId of raw.children) walk(childId);
  };
  walk(document.root_id);
  for (const id of Object.keys(document.nodes).sort()) {
    if (!visited.has(id)) {
      diagnostics.push({ code: "CANVAS_ORPHAN_NODE", message: `Node ${id} is not reachable from root and was isolated.`, severity: "warning", nodeId: id });
      walk(id);
    }
  }
  return { documentId: document.document_id, nodes, orderedIds, diagnostics };
}

export function sceneBounds(scene: SceneSnapshot, ids: readonly string[] = scene.orderedIds): Rect | null {
  const values = ids.map((id) => scene.nodes.get(id)).filter((node): node is RenderNodeSnapshot => Boolean(node && node.visible));
  if (!values.length) return null;
  const minX = Math.min(...values.map((node) => node.bounds.x));
  const minY = Math.min(...values.map((node) => node.bounds.y));
  const maxX = Math.max(...values.map((node) => node.bounds.x + node.bounds.width));
  const maxY = Math.max(...values.map((node) => node.bounds.y + node.bounds.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}
