import {
  CommandStack,
  SpikeSceneStore,
  createSpikeSeedScene,
  cullNodes,
  nodeBounds,
  nodesInRect,
  normalizeRect,
  screenToWorld,
  unionBounds,
  worldToScreen,
  zoomAtScreenPoint,
  type CameraState,
  type Point,
  type Rect,
  type SpikeNode,
} from "@lumi/canvas-sdk";

import { runVirtualizedCanvasBenchmark } from "./virtualized-benchmark";

export const PIXI_VERSION = "8.19.0";
export const PIXI_CDN_URL = `https://cdn.jsdelivr.net/npm/pixi.js@${PIXI_VERSION}/dist/pixi.min.js`;

interface PixiPointLike {
  set(x: number, y?: number): void;
}

interface PixiDisplayObject {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  visible: boolean;
  alpha: number;
  zIndex: number;
  position: PixiPointLike;
  scale: PixiPointLike;
  pivot: PixiPointLike;
  destroy(options?: unknown): void;
}

interface PixiContainer extends PixiDisplayObject {
  sortableChildren: boolean;
  addChild<T extends PixiDisplayObject>(child: T): T;
  removeChild<T extends PixiDisplayObject>(child: T): T;
  removeChildren(): PixiDisplayObject[];
}

interface PixiGraphics extends PixiDisplayObject {
  clear(): this;
  rect(x: number, y: number, width: number, height: number): this;
  roundRect(
    x: number,
    y: number,
    width: number,
    height: number,
    radius: number,
  ): this;
  fill(color: number | { color: number; alpha?: number }): this;
  stroke(options: { color: number; width: number; alpha?: number }): this;
}

interface PixiText extends PixiDisplayObject {
  text: string;
}

interface PixiTicker {
  start(): void;
  stop(): void;
}

interface PixiRenderer {
  readonly type?: number | string;
  readonly name?: string;
  readonly resolution?: number;
}

interface PixiApplication {
  readonly canvas: HTMLCanvasElement;
  readonly stage: PixiContainer;
  readonly ticker: PixiTicker;
  readonly renderer: PixiRenderer;
  init(options: Record<string, unknown>): Promise<void>;
  destroy(removeView?: boolean, options?: unknown): void;
}

interface PixiNamespace {
  readonly VERSION?: string;
  readonly Application: new () => PixiApplication;
  readonly Container: new () => PixiContainer;
  readonly Graphics: new () => PixiGraphics;
  readonly Text: new (options: Record<string, unknown>) => PixiText;
  readonly HTMLText?: new (options: Record<string, unknown>) => PixiText;
  readonly Sprite: new (texture: unknown) => PixiDisplayObject;
  readonly Assets: {
    load(source: string): Promise<unknown>;
    unload?(source: string): Promise<void>;
  };
}

declare global {
  interface Window {
    PIXI?: PixiNamespace;
    __LUMI_CANVAS_SPIKE__?: {
      runBenchmark(): Promise<CanvasSpikeBenchmarkReport>;
      snapshot(): CanvasSpikeSnapshot;
      runtimeVersion: string;
    };
  }
}

export type ScreenRect = Rect;

export interface CanvasSpikeSnapshot {
  readonly ready: boolean;
  readonly renderer: string;
  readonly pixiVersion: string;
  readonly camera: CameraState;
  readonly selectedIds: readonly string[];
  readonly selectionRect: ScreenRect | null;
  readonly marqueeRect: ScreenRect | null;
  readonly selectedImageRef: string | null;
  readonly nodeCount: number;
  readonly visibleNodeCount: number;
  readonly history: { readonly canUndo: boolean; readonly canRedo: boolean };
}

export interface FrameMetric {
  readonly name: string;
  readonly nodeCount: number;
  readonly frames: number;
  readonly p50FrameMs: number;
  readonly p95FrameMs: number;
  readonly meanFrameMs: number;
  readonly approximateFps: number;
}

