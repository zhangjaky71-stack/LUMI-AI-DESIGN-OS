import { rectsIntersect } from "./geometry";
import type { CanvasSceneNode, CanvasSceneSnapshot } from "./ir-scene";
import type { Point, Rect } from "./types";

function containsPoint(rect: Rect, point: Point): boolean {
  return (
    point.x >= rect.x &&
    point.y >= rect.y &&
    point.x <= rect.x + rect.width &&
    point.y <= rect.y + rect.height
  );
}

function cellKey(x: number, y: number): string {
  return `${x}:${y}`;
}

export class CanvasSpatialIndex {
  readonly #cellSize: number;
  readonly #cells = new Map<string, Set<string>>();
  readonly #nodes = new Map<string, CanvasSceneNode>();

  constructor(cellSize = 256) {
    if (!Number.isFinite(cellSize) || cellSize <= 0) {
      throw new Error("cellSize must be a positive finite number");
    }
    this.#cellSize = cellSize;
  }

  rebuild(snapshot: CanvasSceneSnapshot): void {
    this.#cells.clear();
    this.#nodes.clear();
    for (const id of snapshot.paint_order) {
      const node = snapshot.nodes.get(id);
      if (!node || !node.visible || node.kind === "DOCUMENT_ROOT") continue;
      this.#nodes.set(node.id, node);
      for (const key of this.#keysForRect(node.world_bounds)) {
        const bucket = this.#cells.get(key) ?? new Set<string>();
        bucket.add(node.id);
        this.#cells.set(key, bucket);
      }
    }
  }

  get(id: string): CanvasSceneNode | null {
    return this.#nodes.get(id) ?? null;
  }

  query(rect: Rect): CanvasSceneNode[] {
    const ids = new Set<string>();
    for (const key of this.#keysForRect(rect)) {
      for (const id of this.#cells.get(key) ?? []) ids.add(id);
    }
    return [...ids]
      .map((id) => this.#nodes.get(id))
      .filter((node): node is CanvasSceneNode => Boolean(node && rectsIntersect(node.world_bounds, rect)))
      .sort((left, right) => left.paint_order - right.paint_order);
  }

  hitTest(
    point: Point,
    options: { readonly includeLocked?: boolean; readonly isolationRoot?: string | null } = {},
  ): CanvasSceneNode[] {
    const probe: Rect = { x: point.x, y: point.y, width: 0, height: 0 };
    return this.query(probe)
      .filter((node) => (options.includeLocked ?? true) || !node.locked)
      .filter((node) => this.#insideIsolation(node, options.isolationRoot ?? null))
      .filter((node) => containsPoint(node.world_bounds, point))
      .sort((left, right) => right.paint_order - left.paint_order);
  }

  get size(): number {
    return this.#nodes.size;
  }

  #insideIsolation(node: CanvasSceneNode, isolationRoot: string | null): boolean {
    if (!isolationRoot) return true;
    if (node.id === isolationRoot) return true;
    let current: CanvasSceneNode | undefined = node;
    while (current?.parent_id) {
      if (current.parent_id === isolationRoot) return true;
      current = this.#nodes.get(current.parent_id);
    }
    return false;
  }

  #keysForRect(rect: Rect): string[] {
    const left = Math.floor(rect.x / this.#cellSize);
    const top = Math.floor(rect.y / this.#cellSize);
    const right = Math.floor((rect.x + Math.max(0, rect.width)) / this.#cellSize);
    const bottom = Math.floor((rect.y + Math.max(0, rect.height)) / this.#cellSize);
    const keys: string[] = [];
    for (let y = top; y <= bottom; y += 1) {
      for (let x = left; x <= right; x += 1) keys.push(cellKey(x, y));
    }
    return keys;
  }
}
