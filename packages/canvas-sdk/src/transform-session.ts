import type { SceneSnapshot } from "./types";
import type { CanvasOperationGateway } from "./operation-gateway";
import type { OperationCommitResult, OperationDescriptor, Rect } from "./types";

export type TransformMode = "move" | "resize" | "rotate";
export interface TransformPreview { readonly bounds: ReadonlyMap<string, Rect>; readonly rotationDeg: ReadonlyMap<string, number> }

export class TransformSession {
  private readonly initialBounds = new Map<string, Rect>();
  private readonly initialRotation = new Map<string, number>();
  private previewValue: TransformPreview;
  private closed = false;
  constructor(private readonly mode: TransformMode, readonly targetIds: readonly string[], scene: SceneSnapshot, private readonly gateway: CanvasOperationGateway) {
    if (!targetIds.length) throw new Error("CANVAS_TRANSFORM_EMPTY");
    for (const id of targetIds) {
      const node = scene.nodes.get(id);
      if (!node) throw new Error(`CANVAS_TRANSFORM_TARGET_MISSING:${id}`);
      if (node.locked) throw new Error(`CANVAS_TRANSFORM_TARGET_LOCKED:${id}`);
      this.initialBounds.set(id, node.bounds);
      this.initialRotation.set(id, node.rotationDeg);
    }
    if ((mode === "resize" || mode === "rotate") && targetIds.length !== 1) throw new Error("CANVAS_TRANSFORM_MULTI_MODE_UNSUPPORTED");
    this.previewValue = { bounds: new Map(this.initialBounds), rotationDeg: new Map(this.initialRotation) };
  }
  get preview(): TransformPreview { return this.previewValue; }
  update(delta: { dx?: number; dy?: number; width?: number; height?: number; rotationDeg?: number }): TransformPreview {
    if (this.closed) throw new Error("CANVAS_TRANSFORM_CLOSED");
    const bounds = new Map(this.initialBounds); const rotation = new Map(this.initialRotation);
    if (this.mode === "move") {
      for (const [id, rect] of bounds) bounds.set(id, { ...rect, x: rect.x + (delta.dx ?? 0), y: rect.y + (delta.dy ?? 0) });
    } else if (this.mode === "resize") {
      const id = this.targetIds[0]!; const rect = bounds.get(id)!;
      bounds.set(id, { ...rect, width: Math.max(0, delta.width ?? rect.width), height: Math.max(0, delta.height ?? rect.height) });
    } else {
      const id = this.targetIds[0]!; rotation.set(id, delta.rotationDeg ?? this.initialRotation.get(id) ?? 0);
    }
    this.previewValue = { bounds, rotationDeg: rotation }; return this.previewValue;
  }
  commit(): OperationCommitResult {
    if (this.closed) throw new Error("CANVAS_TRANSFORM_CLOSED");
    const descriptors: OperationDescriptor[] = [];
    for (const id of this.targetIds) {
      const initial = this.initialBounds.get(id)!; const preview = this.previewValue.bounds.get(id)!;
      if (this.mode === "move" && (initial.x !== preview.x || initial.y !== preview.y)) descriptors.push({ type: "MOVE_NODE", targetIds: [id], payload: { x: preview.x, y: preview.y }, reason: "canvas transform commit" });
      if (this.mode === "resize" && (initial.width !== preview.width || initial.height !== preview.height)) descriptors.push({ type: "RESIZE_NODE", targetIds: [id], payload: { width: preview.width, height: preview.height }, reason: "canvas transform commit" });
      if (this.mode === "rotate") { const before = this.initialRotation.get(id) ?? 0; const after = this.previewValue.rotationDeg.get(id) ?? before; if (before !== after) descriptors.push({ type: "ROTATE_NODE", targetIds: [id], payload: { rotation_deg: after }, reason: "canvas transform commit" }); }
    }
    const result = this.gateway.commitBatch(descriptors, "canvas-transform");
    this.closed = true;
    if (!result.ok) this.previewValue = { bounds: new Map(this.initialBounds), rotationDeg: new Map(this.initialRotation) };
    return result;
  }
  cancel(): TransformPreview { this.closed = true; this.previewValue = { bounds: new Map(this.initialBounds), rotationDeg: new Map(this.initialRotation) }; return this.previewValue; }
}
