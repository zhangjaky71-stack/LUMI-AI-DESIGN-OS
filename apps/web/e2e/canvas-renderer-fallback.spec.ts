import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const KONVA_CDN = "https://cdn.jsdelivr.net/npm/konva@10.3.0/konva.min.js";
const FABRIC_ESM = "https://cdn.jsdelivr.net/npm/fabric@7.4.0/+esm";

interface RendererMetric {
  readonly renderer: string;
  readonly scenario: string;
  readonly logicalNodes: number;
  readonly rendererResidentNodes: number;
  readonly p50FrameMs: number;
  readonly p95FrameMs: number;
  readonly meanFrameMs: number;
  readonly approximateFps: number;
}

interface RendererFallbackReport {
  readonly schemaVersion: 1;
  readonly measuredAt: string;
  readonly userAgent: string;
  readonly metrics: readonly RendererMetric[];
}

function markdown(report: RendererFallbackReport): string {
  return [
    "# NODE-08 Renderer Fallback Stress",
    "",
    `- Measured at: ${report.measuredAt}`,
    `- User agent: ${report.userAgent}`,
    "",
    "| Renderer | Scenario | Logical | Resident | P50 ms | P95 ms | Approx FPS |",
    "|---|---|---:|---:|---:|---:|---:|",
    ...report.metrics.map(
      (metric) =>
        `| ${metric.renderer} | ${metric.scenario} | ${metric.logicalNodes} | ${metric.rendererResidentNodes} | ${metric.p50FrameMs} | ${metric.p95FrameMs} | ${metric.approximateFps} |`,
    ),
    "",
    "> Same headless Chromium environment. This is a comparative regression signal, not workstation GPU certification.",
    "",
  ].join("\n");
}

