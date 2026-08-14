import { getDocumentVersion, type DesignDocument, type DesignOperation } from "../../design-ir/src/index";
import type {
  ConstraintOverrideToken,
  DesignConstraint,
} from "../../design-constraints/src/index";
import {
  fitWorldRect,
  panCamera,
  screenToWorld,
  viewportWorldRect,
  zoomAtScreenPoint,
  zoomFromWheelDelta,
} from "./camera";
import { CanvasCommandBus, type CanvasCommandResult } from "./command-bus";
import { projectDesignDocument, type CanvasSceneSnapshot } from "./ir-scene";
import type { CanvasRendererAdapter, RendererSyncResult } from "./renderer";
import { CanvasSelectionModel, type SelectionMode, type SelectionSnapshot } from "./selection";
import { CanvasSpatialIndex } from "./spatial-index";
import { CanvasTextEditSession } from "./text-edit";
import { CanvasTransformSession } from "./transform-session";
import type { CameraState, CanvasViewport, Point, Rect } from "./types";

export interface CanvasControllerOptions {
  readonly initial_camera?: CameraState;
  readonly initial_viewport?: CanvasViewport;
  readonly renderer?: CanvasRendererAdapter;
  readonly request_frame?: (callback: FrameRequestCallback) => number;
  readonly cancel_frame?: (id: number) => void;
}

export interface CanvasRuntimeSnapshot {
  readonly document: DesignDocument;
  readonly scene: CanvasSceneSnapshot;
  readonly camera: CameraState;
  readonly viewport: CanvasViewport;
  readonly selection: SelectionSnapshot;
}

function normalizeRect(rect: Rect): Rect {
  return {
    x: rect.width >= 0 ? rect.x : rect.x + rect.width,
    y: rect.height >= 0 ? rect.y : rect.y + rect.height,
    width: Math.abs(rect.width),
    height: Math.abs(rect.height),
  };
}

