import type { ConstraintPreflight, DesignDocument } from "../../design-ir/src/index";
import { CanvasCamera } from "./camera";
import { CanvasOperationGateway } from "./operation-gateway";
import { buildScene, sceneBounds } from "./scene";
import { SelectionModel } from "./selection";
import { ImmediateFrameScheduler, type FrameScheduler } from "./scheduler";
import { SpatialIndex } from "./spatial-index";
import { TransformSession, type TransformMode } from "./transform-session";
import type { CanvasDiagnostic, OperationCommitResult, OperationDescriptor, Point, Rect, RendererAdapter, SceneSnapshot, Viewport } from "./types";

export class CanvasController {
  readonly camera: CanvasCamera;
  readonly selection = new SelectionModel();
  readonly spatial = new SpatialIndex();
  readonly gateway: CanvasOperationGateway;
  private sceneValue: SceneSnapshot;
  private diagnosticsValue: readonly CanvasDiagnostic[] = [];
  private framePending = false;
  constructor(document: DesignDocument, private readonly renderer: RendererAdapter, options: { viewport?: Viewport; preflight?: ConstraintPreflight; scheduler?: FrameScheduler } = {}) {
    this.camera = new CanvasCamera(undefined, options.viewport);
    this.gateway = new CanvasOperationGateway(document, options.preflight);
    this.sceneValue = buildScene(document); this.spatial.rebuild(this.sceneValue); this.diagnosticsValue = this.sceneValue.diagnostics;
    this.scheduler = options.scheduler ?? new ImmediateFrameScheduler();
  }
  private readonly scheduler: FrameScheduler;
  get document(): DesignDocument { return this.gateway.document; }
  get scene(): SceneSnapshot { return this.sceneValue; }
  get diagnostics(): readonly CanvasDiagnostic[] { return this.diagnosticsValue; }
  async mount(): Promise<void> { await this.renderer.mount(); this.scheduleRender(); }
  replaceDocument(document: DesignDocument): void { this.gateway.replaceDocument(document); this.rebuild(); }
  private rebuild(): void { this.sceneValue = buildScene(this.document); this.spatial.rebuild(this.sceneValue); this.diagnosticsValue = this.sceneValue.diagnostics; this.scheduleRender(); }
  scheduleRender(): void {
    if (this.framePending) return; this.framePending = true;
    this.scheduler.request(() => { this.framePending = false; this.renderNow(); });
  }
  renderNow(): void {
    const visible = this.spatial.query(this.camera.worldViewportRect(128));
    this.renderer.render({ camera: this.camera.state, viewport: this.camera.viewport, visibleNodes: visible, selectedIds: this.selection.ids, diagnostics: this.diagnosticsValue });
  }
  setViewport(viewport: Viewport): void { this.camera.setViewport(viewport); this.scheduleRender(); }
  pan(dx: number, dy: number): void { this.camera.panByScreen(dx, dy); this.scheduleRender(); }
  zoomToCursor(point: Point, zoom: number): void { this.camera.zoomToCursor(point, zoom); this.scheduleRender(); }
  fitAll(): void { const bounds = sceneBounds(this.sceneValue); if (bounds) this.camera.fitBounds(bounds); this.scheduleRender(); }
  fitSelection(): void { const bounds = sceneBounds(this.sceneValue, [...this.selection.ids]); if (bounds) this.camera.fitBounds(bounds); this.scheduleRender(); }
  selectAt(screenPoint: Point, options: { shift?: boolean; cycle?: number } = {}): string | null { const world = this.camera.screenToWorld(screenPoint); const id = this.selection.click(this.sceneValue, this.spatial, world, options); this.scheduleRender(); return id; }
  marquee(screenRect: Rect, shift = false): readonly string[] { const a = this.camera.screenToWorld({ x: screenRect.x, y: screenRect.y }); const b = this.camera.screenToWorld({ x: screenRect.x + screenRect.width, y: screenRect.y + screenRect.height }); const ids = this.selection.marquee(this.sceneValue, { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y) }, { shift }); this.scheduleRender(); return ids; }
  beginTransform(mode: TransformMode, ids: readonly string[] = this.selection.transformable(this.sceneValue)): TransformSession { return new TransformSession(mode, ids, this.sceneValue, this.gateway); }
  commit(descriptor: OperationDescriptor): OperationCommitResult { const beforeIds = new Set(this.sceneValue.orderedIds); const result = this.gateway.commit(descriptor); if (result.ok) { this.rebuild(); for (const id of beforeIds) if (!this.sceneValue.nodes.has(id)) this.renderer.destroyNode(id); } else this.scheduleRender(); return result; }
  syncAfterExternalCommit(): void { this.rebuild(); }
  destroy(): void { this.renderer.destroy(); }
}
