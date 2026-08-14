import type { CompiledSceneNode } from "./compiler-types";
import type { CanvasNodeDiagnostic, CanvasSceneNode, CanvasSceneSnapshot } from "./ir-scene";
import type { Matrix2D } from "./matrix";
import type { CameraState } from "./types";

export interface RendererSyncResult {
  readonly created: number;
  readonly updated: number;
  readonly removed: number;
  readonly visible: number;
  readonly diagnostics: readonly CanvasNodeDiagnostic[];
}

export interface CanvasRendererAdapter {
  resize(widthCssPx: number, heightCssPx: number, devicePixelRatio: number): void;
  setCamera(camera: CameraState): void;
  sync(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>): RendererSyncResult;
  destroy(): void;
}

export interface PixiDisplayHandle {
  readonly id: string;
}

export interface PixiV8Bindings {
  readonly stage: PixiDisplayHandle;
  createContainer(id: string): PixiDisplayHandle;
  createText(id: string, content: string, node: CanvasSceneNode): PixiDisplayHandle;
  createImage(id: string, assetId: string): PixiDisplayHandle;
  createShape(id: string, node: CanvasSceneNode): PixiDisplayHandle;
  createVideoPoster(id: string, assetId: string | null): PixiDisplayHandle;
  createPlaceholder(id: string, diagnostic: string): PixiDisplayHandle;
  setLocalMatrix(handle: PixiDisplayHandle, matrix: Matrix2D): void;
  setCamera(camera: CameraState): void;
  redrawShape(handle: PixiDisplayHandle, node: CanvasSceneNode): void;
  setDisplaySize(handle: PixiDisplayHandle, width: number, height: number): void;
  setVisible(handle: PixiDisplayHandle, visible: boolean): void;
  setText(handle: PixiDisplayHandle, content: string, node: CanvasSceneNode): void;
  setAsset(handle: PixiDisplayHandle, assetId: string | null): void;
  setMask(handle: PixiDisplayHandle, mask: PixiDisplayHandle | null): void;
  addChild(parent: PixiDisplayHandle, child: PixiDisplayHandle): void;
  removeChild(parent: PixiDisplayHandle, child: PixiDisplayHandle): void;
  destroyDisplay(handle: PixiDisplayHandle): void;
  resize(widthCssPx: number, heightCssPx: number, devicePixelRatio: number): void;
  destroy(): void;
}

interface RenderEntry {
  readonly handle: PixiDisplayHandle;
  renderKey: string;
  parentId: string | null;
  maskId: string | null;
}

const SHAPE_KINDS = new Set(["FRAME", "MASK", "SHAPE", "VECTOR_PATH", "GUIDE"]);

function compiledNode(node: CanvasSceneNode): CompiledSceneNode | null {
  return "resolved_style" in node ? (node as CompiledSceneNode) : null;
}

function nodeMaskId(node: CanvasSceneNode): string | null {
  const compiled = compiledNode(node);
  return compiled?.mask_id ?? compiled?.clip_id ?? null;
}

function createDisplay(bindings: PixiV8Bindings, node: CanvasSceneNode): PixiDisplayHandle {
  switch (node.kind) {
    case "DOCUMENT_ROOT":
    case "GROUP":
    case "COMPONENT":
    case "INSTANCE":
      return bindings.createContainer(node.id);
    case "FRAME":
    case "MASK":
    case "SHAPE":
    case "VECTOR_PATH":
    case "GUIDE":
      return bindings.createShape(node.id, node);
    case "TEXT":
      return bindings.createText(node.id, node.content ?? "", node);
    case "IMAGE":
      return node.asset_id
        ? bindings.createImage(node.id, node.asset_id)
        : bindings.createPlaceholder(node.id, "missing-image-asset");
    case "VIDEO":
      return bindings.createVideoPoster(node.id, node.asset_id ?? null);
    default:
      return bindings.createPlaceholder(node.id, `unsupported:${node.kind}`);
  }
}