export interface CanvasSpikeBenchmarkReport {
  readonly schemaVersion: 1;
  readonly pixiVersion: string;
  readonly renderer: string;
  readonly devicePixelRatio: number;
  readonly userAgent: string;
  readonly measuredAt: string;
  readonly metrics: readonly FrameMetric[];
  readonly notes: readonly string[];
}

type PointerMode =
  | "idle"
  | "pan"
  | "drag"
  | "marquee"
  | "resize"
  | "rotate"
  | "pinch";
type ResizeHandle = "nw" | "ne" | "sw" | "se";

interface ActivePointer {
  readonly id: number;
  point: Point;
}

interface InteractionState {
  mode: PointerMode;
  pointerId: number | null;
  startScreen: Point;
  lastScreen: Point;
  beforeNodes: SpikeNode[];
  marqueeStart: Point | null;
  resizeHandle: ResizeHandle | null;
  transformBounds: Rect | null;
  transformNodes: SpikeNode[];
  rotationStartAngle: number;
  pinchStartDistance: number;
  pinchStartCenter: Point;
  pinchStartCamera: CameraState;
}

export interface TextEditorRequest {
  readonly nodeId: string;
  readonly text: string;
  readonly rect: ScreenRect;
}

export interface CanvasSpikeRuntimeOptions {
  readonly host: HTMLElement;
  readonly onSnapshot: (snapshot: CanvasSpikeSnapshot) => void;
  readonly onTextEdit: (request: TextEditorRequest | null) => void;
}

const PRODUCT_DATA_URI =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="560" viewBox="0 0 800 560"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#d8b56d"/><stop offset="1" stop-color="#4f3826"/></linearGradient></defs><rect width="800" height="560" rx="48" fill="#ece8df"/><ellipse cx="400" cy="450" rx="250" ry="40" fill="#000" opacity=".12"/><rect x="250" y="100" width="300" height="320" rx="80" fill="url(#g)"/><circle cx="400" cy="210" r="70" fill="#f7f1e4" opacity=".7"/><path d="M330 330h140" stroke="#f7f1e4" stroke-width="24" stroke-linecap="round"/></svg>`,
  );

