import type { Matrix2D } from "./matrix";
import type { CanvasNodeDiagnostic, CanvasSceneNode, CanvasSceneSnapshot } from "./ir-scene";

export interface RendererSyncResult {
  readonly created: number;
  readonly updated: number;
  readonly removed: number;
  readonly visible: number;
  readonly diagnostics: readonly CanvasNodeDiagnostic[];
}

export interface CanvasRendererAdapter {
  resize(widthCssPx: number, heightCssPx: number, devicePixelRatio: number): void;
  sync(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>): RendererSyncResult;
  destroy(): void;
}

/**
 * Structural PixiJS v8 bridge. The domain package intentionally does not import or persist Pixi types.
 * The web application supplies these bindings from its PixiJS runtime.
 */
export interface PixiDisplayHandle {
  readonly id: string;
}

export interface PixiV8Bindings {
  readonly stage: PixiDisplayHandle;
  createContainer(id: string): PixiDisplayHandle;
  createText(id: string, content: string): PixiDisplayHandle;
  createImage(id: string, assetId: string): PixiDisplayHandle;
  createShape(id: string, node: CanvasSceneNode): PixiDisplayHandle;
  createVideoPoster(id: string, assetId: string | null): PixiDisplayHandle;
  createPlaceholder(id: string, diagnostic: string): PixiDisplayHandle;
  setLocalMatrix(handle: PixiDisplayHandle, matrix: Matrix2D): void;
  setVisible(handle: PixiDisplayHandle, visible: boolean): void;
  setText(handle: PixiDisplayHandle, content: string): void;
  setAsset(handle: PixiDisplayHandle, assetId: string | null): void;
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
}

function createDisplay(bindings: PixiV8Bindings, node: CanvasSceneNode): PixiDisplayHandle {
  switch (node.kind) {
    case "DOCUMENT_ROOT":
    case "FRAME":
    case "GROUP":
    case "MASK":
    case "COMPONENT":
    case "INSTANCE":
      return bindings.createContainer(node.id);
    case "TEXT":
      return bindings.createText(node.id, node.content ?? "");
    case "IMAGE":
      return node.asset_id
        ? bindings.createImage(node.id, node.asset_id)
        : bindings.createPlaceholder(node.id, "missing-image-asset");
    case "SHAPE":
    case "VECTOR_PATH":
    case "GUIDE":
      return bindings.createShape(node.id, node);
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

  sync(scene: CanvasSceneSnapshot, visibleIds: ReadonlySet<string>): RendererSyncResult {
    let created = 0;
    let updated = 0;
    let removed = 0;
    const live = new Set(scene.paint_order);

    for (const [id, entry] of this.#entries) {
      if (live.has(id)) continue;
      const parent = entry.parentId ? this.#entries.get(entry.parentId)?.handle : this.#bindings.stage;
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
        entry = { handle, renderKey: "", parentId: null };
        this.#entries.set(id, entry);
        created += 1;
      }
      const nextParentId = node.parent_id && scene.nodes.has(node.parent_id) ? node.parent_id : null;
      if (entry.parentId !== nextParentId) {
        const previousParent = entry.parentId
          ? this.#entries.get(entry.parentId)?.handle
          : this.#bindings.stage;
        if (previousParent) this.#bindings.removeChild(previousParent, entry.handle);
        const nextParent = nextParentId ? this.#entries.get(nextParentId)?.handle : this.#bindings.stage;
        if (nextParent) this.#bindings.addChild(nextParent, entry.handle);
        entry.parentId = nextParentId;
      }
      if (entry.renderKey !== node.render_key) {
        this.#bindings.setLocalMatrix(entry.handle, node.local_matrix);
        if (node.kind === "TEXT") this.#bindings.setText(entry.handle, node.content ?? "");
        if (["IMAGE", "VIDEO"].includes(node.kind)) {
          this.#bindings.setAsset(entry.handle, node.asset_id ?? null);
        }
        entry.renderKey = node.render_key;
        updated += 1;
      }
      const visible = node.visible && (node.kind === "DOCUMENT_ROOT" || visibleIds.has(id));
      this.#bindings.setVisible(entry.handle, visible);
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
    for (const entry of this.#entries.values()) this.#bindings.destroyDisplay(entry.handle);
    this.#entries.clear();
    this.#bindings.destroy();
  }
}