export class PixiV8RendererAdapter implements CanvasRendererAdapter {
  readonly #bindings: PixiV8Bindings;
  readonly #entries = new Map<string, RenderEntry>();

  constructor(bindings: PixiV8Bindings) {
    this.#bindings = bindings;
  }

  resize(widthCssPx: number, heightCssPx: number, devicePixelRatio: number): void {
    this.#bindings.resize(widthCssPx, heightCssPx, devicePixelRatio);
  }

  setCamera(camera: CameraState): void {
    this.#bindings.setCamera(camera);
  }

  sync(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>): RendererSyncResult {
    let created = 0;
    let updated = 0;
    let removed = 0;
    const live = new Set(scene.paint_order);

    for (const [id, entry] of [...this.#entries].reverse()) {
      if (live.has(id)) continue;
      const parent = entry.parentId
        ? this.#entries.get(entry.parentId)?.handle
        : this.#bindings.stage;
      if (parent) this.#bindings.removeChild(parent, entry.handle);
      this.#bindings.destroyDisplay(entry.handle);
      this.#entries.delete(id);
      removed += 1;
    }

    for (const id of scene.paint_order) {
      const node = scene.nodes.get(id);
      if (!node) continue;
      let entry = this.#entries.get(id);
      if (!entry) {
        const handle = createDisplay(this.#bindings, node);
        entry = { handle, renderKey: "", parentId: null, maskId: null };
        this.#entries.set(id, entry);
        created += 1;
      }
      const nextParentId =
        node.parent_id && scene.nodes.has(node.parent_id) ? node.parent_id : null;
      if (entry.parentId !== nextParentId) {
        const previousParent = entry.parentId
          ? this.#entries.get(entry.parentId)?.handle
          : this.#bindings.stage;
        if (previousParent) this.#bindings.removeChild(previousParent, entry.handle);
        const nextParent = nextParentId
          ? this.#entries.get(nextParentId)?.handle
          : this.#bindings.stage;
        if (nextParent) this.#bindings.addChild(nextParent, entry.handle);
        entry.parentId = nextParentId;
      }
      if (entry.renderKey !== node.render_key) {
        this.#bindings.setLocalMatrix(entry.handle, node.local_matrix);
        if (SHAPE_KINDS.has(node.kind)) this.#bindings.redrawShape(entry.handle, node);
        if (node.kind === "TEXT") this.#bindings.setText(entry.handle, node.content ?? "", node);
        if (["IMAGE", "VIDEO"].includes(node.kind)) {
          this.#bindings.setAsset(entry.handle, node.asset_id ?? null);
          this.#bindings.setDisplaySize(
            entry.handle,
            node.local_bounds.width,
            node.local_bounds.height,
          );
        }
        entry.renderKey = node.render_key;
        updated += 1;
      }
      const visible =
        node.visible && (node.kind === "DOCUMENT_ROOT" || visibleIds.has(id));
      this.#bindings.setVisible(entry.handle, visible);
    }

    for (const id of scene.paint_order) {
      const node = scene.nodes.get(id);
      const entry = this.#entries.get(id);
      if (!node || !entry) continue;
      const nextMaskId = nodeMaskId(node);
      if (entry.maskId === nextMaskId) continue;
      const maskHandle = nextMaskId ? this.#entries.get(nextMaskId)?.handle ?? null : null;
      this.#bindings.setMask(entry.handle, maskHandle);
      entry.maskId = nextMaskId;
    }

    return {
      created,
      updated,
      removed,
      visible: visibleIds.size,
      diagnostics: scene.diagnostics,
    };
  }

  destroy(): void {
    for (const entry of [...this.#entries.values()].reverse()) {
      this.#bindings.destroyDisplay(entry.handle);
    }
    this.#entries.clear();
    this.#bindings.destroy();
  }
}
