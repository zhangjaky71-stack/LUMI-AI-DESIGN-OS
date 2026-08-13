import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

interface SyncMetric {
  readonly scenario: string;
  readonly logicalNodes: number;
  readonly visibleNodesMean: number;
  readonly iterations: number;
  readonly p50OperationMs: number;
  readonly p95OperationMs: number;
  readonly meanOperationMs: number;
}

interface SyncReport {
  readonly schemaVersion: 1;
  readonly renderer: string;
  readonly measuredAt: string;
  readonly userAgent: string;
  readonly metrics: readonly SyncMetric[];
  readonly interpretation: string;
}

test.describe("NODE-08 synchronous canvas workload", () => {
  test.setTimeout(120_000);

  test("measures cull + batch rebuild + Pixi render submission without rAF scheduling", async ({
    page,
  }) => {
    await page.goto("/canvas-spike");
    await page.waitForFunction(
      () => window.__LUMI_CANVAS_SPIKE__?.snapshot().ready === true,
      null,
      { timeout: 30_000 },
    );

    const report = await page.evaluate(async (): Promise<SyncReport> => {
      const pixi = window.PIXI;
      if (!pixi) {
        throw new Error("Pixi global unavailable");
      }

      function percentile(values: readonly number[], fraction: number): number {
        const sorted = [...values].sort((a, b) => a - b);
        const index = Math.min(
          sorted.length - 1,
          Math.max(0, Math.ceil(sorted.length * fraction) - 1),
        );
        return sorted[index] ?? 0;
      }

      function summarize(
        scenario: string,
        logicalNodes: number,
        visibleCounts: readonly number[],
        samples: readonly number[],
      ): SyncMetric {
        const mean =
          samples.reduce((total, value) => total + value, 0) /
          Math.max(samples.length, 1);
        const visibleMean =
          visibleCounts.reduce((total, value) => total + value, 0) /
          Math.max(visibleCounts.length, 1);
        return {
          scenario,
          logicalNodes,
          visibleNodesMean: Number(visibleMean.toFixed(1)),
          iterations: samples.length,
          p50OperationMs: Number(percentile(samples, 0.5).toFixed(3)),
          p95OperationMs: Number(percentile(samples, 0.95).toFixed(3)),
          meanOperationMs: Number(mean.toFixed(3)),
        };
      }

      const metrics: SyncMetric[] = [];
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
        document.body.appendChild(app.canvas);

        const graphic = new pixi.Graphics();
        app.stage.addChild(graphic);
        const columns = Math.ceil(Math.sqrt(logicalNodes));
        const positions = Array.from({ length: logicalNodes }, (_, index) => ({
          x: (index % columns) * 38,
          y: Math.floor(index / columns) * 38,
        }));

        // Warm renderer and JIT paths before collecting evidence.
        for (let warmup = 0; warmup < 5; warmup += 1) {
          graphic.clear();
          graphic.rect(0, 0, 28, 28).fill(0x666666);
          app.renderer.render({ container: app.stage });
        }

        const samples: number[] = [];
        const visibleCounts: number[] = [];
        for (let iteration = 0; iteration < 40; iteration += 1) {
          const viewportX = iteration * 22;
          const started = performance.now();
          graphic.clear();
          let visible = 0;
          for (const position of positions) {
            const x = position.x - viewportX;
            if (
              x < -28 ||
              x > 828 ||
              position.y < -28 ||
              position.y > 628
            ) {
              continue;
            }
            graphic.rect(x, position.y, 28, 28);
            visible += 1;
          }
          if (visible > 0) {
            graphic.fill(0x666666);
          }
          app.renderer.render({ container: app.stage });
          samples.push(performance.now() - started);
          visibleCounts.push(visible);
        }

        metrics.push(
          summarize(
            `pixi-batched-sync-${logicalNodes / 1000}k`,
            logicalNodes,
            visibleCounts,
            samples,
          ),
        );
        app.destroy(true, {
          children: true,
          texture: true,
          textureSource: true,
        });
      }

      return {
        schemaVersion: 1,
        renderer: "pixi-webgl-batched",
        measuredAt: new Date().toISOString(),
        userAgent: navigator.userAgent,
        metrics,
        interpretation:
          "Synchronous operation time excludes requestAnimationFrame wait; it measures logical scan/cull, Graphics batch rebuild, and renderer submission on the same headless Chromium environment.",
      };
    });

    expect(report.metrics).toHaveLength(2);
    expect(report.metrics[0]?.logicalNodes).toBe(2_000);
    expect(report.metrics[1]?.logicalNodes).toBe(10_000);
    for (const metric of report.metrics) {
      expect(metric.p95OperationMs).toBeGreaterThan(0);
      expect(metric.visibleNodesMean).toBeGreaterThan(0);
    }

    const reportDir = resolve(process.cwd(), "reports/canvas-spike");
    await mkdir(reportDir, { recursive: true });
    await writeFile(
      resolve(reportDir, "sync-submit.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );
    const markdown = [
      "# NODE-08 Synchronous Pixi Workload",
      "",
      `- Renderer: ${report.renderer}`,
      `- Measured at: ${report.measuredAt}`,
      "",
      "| Scenario | Logical | Visible mean | P50 op ms | P95 op ms | Mean op ms |",
      "|---|---:|---:|---:|---:|---:|",
      ...report.metrics.map(
        (metric) =>
          `| ${metric.scenario} | ${metric.logicalNodes} | ${metric.visibleNodesMean} | ${metric.p50OperationMs} | ${metric.p95OperationMs} | ${metric.meanOperationMs} |`,
      ),
      "",
      report.interpretation,
      "",
    ].join("\n");
    await writeFile(resolve(reportDir, "sync-submit.md"), markdown, "utf8");
  });
});
