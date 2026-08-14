import type { CanvasSceneNode } from "./ir-scene";
import type { Matrix2D } from "./matrix";
import type { PixiDisplayHandle, PixiV8Bindings } from "./renderer";

export interface PixiMatrixLike {}

export interface PixiContainerLike extends PixiDisplayHandle {
  visible: boolean;
  label?: string;
  addChild(child: PixiContainerLike): unknown;
  removeChild(child: PixiContainerLike): unknown;
  destroy(options?: unknown): void;
  setFromMatrix(matrix: PixiMatrixLike): void;
}

export interface PixiTextLike extends PixiContainerLike {
  text: string;
}

export interface PixiSpriteLike extends PixiContainerLike {
  texture: unknown;
}

export interface PixiGraphicsLike extends PixiContainerLike {
  clear(): PixiGraphicsLike;
  rect(x: number, y: number, width: number, height: number): PixiGraphicsLike;
  fill(value: unknown): PixiGraphicsLike;
  stroke?(value: unknown): PixiGraphicsLike;
}

export interface PixiV8RuntimeModule {
  readonly Container: new () => PixiContainerLike;
  readonly Text: new (options: { readonly text: string }) => PixiTextLike;
  readonly Graphics: new () => PixiGraphicsLike;
  readonly Matrix: new (
    a: number,
    b: number,
    c: number,
    d: number,
    tx: number,
    ty: number,
  ) => PixiMatrixLike;
  readonly Sprite: {
    from(source: unknown): PixiSpriteLike;
  };
}

export interface PixiApplicationHost {
  readonly stage: PixiContainerLike;
  resize(widthCssPx: number, heightCssPx: number, devicePixelRatio: number): void;
  destroy(): void;
}

export interface PixiTextureResolver {
  textureForAsset(assetId: string): unknown | null;
}

interface ManagedPixiHandle extends PixiContainerLike {
  readonly id: string;
}

function managed<T extends PixiContainerLike>(object: T, id: string): T & ManagedPixiHandle {
  object.label = id;
  Object.defineProperty(object, "id", {
    value: id,
    enumerable: false,
    writable: false,
    configurable: false,
  });
  return object as T & ManagedPixiHandle;
}

function asContainer(handle: PixiDisplayHandle): PixiContainerLike {
  return handle as PixiContainerLike;
}

function numericFill(node: CanvasSceneNode): number {
  const fill = node.metadata.fill;
  if (typeof fill === "number" && Number.isFinite(fill)) return fill;
  if (node.kind === "FRAME") return 0xffffff;
  if (node.kind === "GUIDE") return 0x5d7cff;
  return 0xb8b8b8;
}

export function createPixiV8Bindings(
  runtime: PixiV8RuntimeModule,
  host: PixiApplicationHost,
  textures: PixiTextureResolver,
): PixiV8Bindings {
  const createGraphics = (id: string, node: CanvasSceneNode): ManagedPixiHandle => {
    const graphics = managed(new runtime.Graphics(), id);
    graphics
      .rect(0, 0, Math.max(0, node.local_bounds.width), Math.max(0, node.local_bounds.height))
      .fill(numericFill(node));
    if (node.kind === "GUIDE" && graphics.stroke) graphics.stroke({ width: 1, color: numericFill(node) });
    return graphics;
  };

  return {
    stage: host.stage,
    createContainer(id) {
      return managed(new runtime.Container(), id);
    },
    createText(id, content) {
      return managed(new runtime.Text({ text: content }), id);
    },
    createImage(id, assetId) {
      const texture = textures.textureForAsset(assetId);
      if (texture === null) return createGraphics(id, { id, kind: "IMAGE", parent_id: null, children: [], depth: 0, paint_order: 0, visible: true, locked: false, local_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 }, world_matrix: { a: 1, b: 0, c: 0, d: 1, tx: 0, ty: 0 }, local_bounds: { x: 0, y: 0, width: 64, height: 64 }, world_bounds: { x: 0, y: 0, width: 64, height: 64 }, render_key: "missing", metadata: {} });
      return managed(runtime.Sprite.from(texture), id);
    },
    createShape(id, node) {
      return createGraphics(id, node);
    },
    createVideoPoster(id, assetId) {
      if (!assetId) return managed(new runtime.Container(), id);
      const texture = textures.textureForAsset(assetId);
      return texture === null ? managed(new runtime.Container(), id) : managed(runtime.Sprite.from(texture), id);
    },
    createPlaceholder(id) {
      const graphics = managed(new runtime.Graphics(), id);
      graphics.rect(0, 0, 64, 64).fill(0xd0d0d0);
      if (graphics.stroke) graphics.stroke({ width: 1, color: 0x777777 });
      return graphics;
    },
    setLocalMatrix(handle, matrix: Matrix2D) {
      asContainer(handle).setFromMatrix(
        new runtime.Matrix(matrix.a, matrix.b, matrix.c, matrix.d, matrix.tx, matrix.ty),
      );
    },
    setVisible(handle, visible) {
      asContainer(handle).visible = visible;
    },
    setText(handle, content) {
      const text = handle as PixiTextLike;
      if (typeof text.text === "string") text.text = content;
    },
    setAsset(handle, assetId) {
      if (!assetId) return;
      const texture = textures.textureForAsset(assetId);
      if (texture === null) return;
      const sprite = handle as PixiSpriteLike;
      if ("texture" in sprite) sprite.texture = texture;
    },
    addChild(parent, child) {
      asContainer(parent).addChild(asContainer(child));
    },
    removeChild(parent, child) {
      asContainer(parent).removeChild(asContainer(child));
    },
    destroyDisplay(handle) {
      asContainer(handle).destroy({ children: true });
    },
    resize(widthCssPx, heightCssPx, devicePixelRatio) {
      host.resize(widthCssPx, heightCssPx, devicePixelRatio);
    },
    destroy() {
      host.destroy();
    },
  };
}
