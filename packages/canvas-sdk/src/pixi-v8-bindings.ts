import type { CompiledSceneNode, ResolvedCompilerStyle } from "./compiler-types";
import type { CanvasSceneNode } from "./ir-scene";
import type { Matrix2D } from "./matrix";
import type { PixiDisplayHandle, PixiV8Bindings } from "./renderer";
import type { CameraState } from "./types";

export type PixiMatrixLike = object;

export interface PixiContainerLike {
  visible: boolean;
  width: number;
  height: number;
  alpha?: number;
  blendMode?: string;
  mask?: unknown;
  label?: string;
  addChild(child: PixiContainerLike): unknown;
  removeChild(child: PixiContainerLike): unknown;
  destroy(options?: unknown): void;
  setFromMatrix(matrix: PixiMatrixLike): void;
  setSize?(width: number, height: number): void;
}

export interface PixiTextLike extends PixiContainerLike {
  text: string;
  style?: unknown;
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
  readonly Text: new (options: { readonly text: string; readonly style?: Readonly<Record<string, unknown>> }) => PixiTextLike;
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

function asGraphics(handle: PixiDisplayHandle): PixiGraphicsLike {
  return handle as PixiGraphicsLike & PixiDisplayHandle;
}

function compiled(node: CanvasSceneNode): CompiledSceneNode | null {
  return "resolved_style" in node ? (node as CompiledSceneNode) : null;
}

function resolvedStyle(node: CanvasSceneNode): ResolvedCompilerStyle {
  return compiled(node)?.resolved_style ?? {};
}

function styleValue(style: ResolvedCompilerStyle, key: string): unknown {
  return style[key];
}

function numericFill(node: CanvasSceneNode): unknown {
  const style = resolvedStyle(node);
  const compiledFill = styleValue(style, "fill");
  if (compiledFill !== undefined && compiledFill !== null) return compiledFill;
  const fill = node.metadata.fill;
  if (typeof fill === "number" && Number.isFinite(fill)) return fill;
  if (typeof fill === "string") return fill;
  if (node.kind === "FRAME") return 0xffffff;
  if (node.kind === "GUIDE") return 0x5d7cff;
  return 0xb8b8b8;
}

function textStyle(node: CanvasSceneNode): Readonly<Record<string, unknown>> {
  const style = resolvedStyle(node);
  const compiledNode = compiled(node);
  const font = compiledNode?.resolved_text?.font;
  const result: Record<string, unknown> = {};
  const fill = styleValue(style, "fill");
  const fontSize = styleValue(style, "font_size");
  const fontFamily = styleValue(style, "font_family");
  const fontWeight = styleValue(style, "font_weight");
  const lineHeight = styleValue(style, "line_height");
  const align = styleValue(style, "align");
  if (fill !== undefined) result.fill = fill;
  if (fontSize !== undefined) result.fontSize = fontSize;
  if (font?.family) result.fontFamily = font.family;
  else if (fontFamily !== undefined) result.fontFamily = fontFamily;
  if (font?.weight !== undefined) result.fontWeight = font.weight;
  else if (fontWeight !== undefined) result.fontWeight = fontWeight;
  if (lineHeight !== undefined) result.lineHeight = lineHeight;
  if (align !== undefined) result.align = align;
  return result;
}

function applyContainerStyle(handle: PixiDisplayHandle, node: CanvasSceneNode): void {
  const display = asContainer(handle);
  const style = resolvedStyle(node);
  const opacity = styleValue(style, "opacity");
  const blendMode = styleValue(style, "blend_mode");
  if (typeof opacity === "number" && Number.isFinite(opacity)) {
    display.alpha = Math.max(0, Math.min(1, opacity));
  }
  if (typeof blendMode === "string" && blendMode.length > 0) display.blendMode = blendMode;
}

function applyTextStyle(handle: PixiDisplayHandle, node: CanvasSceneNode): void {
  const text = handle as PixiTextLike & PixiDisplayHandle;
  text.style = textStyle(node);
  applyContainerStyle(handle, node);
}

function drawGraphics(graphics: PixiGraphicsLike, node: CanvasSceneNode): void {
  graphics.clear();
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
  applyContainerStyle(graphics as PixiGraphicsLike & PixiDisplayHandle, node);
}

function missingGraphic(runtime: PixiV8RuntimeModule, id: string): ManagedPixiHandle {
  const graphics = managed(new runtime.Graphics(), id);
  graphics.clear().rect(0, 0, 64, 64).fill(0xd0d0d0);
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
    drawGraphics(graphics, node);
    return graphics;
  };
  const matrix = (value: Matrix2D): PixiMatrixLike =>
    new runtime.Matrix(value.a, value.b, value.c, value.d, value.tx, value.ty);

  return {
    stage,
    createContainer(id) {
      return managed(new runtime.Container(), id);
    },
    createText(id, content, node) {
      const text = managed(new runtime.Text({ text: content, style: textStyle(node) }), id);
      applyTextStyle(text, node);
      return text;
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
    redrawShape(handle, node) {
      drawGraphics(asGraphics(handle), node);
    },
    setDisplaySize(handle, width, height) {
      const display = asContainer(handle);
      if (display.setSize) display.setSize(Math.max(0, width), Math.max(0, height));
      else {
        display.width = Math.max(0, width);
        display.height = Math.max(0, height);
      }
    },
    setVisible(handle, visible) {
      asContainer(handle).visible = visible;
    },
    setText(handle, content, node) {
      const text = handle as PixiTextLike & PixiDisplayHandle;
      text.text = content;
      applyTextStyle(handle, node);
    },
    setAsset(handle, assetId) {
      if (!assetId) return;
      const texture = textures.textureForAsset(assetId);
      if (texture === null) return;
      const sprite = handle as PixiSpriteLike & PixiDisplayHandle;
      if ("texture" in sprite) sprite.texture = texture;
    },
    setMask(handle, mask) {
      asContainer(handle).mask = mask ? asContainer(mask) : null;
    },
    addChild(parent, child) {
      asContainer(parent).addChild(asContainer(child));
    },
    removeChild(parent, child) {
      asContainer(parent).removeChild(asContainer(child));
    },
    destroyDisplay(handle) {
      asContainer(handle).destroy({ children: false });
    },
    resize(widthCssPx, heightCssPx, devicePixelRatio) {
      host.resize(widthCssPx, heightCssPx, devicePixelRatio);
    },
    destroy() {
      host.destroy();
    },
  };
}