function unionRects(rects: readonly Rect[]): Rect | null {
  if (!rects.length) return null;
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

export class CanvasController {
  readonly selection = new CanvasSelectionModel();
  readonly #spatial = new CanvasSpatialIndex();
  readonly #commands: CanvasCommandBus;
  readonly #renderer?: CanvasRendererAdapter;
  readonly #requestFrame: (callback: FrameRequestCallback) => number;
  readonly #cancelFrame: (id: number) => void;
  #constraints: readonly DesignConstraint[] = [];
  #scene: CanvasSceneSnapshot;
  #camera: CameraState;
  #viewport: CanvasViewport;
  #scheduledFrame: number | null = null;

  constructor(document: DesignDocument, options: CanvasControllerOptions = {}) {
    this.#commands = new CanvasCommandBus(document);
    this.#scene = projectDesignDocument(document);
    this.#spatial.rebuild(this.#scene);
    this.#camera = options.initial_camera ?? { x: 0, y: 0, zoom: 1 };
    this.#viewport = options.initial_viewport ?? { width: 1280, height: 720 };
    this.#renderer = options.renderer;
    this.#requestFrame =
      options.request_frame ?? ((callback) => globalThis.requestAnimationFrame(callback));
    this.#cancelFrame = options.cancel_frame ?? ((id) => globalThis.cancelAnimationFrame(id));
  }

  snapshot(): CanvasRuntimeSnapshot {
    return {
      document: this.#commands.document,
      scene: this.#scene,
      camera: this.#camera,
      viewport: this.#viewport,
      selection: this.selection.snapshot(),
    };
  }

  setConstraints(constraints: readonly DesignConstraint[]): void {
    this.#constraints = constraints;
  }

  replaceDocument(document: DesignDocument, clearHistory = true): void {
    this.#commands.replaceDocument(document, clearHistory);
    this.#refreshScene();
  }

  setViewport(viewport: CanvasViewport, devicePixelRatio = 1): void {
    this.#viewport = {
      width: Math.max(1, viewport.width),
      height: Math.max(1, viewport.height),
    };
    this.#renderer?.resize(this.#viewport.width, this.#viewport.height, devicePixelRatio);
    this.scheduleRender();
  }

  setCamera(camera: CameraState): void {
    this.#camera = { ...camera };
    this.scheduleRender();
  }

  pan(screenDelta: Point): void {
    this.#camera = panCamera(this.#camera, screenDelta);
    this.scheduleRender();
  }

  wheelZoom(screenAnchor: Point, deltaY: number): void {
    this.#camera = zoomAtScreenPoint(
      this.#camera,
      screenAnchor,
      zoomFromWheelDelta(this.#camera, deltaY),
    );
    this.scheduleRender();
  }

  fitFrame(frameId: string, paddingScreenPx = 48): boolean {
    const frame = this.#scene.nodes.get(frameId);
    if (!frame || frame.kind !== "FRAME") return false;
    this.#camera = fitWorldRect(frame.world_bounds, this.#viewport, paddingScreenPx);
    this.scheduleRender();
    return true;
  }

  fitSelection(paddingScreenPx = 48): boolean {
    const selected = this.selection.snapshot().ids
      .map((id) => this.#scene.nodes.get(id)?.world_bounds)
      .filter((rect): rect is Rect => Boolean(rect));
    const bounds = unionRects(selected);
    if (!bounds) return false;
    this.#camera = fitWorldRect(bounds, this.#viewport, paddingScreenPx);
    this.scheduleRender();
    return true;
  }

  fitAll(paddingScreenPx = 48): boolean {
    const bounds = unionRects(
      this.#scene.paint_order
        .map((id) => this.#scene.nodes.get(id))
        .filter((node) => node && node.kind !== "DOCUMENT_ROOT" && node.kind !== "GUIDE")
        .map((node) => node!.world_bounds),
    );
    if (!bounds) return false;
    this.#camera = fitWorldRect(bounds, this.#viewport, paddingScreenPx);
    this.scheduleRender();
    return true;
  }

  selectAtScreenPoint(
    point: Point,
    mode: SelectionMode = "replace",
    cycleOffset = 0,
  ): string | null {
    const selected = this.selection.click(
      screenToWorld(point, this.#camera),
      this.#spatial,
      mode,
      cycleOffset,
    );
    this.scheduleRender();
    return selected;
  }

  marqueeScreen(rect: Rect, mode: SelectionMode = "replace"): readonly string[] {
    const normalized = normalizeRect(rect);
    const start = screenToWorld({ x: normalized.x, y: normalized.y }, this.#camera);
    const end = screenToWorld(
      { x: normalized.x + normalized.width, y: normalized.y + normalized.height },
      this.#camera,
    );
    const ids = this.selection.marquee(
      { x: start.x, y: start.y, width: end.x - start.x, height: end.y - start.y },
      this.#spatial,
      mode,
    );
    this.scheduleRender();
    return ids;
  }

  beginTransform(operationPrefix?: string): CanvasTransformSession {
    return new CanvasTransformSession(
      this.#commands.document,
      this.#scene,
      this.selection.transformableIds(this.#scene),
      operationPrefix,
    );
  }

  commitTransform(
    session: CanvasTransformSession,
    label = "transform",
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    const result = this.#commands.dispatch(label, session.operations(), this.#constraints, overrides);
    if (result.accepted) this.#refreshScene();
    else this.scheduleRender();
    return result;
  }

  commitText(
    session: CanvasTextEditSession,
    operationId: string,
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    const op = session.commitOperation(this.#commands.document, operationId);
    const result = this.#commands.dispatch("text-edit", op ? [op] : [], this.#constraints, overrides);
    if (result.accepted && op) this.#refreshScene();
    return result;
  }

  nudge(
    dx: number,
    dy: number,
    overrides: readonly ConstraintOverrideToken[] = [],
  ): CanvasCommandResult {
    const session = this.beginTransform(`canvas-nudge-${getDocumentVersion(this.#commands.document)}`);
    session.previewMove(dx, dy);
    return this.commitTransform(session, "nudge", overrides);
  }

  deleteSelection(overrides: readonly ConstraintOverrideToken[] = []): CanvasCommandResult {
    const selected = new Set(this.selection.snapshot().ids);
    const roots = [...selected].filter((id) => {
      let parentId = this.#scene.nodes.get(id)?.parent_id ?? null;
      while (parentId) {
        if (selected.has(parentId)) return false;
        parentId = this.#scene.nodes.get(parentId)?.parent_id ?? null;
      }
      return id !== this.#scene.root_id;
    });
    const op: DesignOperation = {
      operation_id: `canvas-delete-${getDocumentVersion(this.#commands.document)}`,
      type: "DELETE_NODE",
      target_ids: roots,
      expected_document_version: getDocumentVersion(this.#commands.document),
      payload: {},
      reason: "canvas-delete",
    };
    const result = this.#commands.dispatch(
      "delete",
      roots.length ? [op] : [],
      this.#constraints,
      overrides,
    );
    if (result.accepted && roots.length) {
      this.selection.clear();
      this.#refreshScene();
    }
    return result;
  }

  undo(overrides: readonly ConstraintOverrideToken[] = []): CanvasCommandResult {
    const result = this.#commands.undo(this.#constraints, overrides);
    if (result.accepted) this.#refreshScene();
    return result;
  }

  redo(overrides: readonly ConstraintOverrideToken[] = []): CanvasCommandResult {
    const result = this.#commands.redo(this.#constraints, overrides);
    if (result.accepted) this.#refreshScene();
    return result;
  }

  renderNow(): RendererSyncResult | null {
    if (!this.#renderer) return null;
    this.#renderer.setCamera(this.#camera);
    const visible = new Set(
      this.#spatial
        .query(viewportWorldRect(this.#camera, this.#viewport))
        .map((node) => node.id),
    );
    return this.#renderer.sync(this.#scene, visible);
  }

  scheduleRender(): void {
    if (!this.#renderer || this.#scheduledFrame !== null) return;
    this.#scheduledFrame = this.#requestFrame(() => {
      this.#scheduledFrame = null;
      this.renderNow();
    });
  }

  destroy(): void {
    if (this.#scheduledFrame !== null) {
      this.#cancelFrame(this.#scheduledFrame);
      this.#scheduledFrame = null;
    }
    this.#renderer?.destroy();
  }

  #refreshScene(): void {
    const previousSelection = this.selection.snapshot();
    this.#scene = projectDesignDocument(this.#commands.document);
    this.#spatial.rebuild(this.#scene);
    this.selection.set(
      previousSelection.ids.filter((id) => this.#scene.nodes.has(id)),
      previousSelection.primary_id,
    );
    if (
      previousSelection.isolation_root_id &&
      this.#scene.nodes.has(previousSelection.isolation_root_id)
    ) {
      this.selection.enterIsolation(previousSelection.isolation_root_id, this.#scene);
      this.selection.set(
        previousSelection.ids.filter((id) => this.#scene.nodes.has(id)),
        previousSelection.primary_id,
      );
    }
    this.scheduleRender();
  }
}
