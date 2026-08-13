import type { Rect, SpikeNode } from "./types";

export function normalizeRect(rect: Rect): Rect {
  const x = rect.width >= 0 ? rect.x : rect.x + rect.width;
  const y = rect.height >= 0 ? rect.y : rect.y + rect.height;
  return {
    x,
    y,
    width: Math.abs(rect.width),
    height: Math.abs(rect.height),
  };
}

export function rectsIntersect(a: Rect, b: Rect): boolean {
  const left = Math.max(a.x, b.x);
  const top = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  return right >= left && bottom >= top;
}

export function nodeBounds(node: SpikeNode): Rect {
  if (node.rotation === 0) {
    return { x: node.x, y: node.y, width: node.width, height: node.height };
  }

  const cx = node.x + node.width / 2;
  const cy = node.y + node.height / 2;
  const radians = node.rotation;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  const corners = [
    { x: node.x, y: node.y },
    { x: node.x + node.width, y: node.y },
    { x: node.x + node.width, y: node.y + node.height },
    { x: node.x, y: node.y + node.height },
  ].map((point) => ({
    x: cx + (point.x - cx) * cosine - (point.y - cy) * sine,
    y: cy + (point.x - cx) * sine + (point.y - cy) * cosine,
  }));

  const xs = corners.map((corner) => corner.x);
  const ys = corners.map((corner) => corner.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export function nodesInRect(nodes: readonly SpikeNode[], rect: Rect): string[] {
  const normalized = normalizeRect(rect);
  return nodes
    .filter((node) => rectsIntersect(nodeBounds(node), normalized))
    .map((node) => node.id);
}

export function cullNodes(nodes: readonly SpikeNode[], viewportWorldRect: Rect): SpikeNode[] {
  return nodes.filter((node) => rectsIntersect(nodeBounds(node), viewportWorldRect));
}

export function unionBounds(nodes: readonly SpikeNode[]): Rect | null {
  if (nodes.length === 0) {
    return null;
  }
  const bounds = nodes.map(nodeBounds);
  const minX = Math.min(...bounds.map((rect) => rect.x));
  const minY = Math.min(...bounds.map((rect) => rect.y));
  const maxX = Math.max(...bounds.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...bounds.map((rect) => rect.y + rect.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}
