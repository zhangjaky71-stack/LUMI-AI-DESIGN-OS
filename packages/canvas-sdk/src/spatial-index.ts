import type { Point, Rect, RenderNodeSnapshot, SceneSnapshot } from "./types";

export function rectIntersects(a: Rect, b: Rect): boolean {
  return a.x <= b.x + b.width && a.x + a.width >= b.x && a.y <= b.y + b.height && a.y + a.height >= b.y;
}
export function rectContainsPoint(rect: Rect, point: Point): boolean {
  return point.x >= rect.x && point.x <= rect.x + rect.width && point.y >= rect.y && point.y <= rect.y + rect.height;
}

export class SpatialIndex {
  private readonly entries = new Map<string, RenderNodeSnapshot>();
  rebuild(scene: SceneSnapshot): void { this.entries.clear(); for (const node of scene.nodes.values()) if (node.visible) this.entries.set(node.id, node); }
  upsert(node: RenderNodeSnapshot): void { if (node.visible) this.entries.set(node.id, node); else this.entries.delete(node.id); }
  remove(id: string): void { this.entries.delete(id); }
  query(rect: Rect): readonly RenderNodeSnapshot[] {
    return [...this.entries.values()].filter((node) => rectIntersects(node.bounds, rect)).sort((a, b) => a.zOrder - b.zOrder);
  }
  hit(point: Point): readonly RenderNodeSnapshot[] {
    return [...this.entries.values()].filter((node) => rectContainsPoint(node.bounds, point)).sort((a, b) => b.zOrder - a.zOrder);
  }
  get size(): number { return this.entries.size; }
}
