import type { Rect, RenderNodeSnapshot } from "./types";

export interface SnapGuide { readonly axis: "x" | "y"; readonly value: number; readonly source: "grid" | "node" }
export interface SnapResult { readonly rect: Rect; readonly guides: readonly SnapGuide[] }

function anchors(rect: Rect): { x: number[]; y: number[] } {
  return { x: [rect.x, rect.x + rect.width / 2, rect.x + rect.width], y: [rect.y, rect.y + rect.height / 2, rect.y + rect.height] };
}

export function snapRect(proposed: Rect, nearby: readonly RenderNodeSnapshot[], options: { zoom: number; thresholdPx?: number; gridSize?: number } ): SnapResult {
  const threshold = (options.thresholdPx ?? 6) / Math.max(0.001, options.zoom);
  const moving = anchors(proposed);
  let bestDxValue = Number.POSITIVE_INFINITY;
  let bestDyValue = Number.POSITIVE_INFINITY;
  let bestDxGuide: SnapGuide | undefined;
  let bestDyGuide: SnapGuide | undefined;
  const considerX = (target: number, source: "grid" | "node"): void => {
    for (const current of moving.x) {
      const delta = target - current;
      if (Math.abs(delta) <= threshold && Math.abs(delta) < Math.abs(bestDxValue)) { bestDxValue = delta; bestDxGuide = { axis: "x", value: target, source }; }
    }
  };
  const considerY = (target: number, source: "grid" | "node"): void => {
    for (const current of moving.y) {
      const delta = target - current;
      if (Math.abs(delta) <= threshold && Math.abs(delta) < Math.abs(bestDyValue)) { bestDyValue = delta; bestDyGuide = { axis: "y", value: target, source }; }
    }
  };
  for (const node of nearby) { const values = anchors(node.bounds); values.x.forEach((value) => considerX(value, "node")); values.y.forEach((value) => considerY(value, "node")); }
  const grid = options.gridSize ?? 0;
  if (grid > 0) {
    for (const value of moving.x) considerX(Math.round(value / grid) * grid, "grid");
    for (const value of moving.y) considerY(Math.round(value / grid) * grid, "grid");
  }
  const dx = Number.isFinite(bestDxValue) ? bestDxValue : 0; const dy = Number.isFinite(bestDyValue) ? bestDyValue : 0;
  return { rect: { ...proposed, x: proposed.x + dx, y: proposed.y + dy }, guides: [bestDxGuide, bestDyGuide].filter((item): item is SnapGuide => Boolean(item)) };
}
