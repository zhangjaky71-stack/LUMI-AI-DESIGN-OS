import {
  executeOperations,
  getDocumentVersion,
  type DesignDocument,
  type DesignOperation,
  type DesignTransform,
} from "../../design-ir/src/index";
import {
  guardedExecute,
  type ConstraintOverrideToken,
  type DesignConstraint,
  type GuardedExecutionResult,
} from "../../design-constraints/src/index";
import { invertMatrix, applyMatrix } from "./matrix";
import type { CanvasSceneSnapshot } from "./ir-scene";
import type { Rect } from "./types";

export interface TransformPreview {
  readonly node_id: string;
  readonly transform: DesignTransform;
}

export interface TransformCommitResult {
  readonly accepted: boolean;
  readonly guarded: GuardedExecutionResult;
  readonly document: DesignDocument;
}

function finite(value: number | undefined, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function unionRects(rects: readonly Rect[]): Rect | null {
  if (!rects.length) return null;
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function same(left: number | undefined, right: number | undefined, epsilon = 1e-8): boolean {
  return Math.abs(finite(left) - finite(right)) <= epsilon;
}

export class CanvasTransformSession {
  readonly #document: DesignDocument;
  readonly #scene: CanvasSceneSnapshot;
  readonly #ids: readonly string[];
  readonly #previews = new Map<string, DesignTransform>();
  readonly #operationPrefix: string;

  constructor(
    document: DesignDocument,
    scene: CanvasSceneSnapshot,
    ids: readonly string[],
    operationPrefix = `canvas-transform-${Date.now()}`,
  ) {
    this.#document = document;
    this.#scene = scene;
    this.#ids = ids.filter((id) => {
      const node = scene.nodes.get(id);
      return Boolean(node && !node.locked && node.kind !== "DOCUMENT_ROOT" && node.kind !== "GUIDE");
    });
    this.#operationPrefix = operationPrefix;
    for (const id of this.#ids) {
      const node = document.nodes[id];
      if (node) this.#previews.set(id, { ...(node.transform ?? {}) });
    }
  }

  get ids(): readonly string[] {
    return this.#ids;
  }

  previewMove(dx: number, dy: number): readonly TransformPreview[] {
    for (const id of this.#ids) {
      const original = this.#document.nodes[id]?.transform ?? {};
      this.#previews.set(id, {
        ...original,
        x: finite(original.x) + dx,
        y: finite(original.y) + dy,
      });
    }
    return this.preview();
  }

  previewRotate(deltaDeg: number): readonly TransformPreview[] {
    for (const id of this.#ids) {
      const original = this.#document.nodes[id]?.transform ?? {};
      this.#previews.set(id, {
        ...original,
        rotation_deg: finite(original.rotation_deg) + deltaDeg,
      });
    }
    return this.preview();
  }

  previewResize(targetWorldBounds: Rect, proportional = false): readonly TransformPreview[] {
    const selected = this.#ids
      .map((id) => this.#scene.nodes.get(id))
      .filter((node): node is NonNullable<typeof node> => Boolean(node));
    const group = unionRects(selected.map((node) => node.world_bounds));
    if (!group || group.width <= 0 || group.height <= 0) return this.preview();

    let target = targetWorldBounds;
    if (proportional) {
      const scale = Math.min(
        Math.max(1e-6, targetWorldBounds.width / group.width),
        Math.max(1e-6, targetWorldBounds.height / group.height),
      );
      target = { ...targetWorldBounds, width: group.width * scale, height: group.height * scale };
    }
    const scaleX = target.width / group.width;
    const scaleY = target.height / group.height;

    for (const sceneNode of selected) {
      const original = this.#document.nodes[sceneNode.id]?.transform ?? {};
      const relativeX = (sceneNode.world_bounds.x - group.x) / group.width;
      const relativeY = (sceneNode.world_bounds.y - group.y) / group.height;
      const nextWorldTopLeft = {
        x: target.x + relativeX * target.width,
        y: target.y + relativeY * target.height,
      };
      const parentMatrix = sceneNode.parent_id
        ? this.#scene.nodes.get(sceneNode.parent_id)?.world_matrix
        : undefined;
      const inverseParent = invertMatrix(parentMatrix ?? { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 });
      const localTopLeft = inverseParent ? applyMatrix(inverseParent, nextWorldTopLeft) : nextWorldTopLeft;
      this.#previews.set(sceneNode.id, {
        ...original,
        x: localTopLeft.x,
        y: localTopLeft.y,
        width: Math.max(1e-6, finite(original.width) * scaleX),
        height: Math.max(1e-6, finite(original.height) * scaleY),
      });
    }
    return this.preview();
  }

  preview(): readonly TransformPreview[] {
    return this.#ids
      .map((id) => {
        const transform = this.#previews.get(id);
        return transform ? { node_id: id, transform: { ...transform } } : null;
      })
      .filter((value): value is TransformPreview => value !== null);
  }

  previewDocument(): DesignDocument {
    const operations = this.#buildOperations();
    if (!operations.length) return this.#document;
    const execution = executeOperations(this.#document, operations);
    return execution.ok ? execution.document : this.#document;
  }

  commit(
    constraints: readonly DesignConstraint[],
    overrides: readonly ConstraintOverrideToken[] = [],
  ): TransformCommitResult {
    const operations = this.#buildOperations();
    const guarded = guardedExecute(this.#document, operations, constraints, { overrides });
    const execution = guarded.execution;
    const accepted = guarded.preflight.decision !== "DENY" && Boolean(execution?.ok);
    return {
      accepted,
      guarded,
      document: accepted && execution?.ok ? execution.document : this.#document,
    };
  }

  #buildOperations(): DesignOperation[] {
    const version = getDocumentVersion(this.#document);
    const operations: DesignOperation[] = [];
    let index = 0;
    for (const id of this.#ids) {
      const original = this.#document.nodes[id]?.transform ?? {};
      const next = this.#previews.get(id);
      if (!next) continue;
      if (!same(original.x, next.x) || !same(original.y, next.y)) {
        operations.push({
          operation_id: `${this.#operationPrefix}-${index++}-move`,
          type: "MOVE_NODE",
          target_ids: [id],
          expected_document_version: version,
          payload: { x: finite(next.x), y: finite(next.y) },
          reason: "canvas-transform",
        });
      }
      if (!same(original.width, next.width) || !same(original.height, next.height)) {
        operations.push({
          operation_id: `${this.#operationPrefix}-${index++}-resize`,
          type: "RESIZE_NODE",
          target_ids: [id],
          expected_document_version: version,
          payload: { width: Math.max(1e-6, finite(next.width)), height: Math.max(1e-6, finite(next.height)) },
          reason: "canvas-transform",
        });
      }
      if (!same(original.rotation_deg, next.rotation_deg)) {
        operations.push({
          operation_id: `${this.#operationPrefix}-${index++}-rotate`,
          type: "ROTATE_NODE",
          target_ids: [id],
          expected_document_version: version,
          payload: { rotation_deg: finite(next.rotation_deg) },
          reason: "canvas-transform",
        });
      }
    }
    return operations;
  }
}
