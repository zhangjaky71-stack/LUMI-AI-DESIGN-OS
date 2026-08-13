import { createGridNodes, cullNodes, type SpikeNode } from "@lumi/canvas-sdk";

interface PixiPointLike {
  set(x: number, y?: number): void;
}

interface PixiDisplayObject {
  x: number;
  y: number;
  width: number;
  height: number;
  visible: boolean;
  position: PixiPointLike;
  destroy(options?: unknown): void;
}

interface PixiContainer extends PixiDisplayObject {
  addChild<T extends PixiDisplayObject>(child: T): T;
  removeChild<T extends PixiDisplayObject>(child: T): T;
}

interface PixiGraphics extends PixiDisplayObject {
  rect(x: number, y: number, width: number, height: number): this;
  roundRect(x: number, y: number, width: number, height: number, radius: number): this;
  fill(color: number): this;
}

interface PixiText extends PixiDisplayObject {
  text: string;
}

interface PixiApplicationLike {
  readonly canvas: HTMLCanvasElement;
  readonly stage: PixiContainer;
  readonly renderer: { readonly name?: string; readonly type?: number | string };
}

interface PixiNamespaceLike {
  readonly VERSION?: string;
  readonly Container: new () => PixiContainer;
  readonly Graphics: new () => PixiGraphics;
  readonly Text: new (options: Record<string, unknown>) => PixiText;
  readonly HTMLText?: new (options: Record<string, unknown>) => PixiText;
  readonly Sprite: new (texture: unknown) => PixiDisplayObject;
  readonly Assets: { load(source: string): Promise<unknown> };
}

export interface VirtualizedFrameMetric {
  readonly name: string;
  readonly nodeCount: number;
  readonly rendererResidentNodes: number;
  readonly frames: number;
  readonly p50FrameMs: number;
  readonly p95FrameMs: number;
  readonly meanFrameMs: number;
  readonly approximateFps: number;
}

export interface VirtualizedBenchmarkReport {
  readonly schemaVersion: 1;
  readonly pixiVersion: string;
  readonly renderer: string;
  readonly devicePixelRatio: number;
  readonly userAgent: string;
  readonly measuredAt: string;
  readonly metrics: readonly VirtualizedFrameMetric[];
  readonly notes: readonly string[];
}

const PRODUCT_DATA_URI =
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="560" viewBox="0 0 800 560"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#d8b56d"/><stop offset="1" stop-color="#4f3826"/></linearGradient></defs><rect width="800" height="560" rx="48" fill="#ece8df"/><ellipse cx="400" cy="450" rx="250" ry="40" fill="#000" opacity=".12"/><rect x="250" y="100" width="300" height="320" rx="80" fill="url(#g)"/><circle cx="400" cy="210" r="70" fill="#f7f1e4" opacity=".7"/><path d="M330 330h140" stroke="#f7f1e4" stroke-width="24" stroke-linecap="round"/></svg>`,
  );

function percentile(values: readonly number[], fraction: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.ceil(sorted.length * fraction) - 1),
  );
  return sorted[index] ?? 0;
}

function average(values: readonly number[]): number {
  return values.length === 0
    ? 0
    : values.reduce((total, value) => total + value, 0) / values.length;
}

async function frameSamples(
  frameCount: number,
  onFrame?: (index: number) => void,
): Promise<number[]> {
  const samples: number[] = [];
  let previous = performance.now();
  for (let index = 0; index < frameCount; index += 1) {
    await new Promise<void>((resolve) => {
      requestAnimationFrame((now) => {
        onFrame?.(index);
        samples.push(now - previous);
        previous = now;
        resolve();
      });
    });
  }
  samples.shift();
  return samples;
}

function metric(
  name: string,
  nodeCount: number,
  rendererResidentNodes: number,
  samples: readonly number[],
): VirtualizedFrameMetric {
  const p50 = percentile(samples, 0.5);
  const p95 = percentile(samples, 0.95);
  const mean = average(samples);
  return {
    name,
    nodeCount,
    rendererResidentNodes,
    frames: samples.length,
    p50FrameMs: Number(p50.toFixed(3)),
    p95FrameMs: Number(p95.toFixed(3)),
    meanFrameMs: Number(mean.toFixed(3)),
    approximateFps: Number((1000 / Math.max(mean, 0.001)).toFixed(1)),
  };
}

function rendererName(renderer: PixiApplicationLike["renderer"]): string {
  if (renderer.name) {
    return renderer.name;
  }
  if (typeof renderer.type === "string") {
    return renderer.type;
  }
  return "webgl-preferred";
}

