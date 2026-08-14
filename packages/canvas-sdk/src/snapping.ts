import type { CanvasSceneNode, CanvasSceneSnapshot } from "./ir-scene";
import type { Rect } from "./types";

export type SnapAxis = "x" | "y";
export type SnapKind = "edge" | "center" | "grid" | "distance";

export interface SnapGuide {
  readonly axis: SnapAxis;
  readonly value: number;
  readonly kind: SnapKind;
  readonly source_node_id?: string;
  readonly target_node_id?: string;
}

export interface SnapResult {
  readonly rect: Rect;
  readonly guides: readonly SnapGuide[];
}

export interface SnapOptions {
  readonly zoom: number;
  readonly tolerance_screen_px?: number;
  readonly grid_size?: number;
  readonly include_grid?: boolean;
}

function candidates(node: CanvasSceneNode): {
  readonly x: readonly number[];
  readonly y: readonly number[];
} {
  const bounds = node.world_bounds;
  return {
    x: [bounds.x, bounds.x + bounds.width / 2, bounds.x + bounds.width],
    y: [bounds.y, bounds.y + bounds.height / 2, bounds.y + bounds.height],
  };
}

function rectCandidates(rect: Rect): { readonly x: readonly number[]; readonly y: readonly number[] } {
  return {
    x: [rect.x, rect.x + rect.width / 2, rect.x + rect.width],
    y: [rect.y, rect.y + rect.height / 2, rect.y + rect.height],
  };
}

function bestDelta(
  sourceValues: readonly number[],
  targetValues: readonly Array<{ readonly value: number; readonly nodeId?: string }>,
  tolerance: number,
): { readonly delta: number; readonly value: number; readonly nodeId?: string } | null {
  let best: { readonly delta: number; readonly value: number; readonly nodeId?: string } | null = null;
  for (const source of sourceValues) {
    for (const target of targetValues) {
      const delta = target.value - source;
      if (Math.abs(delta) > tolerance) continue;
      if (!best || Math.abs(delta) < Math.abs(best.delta)) {
        best = { delta, value: target.value, ...(target.nodeId ? { nodeId: target.nodeId } : {}) };
      }
    }
  }
  return best;
}

export function snapRect(
  desired: Rect,
  scene: CanvasSceneSnapshot,
  ignoreIds: ReadonlySet<string>,
  options: SnapOptions,
): SnapResult {
  const zoom = Math.max(0.0001, Math.abs(options.zoom));
  const tolerance = (options.tolerance_screen_px ?? 6) / zoom;
  const xTargets: Array<{ value: number; nodeId?: string }> = [];
  const yTargets: Array<{ value: number; nodeId?: string }> = [];

  for (const id of scene.paint_order) {
    if (ignoreIds.has(id)) continue;
    const node = scene.nodes.get(id);
    if (!node || !node.visible || node.kind === "DOCUMENT_ROOT" || node.kind === "GUIDE") continue;
    const values = candidates(node);
    xTargets.push(...values.x.map((value) => ({ value, nodeId: id })));
    yTargets.push(...values.y.map((value) => ({ value, nodeId: id })));
  }

  const source = rectCandidates(desired);
  const xSnap = bestDelta(source.x, xTargets, tolerance);
  const ySnap = bestDelta(source.y, yTargets, tolerance);
  let nextX = desired.x + (xSnap?.delta ?? 0);
  let nextY = desired.y + (ySnap?.delta ?? 0);
  const guides: SnapGuide[] = [];

  if (xSnap) guides.push({ axis: "x", value: xSnap.value, kind: "edge", ...(xSnap.nodeId ? { source_node_id: xSnap.nodeId } : {}) });
  if (ySnap) guides.push({ axis: "y", value: ySnap.value, kind: "edge", ...(ySnap.nodeId ? { source_node_id: ySnap.nodeId } : {}) });

  if (options.include_grid && (options.grid_size ?? 0) > 0) {
    const grid = options.grid_size ?? 8;
    if (!xSnap) {
      const snapped = Math.round(nextX / grid) * grid;
      if (Math.abs(snapped - nextX) <= tolerance) {
        nextX = snapped;
        guides.push({ axis: "x", value: snapped, kind: "grid" });
      }
    }
    if (!ySnap) {
      const snapped = Math.round(nextY / grid) * grid;
      if (Math.abs(snapped - nextY) <= tolerance) {
        nextY = snapped;
        guides.push({ axis: "y", value: snapped, kind: "grid" });
      }
    }
  }

  return {
    rect: { ...desired, x: nextX, y: nextY },
    guides,
  };
}
