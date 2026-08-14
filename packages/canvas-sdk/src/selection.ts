import type { CanvasSceneSnapshot } from "./ir-scene";
import type { CanvasSpatialIndex } from "./spatial-index";
import type { Point, Rect } from "./types";

export type SelectionMode = "replace" | "add" | "toggle";

export interface SelectionSnapshot {
  readonly ids: readonly string[];
  readonly primary_id: string | null;
  readonly isolation_root_id: string | null;
}

export class CanvasSelectionModel {
  readonly #selected = new Set<string>();
  #primaryId: string | null = null;
  #isolationRootId: string | null = null;

  snapshot(): SelectionSnapshot {
    return {
      ids: [...this.#selected],
      primary_id: this.#primaryId,
      isolation_root_id: this.#isolationRootId,
    };
  }

  clear(): void {
    this.#selected.clear();
    this.#primaryId = null;
  }

  set(ids: readonly string[], primaryId: string | null = ids[0] ?? null): void {
    this.#selected.clear();
    for (const id of ids) this.#selected.add(id);
    this.#primaryId =
      primaryId && this.#selected.has(primaryId) ? primaryId : (ids[0] ?? null);
  }

  click(
    point: Point,
    index: CanvasSpatialIndex,
    mode: SelectionMode = "replace",
    cycleOffset = 0,
  ): string | null {
    const hits = index.hitTest(point, { isolationRoot: this.#isolationRootId });
    const hit = hits.length ? hits[Math.abs(cycleOffset) % hits.length] ?? null : null;
    if (!hit) {
      if (mode === "replace") this.clear();
      return null;
    }
    this.#apply([hit.id], mode);
    this.#primaryId = hit.id;
    return hit.id;
  }

  marquee(
    rect: Rect,
    index: CanvasSpatialIndex,
    mode: SelectionMode = "replace",
  ): readonly string[] {
    const ids = index
      .query(rect)
      .filter(
        (node) =>
          this.#isolationRootId === null ||
          node.id === this.#isolationRootId ||
          this.#descendsFrom(node.id, this.#isolationRootId, index),
      )
      .map((node) => node.id);
    this.#apply(ids, mode);
    if (ids.length) this.#primaryId = ids[ids.length - 1] ?? this.#primaryId;
    return ids;
  }

  enterIsolation(groupId: string, scene: CanvasSceneSnapshot): boolean {
    const node = scene.nodes.get(groupId);
    if (!node || !["GROUP", "FRAME", "COMPONENT", "INSTANCE"].includes(node.kind)) return false;
    this.#isolationRootId = groupId;
    this.clear();
    return true;
  }

  exitIsolation(): void {
    this.#isolationRootId = null;
    this.clear();
  }

  transformableIds(scene: CanvasSceneSnapshot): string[] {
    return [...this.#selected].filter((id) => {
      const node = scene.nodes.get(id);
      return Boolean(
        node && !node.locked && node.kind !== "DOCUMENT_ROOT" && node.kind !== "GUIDE",
      );
    });
  }

  accessibleRows(scene: CanvasSceneSnapshot): Array<{
    readonly id: string;
    readonly kind: string;
    readonly selected: boolean;
    readonly locked: boolean;
    readonly depth: number;
  }> {
    return scene.paint_order
      .map((id) => scene.nodes.get(id))
      .filter((node): node is NonNullable<typeof node> => Boolean(node))
      .map((node) => ({
        id: node.id,
        kind: node.kind,
        selected: this.#selected.has(node.id),
        locked: node.locked,
        depth: node.depth,
      }));
  }

  #apply(ids: readonly string[], mode: SelectionMode): void {
    if (mode === "replace") this.#selected.clear();
    for (const id of ids) {
      if (mode === "toggle" && this.#selected.has(id)) this.#selected.delete(id);
      else this.#selected.add(id);
    }
    if (this.#primaryId && !this.#selected.has(this.#primaryId)) {
      this.#primaryId = [...this.#selected][0] ?? null;
    }
  }

  #descendsFrom(nodeId: string, rootId: string, index: CanvasSpatialIndex): boolean {
    let current = index.get(nodeId);
    while (current?.parent_id) {
      if (current.parent_id === rootId) return true;
      current = index.get(current.parent_id);
    }
    return false;
  }
}