function cloneNodes(nodes: readonly SpikeNode[]): SpikeNode[] {
  return nodes.map((node) => ({ ...node }));
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function midpoint(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function rendererName(renderer: PixiRenderer): string {
  if (renderer.name) {
    return renderer.name;
  }
  if (typeof renderer.type === "string") {
    return renderer.type;
  }
  return "webgl-preferred";
}

export class CanvasSpikeRuntime {
  readonly #host: HTMLElement;
  readonly #onSnapshot: (snapshot: CanvasSpikeSnapshot) => void;
  readonly #onTextEdit: (request: TextEditorRequest | null) => void;
  readonly #store = new SpikeSceneStore(createSpikeSeedScene());
  readonly #history = new CommandStack(100);
  readonly #displays = new Map<string, PixiDisplayObject>();
  readonly #activePointers = new Map<number, ActivePointer>();
  readonly #selected = new Set<string>();
  #pixi: PixiNamespace | null = null;
  #app: PixiApplication | null = null;
  #world: PixiContainer | null = null;
  #camera: CameraState = { x: -80, y: -60, zoom: 0.8 };
  #marqueeRect: ScreenRect | null = null;
  #spaceDown = false;
  #clipboard: SpikeNode[] = [];
  #disposed = false;
  #visibleNodeCount = 0;
  #interaction: InteractionState = this.#idleInteraction();

  constructor(options: CanvasSpikeRuntimeOptions) {
    this.#host = options.host;
    this.#onSnapshot = options.onSnapshot;
    this.#onTextEdit = options.onTextEdit;
  }

  #idleInteraction(): InteractionState {
    return {
      mode: "idle",
      pointerId: null,
      startScreen: { x: 0, y: 0 },
      lastScreen: { x: 0, y: 0 },
      beforeNodes: [],
      marqueeStart: null,
      resizeHandle: null,
      transformBounds: null,
      transformNodes: [],
      rotationStartAngle: 0,
      pinchStartDistance: 0,
      pinchStartCenter: { x: 0, y: 0 },
      pinchStartCamera: this.#camera,
    };
  }

  async init(): Promise<void> {
    const pixi = window.PIXI;
    if (!pixi) {
      throw new Error("PixiJS global is not loaded");
    }
    this.#pixi = pixi;
    const app = new pixi.Application();
    await app.init({
      resizeTo: this.#host,
      background: 0x171717,
      antialias: true,
      autoDensity: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      preference: "webgl",
    });
    this.#app = app;
    app.canvas.dataset.canvasSpike = "pixi";
    app.canvas.tabIndex = 0;
    app.canvas.style.width = "100%";
    app.canvas.style.height = "100%";
    app.canvas.style.display = "block";
    app.canvas.style.touchAction = "none";
    this.#host.replaceChildren(app.canvas);

    const world = new pixi.Container();
    world.sortableChildren = true;
    app.stage.addChild(world);
    this.#world = world;
    await this.#syncDisplays(true);
    this.#applyCamera();
    this.#bindEvents();
    this.#emit();

    window.__LUMI_CANVAS_SPIKE__ = {
      runtimeVersion: PIXI_VERSION,
      runBenchmark: () => this.runBenchmark(),
      snapshot: () => this.snapshot(),
    };
  }

  dispose(): void {
    this.#disposed = true;
    this.#unbindEvents();
    this.#onTextEdit(null);
    if (window.__LUMI_CANVAS_SPIKE__) {
      delete window.__LUMI_CANVAS_SPIKE__;
    }
    this.#app?.destroy(true, {
      children: true,
      texture: true,
      textureSource: true,
    });
    this.#displays.clear();
    this.#app = null;
    this.#world = null;
  }

  snapshot(): CanvasSpikeSnapshot {
    const selectedNodes = this.#store
      .list()
      .filter((node) => this.#selected.has(node.id));
    const worldBounds = unionBounds(selectedNodes);
    let selectionRect: ScreenRect | null = null;
    if (worldBounds) {
      const topLeft = worldToScreen(
        { x: worldBounds.x, y: worldBounds.y },
        this.#camera,
      );
      const bottomRight = worldToScreen(
        {
          x: worldBounds.x + worldBounds.width,
          y: worldBounds.y + worldBounds.height,
        },
        this.#camera,
      );
      selectionRect = {
        x: topLeft.x,
        y: topLeft.y,
        width: bottomRight.x - topLeft.x,
        height: bottomRight.y - topLeft.y,
      };
    }
    const selectedImage = selectedNodes.find((node) => node.kind === "image");
    return {
      ready: this.#app !== null,
      renderer: this.#app ? rendererName(this.#app.renderer) : "not-ready",
      pixiVersion: this.#pixi?.VERSION ?? PIXI_VERSION,
      camera: this.#camera,
      selectedIds: [...this.#selected],
      selectionRect,
      marqueeRect: this.#marqueeRect,
      selectedImageRef: selectedImage?.assetRef ?? null,
      nodeCount: this.#store.list().length,
      visibleNodeCount: this.#visibleNodeCount,
      history: {
        canUndo: this.#history.canUndo,
        canRedo: this.#history.canRedo,
      },
    };
  }

  #emit(): void {
    if (!this.#disposed) {
      this.#onSnapshot(this.snapshot());
    }
  }

  #bindEvents(): void {
    const canvas = this.#app?.canvas;
    if (!canvas) {
      return;
    }
    canvas.addEventListener("pointerdown", this.#handlePointerDown);
    canvas.addEventListener("pointermove", this.#handlePointerMove);
    canvas.addEventListener("pointerup", this.#handlePointerUp);
    canvas.addEventListener("pointercancel", this.#handlePointerUp);
    canvas.addEventListener("wheel", this.#handleWheel, { passive: false });
    canvas.addEventListener("dblclick", this.#handleDoubleClick);
    window.addEventListener("keydown", this.#handleKeyDown);
    window.addEventListener("keyup", this.#handleKeyUp);
  }

  #unbindEvents(): void {
    const canvas = this.#app?.canvas;
    if (canvas) {
      canvas.removeEventListener("pointerdown", this.#handlePointerDown);
      canvas.removeEventListener("pointermove", this.#handlePointerMove);
      canvas.removeEventListener("pointerup", this.#handlePointerUp);
      canvas.removeEventListener("pointercancel", this.#handlePointerUp);
      canvas.removeEventListener("wheel", this.#handleWheel);
      canvas.removeEventListener("dblclick", this.#handleDoubleClick);
    }
    window.removeEventListener("keydown", this.#handleKeyDown);
    window.removeEventListener("keyup", this.#handleKeyUp);
  }

  #screenPoint(event: PointerEvent | MouseEvent | WheelEvent): Point {
    const rect = this.#app?.canvas.getBoundingClientRect();
    return {
      x: event.clientX - (rect?.left ?? 0),
      y: event.clientY - (rect?.top ?? 0),
    };
  }

  #hitTest(screen: Point): SpikeNode | null {
    const world = screenToWorld(screen, this.#camera);
    const nodes = this.#store.list().sort((a, b) => b.zIndex - a.zIndex);
    for (const node of nodes) {
      const bounds = nodeBounds(node);
      if (
        world.x >= bounds.x &&
        world.x <= bounds.x + bounds.width &&
        world.y >= bounds.y &&
        world.y <= bounds.y + bounds.height
      ) {
        return node;
      }
    }
    return null;
  }

  #handlePointerDown = (event: PointerEvent): void => {
    this.#app?.canvas.setPointerCapture(event.pointerId);
    const screen = this.#screenPoint(event);
    this.#activePointers.set(event.pointerId, {
      id: event.pointerId,
      point: screen,
    });

    if (event.pointerType === "touch" && this.#activePointers.size >= 2) {
      const [first, second] = [...this.#activePointers.values()];
      if (first && second) {
        const center = midpoint(first.point, second.point);
        this.#interaction = {
          ...this.#idleInteraction(),
          mode: "pinch",
          pinchStartDistance: distance(first.point, second.point),
          pinchStartCenter: center,
          pinchStartCamera: this.#camera,
        };
      }
      return;
    }

    if (event.button === 1 || this.#spaceDown) {
      this.#interaction = {
        ...this.#idleInteraction(),
        mode: "pan",
        pointerId: event.pointerId,
        startScreen: screen,
        lastScreen: screen,
      };
      return;
    }

    const hit = this.#hitTest(screen);
    if (hit) {
      if (event.shiftKey) {
        if (this.#selected.has(hit.id)) {
          this.#selected.delete(hit.id);
        } else {
          this.#selected.add(hit.id);
        }
      } else if (!this.#selected.has(hit.id)) {
        this.#selected.clear();
        this.#selected.add(hit.id);
      }
      this.#interaction = {
        ...this.#idleInteraction(),
        mode: "drag",
        pointerId: event.pointerId,
        startScreen: screen,
        lastScreen: screen,
        beforeNodes: cloneNodes(this.#store.list()),
      };
      this.#onTextEdit(null);
      this.#emit();
      return;
    }

    if (!event.shiftKey) {
      this.#selected.clear();
    }
    this.#marqueeRect = { x: screen.x, y: screen.y, width: 0, height: 0 };
    this.#interaction = {
      ...this.#idleInteraction(),
      mode: "marquee",
      pointerId: event.pointerId,
      startScreen: screen,
      lastScreen: screen,
      marqueeStart: screen,
    };
    this.#onTextEdit(null);
    this.#emit();
  };

  #handlePointerMove = (event: PointerEvent): void => {
    const screen = this.#screenPoint(event);
    const tracked = this.#activePointers.get(event.pointerId);
    if (tracked) {
      tracked.point = screen;
    }

    if (this.#interaction.mode === "pinch") {
      const [first, second] = [...this.#activePointers.values()];
      if (first && second && this.#interaction.pinchStartDistance > 0) {
        const center = midpoint(first.point, second.point);
        const ratio =
          distance(first.point, second.point) /
          this.#interaction.pinchStartDistance;
        let camera = zoomAtScreenPoint(
          this.#interaction.pinchStartCamera,
          this.#interaction.pinchStartCenter,
          this.#interaction.pinchStartCamera.zoom * ratio,
        );
        camera = {
          ...camera,
          x:
            camera.x -
            (center.x - this.#interaction.pinchStartCenter.x) / camera.zoom,
          y:
            camera.y -
            (center.y - this.#interaction.pinchStartCenter.y) / camera.zoom,
        };
        this.#camera = camera;
        this.#applyCamera();
        this.#emit();
      }
      return;
    }

    if (this.#interaction.pointerId !== event.pointerId) {
      return;
    }

    if (this.#interaction.mode === "pan") {
      const dx = screen.x - this.#interaction.lastScreen.x;
      const dy = screen.y - this.#interaction.lastScreen.y;
      this.#camera = {
        ...this.#camera,
        x: this.#camera.x - dx / this.#camera.zoom,
        y: this.#camera.y - dy / this.#camera.zoom,
      };
      this.#interaction.lastScreen = screen;
      this.#applyCamera();
      this.#emit();
      return;
    }

    if (this.#interaction.mode === "drag") {
      const previousWorld = screenToWorld(
        this.#interaction.lastScreen,
        this.#camera,
      );
      const nextWorld = screenToWorld(screen, this.#camera);
      this.#store.translate(
        [...this.#selected],
        nextWorld.x - previousWorld.x,
        nextWorld.y - previousWorld.y,
      );
      this.#interaction.lastScreen = screen;
      void this.#syncDisplays(false);
      return;
    }

    if (
      this.#interaction.mode === "marquee" &&
      this.#interaction.marqueeStart
    ) {
      const start = this.#interaction.marqueeStart;
      this.#marqueeRect = normalizeRect({
        x: start.x,
        y: start.y,
        width: screen.x - start.x,
        height: screen.y - start.y,
      });
      this.#emit();
    }
  };

  #handlePointerUp = (event: PointerEvent): void => {
    const screen = this.#screenPoint(event);
    this.#activePointers.delete(event.pointerId);
    if (this.#interaction.mode === "pinch") {
      if (this.#activePointers.size < 2) {
        this.#interaction = this.#idleInteraction();
      }
      return;
    }
    if (this.#interaction.pointerId !== event.pointerId) {
      return;
    }

    if (this.#interaction.mode === "drag") {
      this.#commitMutation("drag selection", this.#interaction.beforeNodes);
    } else if (
      this.#interaction.mode === "marquee" &&
      this.#interaction.marqueeStart
    ) {
      const startWorld = screenToWorld(
        this.#interaction.marqueeStart,
        this.#camera,
      );
      const endWorld = screenToWorld(screen, this.#camera);
      const ids = nodesInRect(this.#store.list(), {
        x: startWorld.x,
        y: startWorld.y,
        width: endWorld.x - startWorld.x,
        height: endWorld.y - startWorld.y,
      });
      for (const id of ids) {
        this.#selected.add(id);
      }
      this.#marqueeRect = null;
    }
    this.#interaction = this.#idleInteraction();
    this.#emit();
  };

  #handleWheel = (event: WheelEvent): void => {
    event.preventDefault();
    const point = this.#screenPoint(event);
    const factor = Math.exp(-event.deltaY * 0.0012);
    this.#camera = zoomAtScreenPoint(
      this.#camera,
      point,
      this.#camera.zoom * factor,
    );
    this.#applyCamera();
    this.#emit();
  };

  #handleDoubleClick = (event: MouseEvent): void => {
    const screen = this.#screenPoint(event);
    const hit = this.#hitTest(screen);
    if (!hit || hit.kind !== "text") {
      return;
    }
    this.#selected.clear();
    this.#selected.add(hit.id);
    const bounds = nodeBounds(hit);
    const topLeft = worldToScreen({ x: bounds.x, y: bounds.y }, this.#camera);
    const bottomRight = worldToScreen(
      { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
      this.#camera,
    );
    this.#onTextEdit({
      nodeId: hit.id,
      text: hit.text ?? "",
      rect: {
        x: topLeft.x,
        y: topLeft.y,
        width: bottomRight.x - topLeft.x,
        height: bottomRight.y - topLeft.y,
      },
    });
    this.#emit();
  };

  #handleKeyDown = (event: KeyboardEvent): void => {
    if (event.code === "Space" && !event.repeat) {
      this.#spaceDown = true;
    }
    const modifier = event.ctrlKey || event.metaKey;
    if (!modifier) {
      return;
    }
    const key = event.key.toLowerCase();
    if (key === "c") {
      this.copySelection();
    } else if (key === "v") {
      this.pasteSelection();
    } else if (key === "z" && event.shiftKey) {
      this.redo();
    } else if (key === "z") {
      this.undo();
    } else if (key === "y") {
      this.redo();
    }
  };

  #handleKeyUp = (event: KeyboardEvent): void => {
    if (event.code === "Space") {
      this.#spaceDown = false;
    }
  };

  #applyCamera(): void {
    if (!this.#world || !this.#app) {
      return;
    }
    this.#world.scale.set(this.#camera.zoom);
    this.#world.position.set(
      -this.#camera.x * this.#camera.zoom,
      -this.#camera.y * this.#camera.zoom,
    );
    this.#updateCulling();
  }

  #updateCulling(): void {
    const app = this.#app;
    if (!app) {
      return;
    }
    const rect = app.canvas.getBoundingClientRect();
    const topLeft = screenToWorld({ x: 0, y: 0 }, this.#camera);
    const bottomRight = screenToWorld(
      { x: rect.width, y: rect.height },
      this.#camera,
    );
    const viewport = normalizeRect({
      x: topLeft.x,
      y: topLeft.y,
      width: bottomRight.x - topLeft.x,
      height: bottomRight.y - topLeft.y,
    });
    const visible = new Set(
      cullNodes(this.#store.list(), viewport).map((node) => node.id),
    );
    this.#visibleNodeCount = visible.size;
    for (const [id, display] of this.#displays) {
      display.visible = visible.has(id);
    }
  }

  async #createDisplay(node: SpikeNode): Promise<PixiDisplayObject> {
    const pixi = this.#pixi;
    if (!pixi) {
      throw new Error("PixiJS not initialized");
    }
    if (node.kind === "text") {
      return new pixi.Text({
        text: node.text ?? "",
        style: {
          fill: node.fill ?? 0x111111,
          fontFamily: "Arial, sans-serif",
          fontSize: 34,
          fontWeight: "500",
          lineHeight: 44,
          wordWrap: true,
          wordWrapWidth: node.width,
        },
      });
    }
    if (node.kind === "image") {
      const texture = await pixi.Assets.load(PRODUCT_DATA_URI);
      return new pixi.Sprite(texture);
    }
    const graphics = new pixi.Graphics();
    const color = node.fill ?? (node.kind === "frame" ? 0xf2efe8 : 0x2a2a2a);
    if (node.kind === "frame") {
      graphics.roundRect(0, 0, node.width, node.height, 18).fill(color).stroke({
        color: 0xffffff,
        width: 1,
        alpha: 0.15,
      });
    } else {
      graphics.roundRect(0, 0, node.width, node.height, 6).fill(color);
    }
    return graphics;
  }

  async #syncDisplays(createMissing: boolean): Promise<void> {
    if (!this.#world) {
      return;
    }
    const nodes = this.#store.list();
    const ids = new Set(nodes.map((node) => node.id));
    for (const [id, display] of this.#displays) {
      if (!ids.has(id)) {
        this.#world.removeChild(display);
        display.destroy();
        this.#displays.delete(id);
      }
    }
    for (const node of nodes) {
      let display = this.#displays.get(node.id);
      if (!display && createMissing) {
        display = await this.#createDisplay(node);
        this.#displays.set(node.id, display);
        this.#world.addChild(display);
      } else if (!display) {
        display = await this.#createDisplay(node);
        this.#displays.set(node.id, display);
        this.#world.addChild(display);
      }
      if (node.kind === "text" && "text" in display) {
        (display as PixiText).text = node.text ?? "";
      }
      display.zIndex = node.zIndex;
      display.pivot.set(node.width / 2, node.height / 2);
      display.position.set(node.x + node.width / 2, node.y + node.height / 2);
      display.rotation = node.rotation;
      if (node.kind === "image" || node.kind === "text") {
        display.width = node.width;
        display.height = node.height;
      }
      display.alpha = this.#selected.has(node.id) ? 0.92 : 1;
    }
    this.#world.sortableChildren = true;
    this.#updateCulling();
    this.#emit();
  }

  #commitMutation(label: string, before: readonly SpikeNode[]): void {
    const after = cloneNodes(this.#store.list());
    if (JSON.stringify(before) === JSON.stringify(after)) {
      return;
    }
    this.#store.replaceAll(before);
    this.#history.execute({
      label,
      do: () => {
        this.#store.replaceAll(after);
        void this.#syncDisplays(false);
      },
      undo: () => {
        this.#store.replaceAll(before);
        void this.#syncDisplays(false);
      },
    });
  }

  copySelection(): void {
    this.#clipboard = this.#store
      .list()
      .filter((node) => this.#selected.has(node.id));
  }

  pasteSelection(): void {
    if (this.#clipboard.length === 0) {
      return;
    }
    const before = cloneNodes(this.#store.list());
    const ids: string[] = [];
    for (const source of this.#clipboard) {
      const copy = this.#store.duplicate([source.id])[0];
      if (copy) {
        ids.push(copy.id);
      }
    }
    this.#selected.clear();
    ids.forEach((id) => this.#selected.add(id));
    this.#commitMutation("paste", before);
    void this.#syncDisplays(false);
  }

  undo(): void {
    if (this.#history.undo()) {
      void this.#syncDisplays(false);
    }
  }

  redo(): void {
    if (this.#history.redo()) {
      void this.#syncDisplays(false);
    }
  }

  reorderSelection(direction: -1 | 1): void {
    const id = [...this.#selected][0];
    const node = id ? this.#store.get(id) : null;
    if (!node) {
      return;
    }
    const before = cloneNodes(this.#store.list());
    this.#store.reorder(node.id, node.zIndex + direction);
    this.#commitMutation("reorder layer", before);
    void this.#syncDisplays(false);
  }

  commitText(nodeId: string, text: string): void {
    const node = this.#store.get(nodeId);
    if (!node || node.kind !== "text") {
      return;
    }
    const before = cloneNodes(this.#store.list());
    this.#store.patch(nodeId, { text });
    this.#commitMutation("edit text", before);
    this.#onTextEdit(null);
    void this.#syncDisplays(false);
  }

  beginResize(handle: ResizeHandle, event: PointerEvent): void {
    const selectedNodes = this.#store
      .list()
      .filter((node) => this.#selected.has(node.id));
    const bounds = unionBounds(selectedNodes);
    if (!bounds || selectedNodes.length === 0) {
      return;
    }
    const screen = this.#screenPoint(event);
    this.#interaction = {
      ...this.#idleInteraction(),
      mode: "resize",
      pointerId: event.pointerId,
      startScreen: screen,
      lastScreen: screen,
      beforeNodes: cloneNodes(this.#store.list()),
      resizeHandle: handle,
      transformBounds: bounds,
      transformNodes: cloneNodes(selectedNodes),
    };
    window.addEventListener("pointermove", this.#handleTransformMove);
    window.addEventListener("pointerup", this.#handleTransformUp, {
      once: true,
    });
  }

  beginRotate(event: PointerEvent): void {
    const selectedNodes = this.#store
      .list()
      .filter((node) => this.#selected.has(node.id));
    const bounds = unionBounds(selectedNodes);
    if (!bounds || selectedNodes.length === 0) {
      return;
    }
    const center = {
      x: bounds.x + bounds.width / 2,
      y: bounds.y + bounds.height / 2,
    };
    const screen = this.#screenPoint(event);
    const world = screenToWorld(screen, this.#camera);
    this.#interaction = {
      ...this.#idleInteraction(),
      mode: "rotate",
      pointerId: event.pointerId,
      startScreen: screen,
      lastScreen: screen,
      beforeNodes: cloneNodes(this.#store.list()),
      transformBounds: bounds,
      transformNodes: cloneNodes(selectedNodes),
      rotationStartAngle: Math.atan2(world.y - center.y, world.x - center.x),
    };
    window.addEventListener("pointermove", this.#handleTransformMove);
    window.addEventListener("pointerup", this.#handleTransformUp, {
      once: true,
    });
  }

  #handleTransformMove = (event: PointerEvent): void => {
    if (
      this.#interaction.mode !== "resize" &&
      this.#interaction.mode !== "rotate"
    ) {
      return;
    }
    const bounds = this.#interaction.transformBounds;
    if (!bounds) {
      return;
    }
    const screen = this.#screenPoint(event);
    const world = screenToWorld(screen, this.#camera);
    const center = {
      x: bounds.x + bounds.width / 2,
      y: bounds.y + bounds.height / 2,
    };

    if (this.#interaction.mode === "rotate") {
      const angle = Math.atan2(world.y - center.y, world.x - center.x);
      const delta = angle - this.#interaction.rotationStartAngle;
      for (const original of this.#interaction.transformNodes) {
        const originalCenter = {
          x: original.x + original.width / 2,
          y: original.y + original.height / 2,
        };
        const dx = originalCenter.x - center.x;
        const dy = originalCenter.y - center.y;
        const cosine = Math.cos(delta);
        const sine = Math.sin(delta);
        const rotatedCenter = {
          x: center.x + dx * cosine - dy * sine,
          y: center.y + dx * sine + dy * cosine,
        };
        this.#store.patch(original.id, {
          x: rotatedCenter.x - original.width / 2,
          y: rotatedCenter.y - original.height / 2,
          rotation: original.rotation + delta,
        });
      }
    } else {
      const handle = this.#interaction.resizeHandle;
      if (!handle) {
        return;
      }
      const anchorX = handle.includes("w") ? bounds.x + bounds.width : bounds.x;
      const anchorY = handle.includes("n")
        ? bounds.y + bounds.height
        : bounds.y;
      const targetWidth = Math.max(20, Math.abs(world.x - anchorX));
      const targetHeight = Math.max(20, Math.abs(world.y - anchorY));
      const scaleX = targetWidth / Math.max(1, bounds.width);
      const scaleY = targetHeight / Math.max(1, bounds.height);
      for (const original of this.#interaction.transformNodes) {
        const relativeX = original.x - bounds.x;
        const relativeY = original.y - bounds.y;
        const nextWidth = Math.max(8, original.width * scaleX);
        const nextHeight = Math.max(8, original.height * scaleY);
        const baseX = handle.includes("w") ? anchorX - targetWidth : anchorX;
        const baseY = handle.includes("n") ? anchorY - targetHeight : anchorY;
        this.#store.patch(original.id, {
          x: baseX + relativeX * scaleX,
          y: baseY + relativeY * scaleY,
          width: nextWidth,
          height: nextHeight,
        });
      }
    }
    void this.#syncDisplays(false);
  };

  #handleTransformUp = (): void => {
    window.removeEventListener("pointermove", this.#handleTransformMove);
    const before = this.#interaction.beforeNodes;
    const label =
      this.#interaction.mode === "rotate"
        ? "rotate selection"
        : "resize selection";
    this.#commitMutation(label, before);
    this.#interaction = this.#idleInteraction();
    void this.#syncDisplays(false);
  };

  async runBenchmark(): Promise<CanvasSpikeBenchmarkReport> {
    const app = this.#app;
    const pixi = this.#pixi;
    if (!app || !pixi) {
      throw new Error("canvas spike is not ready");
    }
    return runVirtualizedCanvasBenchmark(pixi, app);
  }
}