test.describe("NODE-08 renderer fallback stress", () => {
  test.setTimeout(240_000);

  test("compares Pixi batched rendering with Konva and Fabric in the same browser", async ({
    page,
  }) => {
    await page.goto("/canvas-spike");
    await page.waitForFunction(
      () => window.__LUMI_CANVAS_SPIKE__?.snapshot().ready === true,
      null,
      { timeout: 30_000 },
    );

    const pixiMetrics = await page.evaluate(async () => {
      function percentile(values: readonly number[], fraction: number): number {
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.min(
          sorted.length - 1,
          Math.max(0, Math.ceil(sorted.length * fraction) - 1),
        );
        return sorted[index] ?? 0;
      }

      function summarize(
        renderer: string,
        scenario: string,
        logicalNodes: number,
        rendererResidentNodes: number,
        samples: readonly number[],
      ) {
        const mean =
          samples.reduce((total, value) => total + value, 0) /
          Math.max(samples.length, 1);
        return {
          renderer,
          scenario,
          logicalNodes,
          rendererResidentNodes,
          p50FrameMs: Number(percentile(samples, 0.5).toFixed(3)),
          p95FrameMs: Number(percentile(samples, 0.95).toFixed(3)),
          meanFrameMs: Number(mean.toFixed(3)),
          approximateFps: Number((1000 / Math.max(mean, 0.001)).toFixed(1)),
        };
      }

      async function sampleFrames(
        count: number,
        render?: (index: number) => void,
      ): Promise<number[]> {
        const values: number[] = [];
        let previous = performance.now();
        for (let index = 0; index < count; index += 1) {
          await new Promise<void>((resolveFrame) => {
            requestAnimationFrame((now) => {
              render?.(index);
              values.push(now - previous);
              previous = now;
              resolveFrame();
            });
          });
        }
        values.shift();
        return values;
      }

      const metrics = [];
      metrics.push(
        summarize("browser", "empty-rAF", 0, 0, await sampleFrames(30)),
      );

      const pixi = window.PIXI;
      if (!pixi) {
        throw new Error("Pixi global unavailable");
      }

      for (const logicalNodes of [2_000, 10_000]) {
        const app = new pixi.Application();
        await app.init({
          width: 800,
          height: 600,
          background: 0x111111,
          antialias: false,
          preference: "webgl",
        });
        app.canvas.style.position = "fixed";
        app.canvas.style.left = "-10000px";
        app.canvas.style.top = "0";
        document.body.appendChild(app.canvas);
        const graphic = new pixi.Graphics();
        app.stage.addChild(graphic);

        const columns = Math.ceil(Math.sqrt(logicalNodes));
        const positions = Array.from({ length: logicalNodes }, (_, index) => ({
          x: (index % columns) * 38,
          y: Math.floor(index / columns) * 38,
        }));
        const samples = await sampleFrames(24, (frame) => {
          const viewportX = frame * 22;
          graphic.clear();
          let resident = 0;
          for (const position of positions) {
            const x = position.x - viewportX;
            if (x < -24 || x > 824 || position.y < -24 || position.y > 624) {
              continue;
            }
            graphic.rect(x, position.y, 28, 28);
            resident += 1;
          }
          if (resident > 0) {
            graphic.fill(0x666666);
          }
        });
        const residentEstimate = Math.min(
          logicalNodes,
          Math.ceil(848 / 38) * Math.ceil(648 / 38),
        );
        metrics.push(
          summarize(
            "pixi-webgl-batched",
            `simple-${logicalNodes / 1000}k`,
            logicalNodes,
            residentEstimate,
            samples,
          ),
        );
        app.destroy(true, {
          children: true,
          texture: true,
          textureSource: true,
        });
      }
      return metrics;
    });

    await page.addScriptTag({ url: KONVA_CDN });
    await page.waitForFunction(() => "Konva" in window);
    const konvaMetrics = await page.evaluate(async () => {
      interface KonvaNode {
        destroy(): void;
      }
      interface KonvaStage extends KonvaNode {
        add(layer: KonvaLayer): void;
        position(point: { x: number; y: number }): void;
      }
      interface KonvaLayer extends KonvaNode {
        add(node: KonvaNode): void;
        draw(): void;
      }
      interface KonvaGlobal {
        Stage: new (options: Record<string, unknown>) => KonvaStage;
        Layer: new (options?: Record<string, unknown>) => KonvaLayer;
        Rect: new (options: Record<string, unknown>) => KonvaNode;
      }
      const konva = (window as unknown as { Konva: KonvaGlobal }).Konva;

      function percentile(values: readonly number[], fraction: number): number {
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.min(
          sorted.length - 1,
          Math.max(0, Math.ceil(sorted.length * fraction) - 1),
        );
        return sorted[index] ?? 0;
      }
      async function sampleFrames(
        count: number,
        render: (index: number) => void,
      ): Promise<number[]> {
        const values: number[] = [];
        let previous = performance.now();
        for (let index = 0; index < count; index += 1) {
          await new Promise<void>((resolveFrame) => {
            requestAnimationFrame((now) => {
              render(index);
              values.push(now - previous);
              previous = now;
              resolveFrame();
            });
          });
        }
        values.shift();
        return values;
      }
      const output = [];
      for (const logicalNodes of [2_000, 10_000]) {
        const host = document.createElement("div");
        host.style.position = "fixed";
        host.style.left = "-10000px";
        host.style.width = "800px";
        host.style.height = "600px";
        document.body.appendChild(host);
        const stage = new konva.Stage({ container: host, width: 800, height: 600 });
        const layer = new konva.Layer({ listening: false });
        stage.add(layer);
        const columns = Math.ceil(Math.sqrt(logicalNodes));
        for (let index = 0; index < logicalNodes; index += 1) {
          layer.add(
            new konva.Rect({
              x: (index % columns) * 38,
              y: Math.floor(index / columns) * 38,
              width: 28,
              height: 28,
              fill: "#666",
              listening: false,
              perfectDrawEnabled: false,
            }),
          );
        }
        layer.draw();
        const samples = await sampleFrames(18, (frame) => {
          stage.position({ x: -frame * 22, y: 0 });
          layer.draw();
        });
        const mean =
          samples.reduce((total, value) => total + value, 0) /
          Math.max(samples.length, 1);
        output.push({
          renderer: "konva-canvas2d",
          scenario: `simple-${logicalNodes / 1000}k`,
          logicalNodes,
          rendererResidentNodes: logicalNodes,
          p50FrameMs: Number(percentile(samples, 0.5).toFixed(3)),
          p95FrameMs: Number(percentile(samples, 0.95).toFixed(3)),
          meanFrameMs: Number(mean.toFixed(3)),
          approximateFps: Number((1000 / Math.max(mean, 0.001)).toFixed(1)),
        });
        stage.destroy();
        host.remove();
      }
      return output;
    });

    await page.addScriptTag({
      type: "module",
      content: `import * as fabric from '${FABRIC_ESM}'; window.__LUMI_FABRIC__ = fabric;`,
    });
    await page.waitForFunction(() => "__LUMI_FABRIC__" in window, null, {
      timeout: 30_000,
    });
    const fabricMetrics = await page.evaluate(async () => {
      interface FabricObject {}
      interface FabricCanvas {
        add(...objects: FabricObject[]): number;
        renderAll(): void;
        setViewportTransform(transform: number[]): void;
        dispose(): void;
      }
      interface FabricGlobal {
        Canvas: new (
          element: HTMLCanvasElement,
          options: Record<string, unknown>,
        ) => FabricCanvas;
        Rect: new (options: Record<string, unknown>) => FabricObject;
      }
      const fabric = (
        window as unknown as { __LUMI_FABRIC__: FabricGlobal }
      ).__LUMI_FABRIC__;

      function percentile(values: readonly number[], fraction: number): number {
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.min(
          sorted.length - 1,
          Math.max(0, Math.ceil(sorted.length * fraction) - 1),
        );
        return sorted[index] ?? 0;
      }
      async function sampleFrames(
        count: number,
        render: (index: number) => void,
      ): Promise<number[]> {
        const values: number[] = [];
        let previous = performance.now();
        for (let index = 0; index < count; index += 1) {
          await new Promise<void>((resolveFrame) => {
            requestAnimationFrame((now) => {
              render(index);
              values.push(now - previous);
              previous = now;
              resolveFrame();
            });
          });
        }
        values.shift();
        return values;
      }

      const output = [];
      for (const logicalNodes of [2_000, 10_000]) {
        const element = document.createElement("canvas");
        element.width = 800;
        element.height = 600;
        element.style.position = "fixed";
        element.style.left = "-10000px";
        document.body.appendChild(element);
        const canvas = new fabric.Canvas(element, {
          width: 800,
          height: 600,
          selection: false,
          renderOnAddRemove: false,
          skipOffscreen: true,
        });
        const columns = Math.ceil(Math.sqrt(logicalNodes));
        for (let index = 0; index < logicalNodes; index += 1) {
          canvas.add(
            new fabric.Rect({
              left: (index % columns) * 38,
              top: Math.floor(index / columns) * 38,
              width: 28,
              height: 28,
              fill: "#666",
              selectable: false,
              evented: false,
              objectCaching: false,
            }),
          );
        }
        canvas.renderAll();
        const samples = await sampleFrames(18, (frame) => {
          canvas.setViewportTransform([1, 0, 0, 1, -frame * 22, 0]);
          canvas.renderAll();
        });
        const mean =
          samples.reduce((total, value) => total + value, 0) /
          Math.max(samples.length, 1);
        output.push({
          renderer: "fabric-canvas2d",
          scenario: `simple-${logicalNodes / 1000}k`,
          logicalNodes,
          rendererResidentNodes: logicalNodes,
          p50FrameMs: Number(percentile(samples, 0.5).toFixed(3)),
          p95FrameMs: Number(percentile(samples, 0.95).toFixed(3)),
          meanFrameMs: Number(mean.toFixed(3)),
          approximateFps: Number((1000 / Math.max(mean, 0.001)).toFixed(1)),
        });
        canvas.dispose();
        element.remove();
      }
      return output;
    });

    const report: RendererFallbackReport = {
      schemaVersion: 1,
      measuredAt: new Date().toISOString(),
      userAgent: await page.evaluate(() => navigator.userAgent),
      metrics: [...pixiMetrics, ...konvaMetrics, ...fabricMetrics],
    };

    expect(report.metrics.find((metric) => metric.scenario === "empty-rAF")).toBeDefined();
    expect(
      report.metrics.find(
        (metric) =>
          metric.renderer === "pixi-webgl-batched" &&
          metric.scenario === "simple-10k",
      )?.logicalNodes,
    ).toBe(10_000);
    expect(
      report.metrics.find(
        (metric) =>
          metric.renderer === "konva-canvas2d" &&
          metric.scenario === "simple-10k",
      )?.logicalNodes,
    ).toBe(10_000);
    expect(
      report.metrics.find(
        (metric) =>
          metric.renderer === "fabric-canvas2d" &&
          metric.scenario === "simple-10k",
      )?.logicalNodes,
    ).toBe(10_000);

    const reportDir = resolve(process.cwd(), "reports/canvas-spike");
    await mkdir(reportDir, { recursive: true });
    await writeFile(
      resolve(reportDir, "renderer-fallback.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
    await writeFile(
      resolve(reportDir, "renderer-fallback.md"),
      markdown(report),
      "utf8",
    );
  });
});
