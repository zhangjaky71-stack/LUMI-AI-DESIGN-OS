import { expect, test } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

test.describe("NODE-08 Canvas Technology Spike", () => {
  test.setTimeout(180_000);

  test("loads Pixi, supports precise UI interactions, and emits benchmark evidence", async ({
    page,
  }) => {
    await page.goto("/canvas-spike");
    await page.waitForFunction(
      () => window.__LUMI_CANVAS_SPIKE__?.snapshot().ready === true,
      null,
      {
        timeout: 30_000,
      },
    );

    const canvas = page.locator('canvas[data-canvas-spike="pixi"]');
    await expect(canvas).toBeVisible();
    await expect(page.getByText("READY", { exact: true })).toBeVisible();

    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    if (!box) {
      throw new Error("Canvas bounding box unavailable");
    }

    // Image center in the seeded world scene under the initial camera.
    await page.mouse.click(box.x + 400, box.y + 528);
    await expect(page.getByTestId("selected-reference")).toContainText(
      "asset://product-reference-v1",
    );
    await expect(page.getByTestId("selection-box")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "resize southeast" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "rotate selection" }),
    ).toBeVisible();

    // Text center under the initial camera: double click opens a DOM editor that is safe for IME composition.
    await page.mouse.dblclick(box.x + 368, box.y + 272);
    const editor = page.getByTestId("dom-text-editor");
    await expect(editor).toBeVisible();
    await expect(editor).toHaveAttribute("data-ime-safe", "true");
    await editor.fill("LUMI 中文输入 🧪\nDOM Overlay Text");
    await editor.blur();
    await expect(editor).toBeHidden();

    const report = await page.evaluate(async () => {
      const api = window.__LUMI_CANVAS_SPIKE__;
      if (!api) {
        throw new Error("Canvas Spike benchmark API unavailable");
      }
      return api.runBenchmark();
    });

    expect(report.pixiVersion).toContain("8.19");
    expect(report.metrics).toHaveLength(5);
    expect(
      report.metrics.find((metric) => metric.name === "simple-2k")?.nodeCount,
    ).toBe(2_000);
    expect(
      report.metrics.find((metric) => metric.name === "simple-10k")?.nodeCount,
    ).toBe(10_000);
    expect(
      report.metrics.find((metric) => metric.name === "images-1k")?.nodeCount,
    ).toBe(1_000);
    expect(
      report.metrics.find((metric) => metric.name === "text-1k-rich-100")
        ?.nodeCount,
    ).toBe(1_100);
    expect(
      report.metrics.find((metric) => metric.name === "selected-500-drag")
        ?.nodeCount,
    ).toBe(500);
    for (const metric of report.metrics) {
      expect(metric.p95FrameMs).toBeGreaterThan(0);
      expect(metric.approximateFps).toBeGreaterThan(0);
    }

    const reportDir = resolve(process.cwd(), "reports/canvas-spike");
    await mkdir(reportDir, { recursive: true });
    await writeFile(
      resolve(reportDir, "ci-headless.json"),
      `${JSON.stringify(report, null, 2)}\n`,
      "utf8",
    );

    const markdown = [
      "# NODE-08 CI Headless Canvas Benchmark",
      "",
      `- PixiJS: ${report.pixiVersion}`,
      `- Renderer: ${report.renderer}`,
      `- DPR: ${report.devicePixelRatio}`,
      `- Measured at: ${report.measuredAt}`,
      "",
      "| Scenario | Nodes | P50 ms | P95 ms | Approx FPS |",
      "|---|---:|---:|---:|---:|",
      ...report.metrics.map(
        (metric) =>
          `| ${metric.name} | ${metric.nodeCount} | ${metric.p50FrameMs} | ${metric.p95FrameMs} | ${metric.approximateFps} |`,
      ),
      "",
      "> CI headless Chromium is a reproducible regression signal, not workstation/GPU certification.",
      "",
    ].join("\n");
    await writeFile(resolve(reportDir, "ci-headless.md"), markdown, "utf8");
  });
});
