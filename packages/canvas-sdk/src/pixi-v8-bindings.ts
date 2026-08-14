import type { CanvasSceneNode } from "./ir-scene";
import type { Matrix2D } from "./matrix";
import type { PixiDisplayHandle, PixiV8Bindings } from "./renderer";
import type { CameraState } from "./types";

export type PixiMatrixLike = object;

export interface PixiContainerLike {
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

interface ManagedPixiHandle extends PixiDisplayHandle, PixiContainerLike {}

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
  return handle as ManagedPixiHandle;
}

function numericFill(node: CanvasSceneNode): number {
  const fill = node.metadata.fill;
  if (typeof fill === "number" && Number.isFinite(fill)) return fill;
  if (node.kind === "FRAME") return 0xffffff;
  if (node.kind === "GUIDE") return 0x5d7cff;
  return 0xb8b8b8;
}

function missingGraphic(runtime: PixiV8RuntimeModule, id: string): ManagedPixiHandle {
  const graphics = managed(new runtime.Graphics(), id);
  graphics.rect(0, 0, 64, 64).fill(0xd0d0d0);
  if (graphics.stroke) graphics.stroke({ width: 1, color: 0x777777 });
  return graphics;
}

export function createPixiV8Bindings(
  runtime: PixiV8RuntimeModule,
  host: PixiApplicationHost,
  textures: PixiTextureResolver,
): PixiV8Bindings {
  const stage = managed(host.stage, "__lumi_canvas_stage__");
  const createGraphics = (id: string, node: CanvasSceneNode): ManagedPixiHandle => {
    const graphics = managed(new runtime.Graphics(), id);
    graphics
      .rect(
        0,
        0,
        Math.max(0, node.local_bounds.width),
        Math.max(0, node.local_bounds.height),
      )
      .fill(numericFill(node));
    if (node.kind === "GUIDE" && graphics.stroke) {
      graphics.stroke({ width: 1, color: numericFill(node) });
    }
    return graphics;
  };
  const matrix = (value: Matrix2D): PixiMatrixLike =>
    new runtime.Matrix(value.a, value.b, value.c, value.d, value.tx, value.ty);

  return {
    stage,
    createContainer(id) {
      return managed(new runtime.Container(), id);
    },
    createText(id, content) {
      return managed(new runtime.Text({ text: content }), id);
    },
    createImage(id, assetId) {
      const texture = textures.textureForAsset(assetId);
      return texture === null
        ? missingGraphic(runtime, id)
        : managed(runtime.Sprite.from(texture), id);
    },
    createShape(id, node) {
      return createGraphics(id, node);
    },
    createVideoPoster(id, assetId) {
      if (!assetId) return missingGraphic(runtime, id);
      const texture = textures.textureForAsset(assetId);
      return texture === null
        ? missingGraphic(runtime, id)
        : managed(runtime.Sprite.from(texture), id);
    },
    createPlaceholder(id) {
      return missingGraphic(runtime, id);
    },
    setLocalMatrix(handle, value) {
      asContainer(handle).setFromMatrix(matrix(value));
    },
    setCamera(camera: CameraState) {
      stage.setFromMatrix(
        matrix({
          a: camera.zoom,
          b: 0,
          c: 0,
          d: camera.zoom,
          tx: -camera.x * camera.zoom,
          ty: -camera.y * camera.zoom,
        }),
      );
    },
    setVisible(handle, visible) {
      asContainer(handle).visible = visible;
    },
    setText(handle, content) {
      const text = handle as PixiTextLike & PixiDisplayHandle;
      if (typeof text.text === "string") text.text = content;
    },
    setAsset(handle, assetId) {
      if (!assetId) return;
      const texture = textures.textureForAsset(assetId);
      if (texture === null) return;
      const sprite = handle as PixiSpriteLike & PixiDisplayHandle;
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