function viewportSize(app: PixiApplicationLike): { width: number; height: number } {
  const rect = app.canvas.getBoundingClientRect();
  return {
    width: Math.max(480, Math.min(1280, rect.width || 960)),
    height: Math.max(420, Math.min(900, rect.height || 720)),
  };
}

function poolSizeFor(
  nodes: readonly SpikeNode[],
  width: number,
  height: number,
  sampleSteps = 12,
): number {
  let maximum = 0;
  for (let index = 0; index < sampleSteps; index += 1) {
    const visible = cullNodes(nodes, {
      x: index * 36,
      y: index * 14,
      width: width + 180,
      height: height + 180,
    }).length;
    maximum = Math.max(maximum, visible);
  }
  return Math.max(32, maximum + 24);
}

function updatePool(
  pool: readonly PixiDisplayObject[],
  visibleNodes: readonly SpikeNode[],
  viewportX: number,
  viewportY: number,
): void {
  for (let index = 0; index < pool.length; index += 1) {
    const display = pool[index];
    const node = visibleNodes[index];
    if (!display) {
      continue;
    }
    if (!node) {
      display.visible = false;
      continue;
    }
    display.visible = true;
    display.position.set(node.x - viewportX, node.y - viewportY);
  }
}

async function measureVirtualizedShapes(
  pixi: PixiNamespaceLike,
  app: PixiApplicationLike,
  name: string,
  count: number,
  frames: number,
): Promise<VirtualizedFrameMetric> {
  const { width, height } = viewportSize(app);
  const nodes = createGridNodes(count, 62);
  const poolSize = poolSizeFor(nodes, width, height);
  const root = new pixi.Container();
  const pool: PixiGraphics[] = [];
  for (let index = 0; index < poolSize; index += 1) {
    const display = new pixi.Graphics()
      .roundRect(0, 0, 48, 48, 4)
      .fill(0x666666);
    root.addChild(display);
    pool.push(display);
  }
  app.stage.addChild(root);

  const samples = await frameSamples(frames, (index) => {
    const viewportX = index * 28;
    const viewportY = index * 10;
    const visible = cullNodes(nodes, {
      x: viewportX - 90,
      y: viewportY - 90,
      width: width + 180,
      height: height + 180,
    });
    updatePool(pool, visible, viewportX, viewportY);
  });

  app.stage.removeChild(root);
  root.destroy({ children: true });
  return metric(name, count, poolSize, samples);
}

async function measureVirtualizedImages(
  pixi: PixiNamespaceLike,
  app: PixiApplicationLike,
  count: number,
  frames: number,
): Promise<VirtualizedFrameMetric> {
  const { width, height } = viewportSize(app);
  const columns = 40;
  const nodes: SpikeNode[] = Array.from({ length: count }, (_, index) => ({
    id: `image-${index}`,
    kind: "image",
    x: (index % columns) * 88,
    y: Math.floor(index / columns) * 64,
    width: 80,
    height: 56,
    rotation: 0,
    zIndex: index,
  }));
  const poolSize = poolSizeFor(nodes, width, height);
  const texture = await pixi.Assets.load(PRODUCT_DATA_URI);
  const root = new pixi.Container();
  const pool: PixiDisplayObject[] = [];
  for (let index = 0; index < poolSize; index += 1) {
    const sprite = new pixi.Sprite(texture);
    sprite.width = 80;
    sprite.height = 56;
    root.addChild(sprite);
    pool.push(sprite);
  }
  app.stage.addChild(root);

  const samples = await frameSamples(frames, (index) => {
    const viewportX = index * 18;
    const viewportY = index * 7;
    const visible = cullNodes(nodes, {
      x: viewportX - 90,
      y: viewportY - 90,
      width: width + 180,
      height: height + 180,
    });
    updatePool(pool, visible, viewportX, viewportY);
  });

  app.stage.removeChild(root);
  root.destroy({ children: true });
  return metric("images-1k", count, poolSize, samples);
}

