import { rectIntersects, SpatialIndex } from "./spatial-index";
import type { Point, Rect, SceneSnapshot } from "./types";

function isDescendant(scene: SceneSnapshot, nodeId: string, ancestorId: string): boolean {
  let current = scene.nodes.get(nodeId);
  const seen = new Set<string>();
  while (current?.parentId) {
    if (current.parentId === ancestorId) return true;
    if (seen.has(current.parentId)) return false;
    seen.add(current.parentId);
    current = scene.nodes.get(current.parentId);
  }
  return false;
}

export class SelectionModel {
  private idsValue = new Set<string>();
  private isolationRootValue: string | null = null;
  get ids(): ReadonlySet<string> { return this.idsValue; }
  get isolationRoot(): string | null { return this.isolationRootValue; }
  clear(): void { this.idsValue = new Set(); }
  set(ids: Iterable<string>): void { this.idsValue = new Set(ids); }
  toggle(id: string): void { if (this.idsValue.has(id)) this.idsValue.delete(id); else this.idsValue.add(id); }
  enterIsolation(id: string): void { this.isolationRootValue = id; this.clear(); }
  exitIsolation(): void { this.isolationRootValue = null; this.clear(); }
  private allowed(scene: SceneSnapshot, id: string): boolean {
    const root = this.isolationRootValue;
    return !root || id === root || isDescendant(scene, id, root);
  }
  click(scene: SceneSnapshot, index: SpatialIndex, point: Point, options: { shift?: boolean; cycle?: number } = {}): string | null {
    const hits = index.hit(point).filter((node) => this.allowed(scene, node.id));
    if (!hits.length) { if (!options.shift) this.clear(); return null; }
    const position = Math.max(0, options.cycle ?? 0) % hits.length;
    const chosen = hits[position];
    if (!chosen) return null;
    if (options.shift) this.toggle(chosen.id); else this.set([chosen.id]);
    return chosen.id;
  }
  marquee(scene: SceneSnapshot, rect: Rect, options: { shift?: boolean } = {}): readonly string[] {
    const matched = [...scene.nodes.values()]
      .filter((node) => node.visible && this.allowed(scene, node.id) && rectIntersects(node.bounds, rect))
      .sort((a, b) => a.zOrder - b.zOrder)
      .map((node) => node.id);
    if (!options.shift) this.set(matched); else for (const id of matched) this.idsValue.add(id);
    return matched;
  }
  transformable(scene: SceneSnapshot): readonly string[] {
    return [...this.idsValue].filter((id) => scene.nodes.get(id)?.locked !== true);
  }
}
