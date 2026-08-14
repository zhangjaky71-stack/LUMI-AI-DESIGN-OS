import type { DesignDocument, DesignNode, JsonValue } from "../../design-ir/src/index";
import { canonicalStringify } from "../../design-ir/src/index";
import {
  IDENTITY_MATRIX,
  multiplyMatrix,
  transformToMatrix,
  transformedRectBounds,
  type Matrix2D,
} from "./matrix";
import type { Rect } from "./types";

export const CANVAS_RENDERABLE_KINDS = [
  "FRAME",
  "GROUP",
  "TEXT",
  "IMAGE",
  "SHAPE",
  "VECTOR_PATH",
  "VIDEO",
  "MASK",
  "GUIDE",
  "COMPONENT",
  "INSTANCE",
] as const;

export interface CanvasNodeDiagnostic {
  readonly node_id: string;
  readonly code:
    | "MISSING_PARENT"
    | "MISSING_CHILD"
    | "CYCLE"
    | "MALFORMED_TRANSFORM"
    | "UNSUPPORTED_KIND";
  readonly detail?: string;
}

export interface CanvasSceneNode {
  readonly id: string;
  readonly kind: string;
  readonly parent_id: string | null;
  readonly children: readonly string[];
  readonly depth: number;
  readonly paint_order: number;
  readonly visible: boolean;
  readonly locked: boolean;
  readonly local_matrix: Matrix2D;
  readonly world_matrix: Matrix2D;
  readonly local_bounds: Rect;
  readonly world_bounds: Rect;
  readonly render_key: string;
  readonly asset_id?: string;
  readonly content?: string;
  readonly metadata: Readonly<Record<string, JsonValue>>;
}

export interface CanvasSceneSnapshot {
  readonly document_id: string;
  readonly schema_version: string;
  readonly root_id: string;
  readonly nodes: ReadonlyMap<string, CanvasSceneNode>;
  readonly paint_order: readonly string[];
  readonly frame_ids: readonly string[];
  readonly diagnostics: readonly CanvasNodeDiagnostic[];
}

function finite(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function safeDimensions(node: DesignNode): { width: number; height: number } {
  return {
    width: Math.max(0, finite(node.transform?.width)),
    height: Math.max(0, finite(node.transform?.height)),
  };
}

function renderKey(node: DesignNode): string {
  return canonicalStringify({
    id: node.id,
    kind: node.kind,
    visible: node.visible ?? true,
    opacity: node.opacity ?? 1,
    blend_mode: node.blend_mode ?? "normal",
    transform: node.transform ?? {},
    style_refs: node.style_refs ?? [],
    content: typeof node.content === "string" ? node.content : null,
    asset_id: typeof node.asset_id === "string" ? node.asset_id : null,
    metadata: node.metadata ?? {},
  });
}

function diagnostic(
  diagnostics: CanvasNodeDiagnostic[],
  nodeId: string,
  code: CanvasNodeDiagnostic["code"],
  detail?: string,
): void {
  diagnostics.push({ node_id: nodeId, code, ...(detail ? { detail } : {}) });
}

function isRenderable(node: DesignNode): boolean {
  return CANVAS_RENDERABLE_KINDS.includes(
    node.kind as (typeof CANVAS_RENDERABLE_KINDS)[number],
  );
}

export function projectDesignDocument(document: DesignDocument): CanvasSceneSnapshot {
  const nodes = new Map<string, CanvasSceneNode>();
  const diagnostics: CanvasNodeDiagnostic[] = [];
  const paintOrder: string[] = [];
  const frameIds: string[] = [];
  const visiting = new Set<string>();
  const visited = new Set<string>();
  let paint = 0;

  const visit = (id: string, parentWorld: Matrix2D, depth: number): void => {
    if (visited.has(id)) return;
    if (visiting.has(id)) {
      diagnostic(diagnostics, id, "CYCLE");
      return;
    }
    const node = document.nodes[id];
    if (!node) {
      diagnostic(diagnostics, id, "MISSING_CHILD");
      return;
    }
    visiting.add(id);
    if (!isRenderable(node) && node.kind !== "DOCUMENT_ROOT") {
      diagnostic(diagnostics, id, "UNSUPPORTED_KIND", node.kind);
    }

    const local = transformToMatrix(node.transform ?? {});
    const world = multiplyMatrix(parentWorld, local);
    const dimensions = safeDimensions(node);
    const localBounds: Rect = { x: 0, y: 0, width: dimensions.width, height: dimensions.height };
    const sceneNode: CanvasSceneNode = {
      id: node.id,
      kind: node.kind,
      parent_id: node.parent_id,
      children: [...node.children],
      depth,
      paint_order: paint,
      visible: node.visible ?? true,
      locked: node.locked ?? false,
      local_matrix: local,
      world_matrix: world,
      local_bounds: localBounds,
      world_bounds: transformedRectBounds(world, dimensions.width, dimensions.height),
      render_key: renderKey(node),
      ...(typeof node.asset_id === "string" ? { asset_id: node.asset_id } : {}),
      ...(typeof node.content === "string" ? { content: node.content } : {}),
      metadata: node.metadata ?? {},
    };
    nodes.set(id, sceneNode);
    paintOrder.push(id);
    if (node.kind === "FRAME") frameIds.push(id);
    paint += 1;

    for (const childId of node.children) {
      const child = document.nodes[childId];
      if (!child) {
        diagnostic(diagnostics, childId, "MISSING_CHILD", `referenced by ${id}`);
        continue;
      }
      if (child.parent_id !== id) {
        diagnostic(
          diagnostics,
          childId,
          "MISSING_PARENT",
          `declared=${child.parent_id ?? "null"}, expected=${id}`,
        );
      }
      visit(childId, world, depth + 1);
    }
    visiting.delete(id);
    visited.add(id);
  };

  visit(document.root_id, IDENTITY_MATRIX, 0);

  for (const node of Object.values(document.nodes)) {
    if (!visited.has(node.id)) {
      diagnostic(diagnostics, node.id, "MISSING_PARENT", "node is unreachable from document root");
      visit(node.id, IDENTITY_MATRIX, 0);
    }
  }

  return {
    document_id: document.document_id,
    schema_version: document.schema_version,
    root_id: document.root_id,
    nodes,
    paint_order: paintOrder,
    frame_ids: frameIds,
    diagnostics,
  };
}

export function sceneNode(snapshot: CanvasSceneSnapshot, id: string): CanvasSceneNode | null {
  return snapshot.nodes.get(id) ?? null;
}

export function visibleSceneNodes(snapshot: CanvasSceneSnapshot): CanvasSceneNode[] {
  return snapshot.paint_order
    .map((id) => snapshot.nodes.get(id))
    .filter((node): node is CanvasSceneNode => Boolean(node?.visible));
}