async function measureVirtualizedText(
  pixi: PixiNamespaceLike,
  app: PixiApplicationLike,
  textCount: number,
  richTextCount: number,
  frames: number,
): Promise<VirtualizedFrameMetric> {
  const { width, height } = viewportSize(app);
  const regularNodes: SpikeNode[] = Array.from({ length: textCount }, (_, index) => ({
    id: `text-${index}`,
    kind: "text",
    x: (index % 30) * 120,
    y: Math.floor(index / 30) * 30,
    width: 110,
    height: 24,
    rotation: 0,
    zIndex: index,
    text: `LUMI ${index} 中文 🧪`,
  }));
  const regularPoolSize = poolSizeFor(regularNodes, width, height);
  const root = new pixi.Container();
  const regularPool: PixiText[] = [];
  for (let index = 0; index < regularPoolSize; index += 1) {
    const text = new pixi.Text({
      text: `LUMI 中文 🧪`,
      style: { fill: 0xffffff, fontSize: 14, fontFamily: "Arial, sans-serif" },
    });
    root.addChild(text);
    regularPool.push(text);
  }

  const richPool: PixiText[] = [];
  if (pixi.HTMLText) {
    for (let index = 0; index < richTextCount; index += 1) {
      const rich = new pixi.HTMLText({
        text: `<b>LUMI</b> <i>${index}</i> 中文`,
        style: { fill: 0xffffff, fontSize: 14 },
      });
      rich.position.set((index % 20) * 64, 300 + Math.floor(index / 20) * 34);
      root.addChild(rich);
      richPool.push(rich);
    }
  }
  app.stage.addChild(root);

  const samples = await frameSamples(frames, (index) => {
    const viewportX = index * 12;
    const viewportY = index * 4;
    const visible = cullNodes(regularNodes, {
      x: viewportX - 90,
      y: viewportY - 90,
      width: width + 180,
      height: height + 180,
    });
    for (let poolIndex = 0; poolIndex < regularPool.length; poolIndex += 1) {
      const display = regularPool[poolIndex];
      const node = visible[poolIndex];
      if (!display) {
        continue;
      }
      if (!node) {
        display.visible = false;
        continue;
      }
      display.visible = true;
      display.position.set(node.x - viewportX, node.y - viewportY);
    }
    root.x = Math.sin(index / 5) * 2;
  });

  app.stage.removeChild(root);
  root.destroy({ children: true });
  return metric(
    "text-1k-rich-100",
    textCount + richTextCount,
    regularPoolSize + richPool.length,
    samples,
  );
}

async function measureSelectedDrag(
  pixi: PixiNamespaceLike,
  app: PixiApplicationLike,
  count: number,
  frames: number,
): Promise<VirtualizedFrameMetric> {
  const root = new pixi.Container();
  const displays: PixiGraphics[] = [];
  for (let index = 0; index < count; index += 1) {
    const display = new pixi.Graphics().rect(0, 0, 20, 20).fill(0x40c4ff);
    display.position.set((index % 25) * 28, Math.floor(index / 25) * 28);
    root.addChild(display);
    displays.push(display);
  }
  app.stage.addChild(root);
  const samples = await frameSamples(frames, () => {
    for (const display of displays) {
      display.x += 1;
      display.y += 0.25;
    }
  });
  app.stage.removeChild(root);
  root.destroy({ children: true });
  return metric("selected-500-drag", count, count, samples);
}

export async function runVirtualizedCanvasBenchmark(
  pixiValue: unknown,
  appValue: unknown,
): Promise<VirtualizedBenchmarkReport> {
  const pixi = pixiValue as PixiNamespaceLike;
  const app = appValue as PixiApplicationLike;
  const metrics: VirtualizedFrameMetric[] = [];
  metrics.push(await measureVirtualizedShapes(pixi, app, "simple-2k", 2_000, 45));
  metrics.push(await measureVirtualizedShapes(pixi, app, "simple-10k", 10_000, 30));
  metrics.push(await measureVirtualizedImages(pixi, app, 1_000, 20));
  metrics.push(await measureVirtualizedText(pixi, app, 1_000, 100, 16));
  metrics.push(await measureSelectedDrag(pixi, app, 500, 35));

  return {
    schemaVersion: 1,
    pixiVersion: pixi.VERSION ?? "8.19.0",
    renderer: rendererName(app.renderer),
    devicePixelRatio: window.devicePixelRatio || 1,
    userAgent: navigator.userAgent,
    measuredAt: new Date().toISOString(),
    metrics,
    notes: [
      "Logical scene counts remain 2k/10k/1k/1.1k while Pixi display objects are viewport-virtualized.",
      "rendererResidentNodes records the renderer pool size; selected-500-drag intentionally keeps all 500 displays resident.",
      "CI headless Chromium is a reproducible regression signal, not workstation/GPU certification.",
    ],
  };
}
