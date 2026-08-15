import { mkdir, writeFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test.describe("NODE-08 canvas technology spike", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/canvas-spike/index.html");
    await expect(page.getByTestId("canvas-status")).toHaveText("ready", { timeout: 30_000 });
  });

  test("boots Pixi, pans/zooms, and keeps renderer data decoupled", async ({ page }) => {
    const initial = await page.evaluate(() => {
      const spike = (window as typeof window & { __LUMI_CANVAS_SPIKE__: { camera: { x: number; y: number; zoom: number }; nodes: Array<{ id: string; type: string }> } }).__LUMI_CANVAS_SPIKE__;
      return { camera: spike.camera, firstNode: spike.nodes[0], nodeCount: spike.nodes.length };
    });
    expect(initial.nodeCount).toBe(2000);
    expect(initial.firstNode).toMatchObject({ id: "node-1", type: "text" });
    expect(initial.firstNode).not.toHaveProperty("pixiObject");

    const host = page.getByTestId("canvas-host");
    const box = await host.boundingBox();
    if (!box) throw new Error("canvas host has no bounding box");

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -420);
    await page.waitForTimeout(100);

    const zoomed = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { camera: { zoom: number } } }).__LUMI_CANVAS_SPIKE__.camera.zoom);
    expect(zoomed).toBeGreaterThan(initial.camera.zoom);

    const beforePan = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { camera: { x: number; y: number } } }).__LUMI_CANVAS_SPIKE__.camera);
    await page.mouse.move(box.x + 50, box.y + 50);
    await page.mouse.down();
    await page.mouse.move(box.x + 130, box.y + 90, { steps: 5 });
    await page.mouse.up();
    const afterPan = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { camera: { x: number; y: number } } }).__LUMI_CANVAS_SPIKE__.camera);
    expect(Math.abs(afterPan.x - beforePan.x) + Math.abs(afterPan.y - beforePan.y)).toBeGreaterThan(20);
  });

  test("DOM text editing supports CJK/emoji and undo-redo", async ({ page }) => {
    await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { frameNode: (id: string) => void } }).__LUMI_CANVAS_SPIKE__.frameNode("node-1"));
    await page.getByTestId("edit-text").click();
    const editor = page.getByTestId("text-editor");
    await expect(editor).toBeVisible();
    await editor.fill("中文输入测试 🙂\n第二行");
    await editor.press("Control+Enter");
    await expect(editor).toBeHidden();

    const edited = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; text?: string }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1")?.text);
    expect(edited).toBe("中文输入测试 🙂\n第二行");

    await page.getByTestId("undo").click();
    const undone = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; text?: string }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1")?.text);
    expect(undone).not.toBe(edited);

    await page.getByTestId("redo").click();
    const redone = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; text?: string }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1")?.text);
    expect(redone).toBe(edited);
  });

  test("resize, rotate, layer order, and copy/paste are interactive", async ({ page }) => {
    await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { frameNode: (id: string) => void } }).__LUMI_CANVAS_SPIKE__.frameNode("node-1"));
    const before = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; width: number; height: number; rotation: number }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1"));
    if (!before) throw new Error("node-1 missing");

    const handle = page.locator(".handle.se");
    const handleBox = await handle.boundingBox();
    if (!handleBox) throw new Error("resize handle missing");
    await page.mouse.move(handleBox.x + 5, handleBox.y + 5);
    await page.mouse.down();
    await page.mouse.move(handleBox.x + 55, handleBox.y + 35, { steps: 4 });
    await page.mouse.up();

    const resized = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; width: number; height: number }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1"));
    expect(resized?.width).toBeGreaterThan(before.width);
    expect(resized?.height).toBeGreaterThan(before.height);

    const rotate = page.getByTestId("rotate-handle");
    const rotateBox = await rotate.boundingBox();
    if (!rotateBox) throw new Error("rotate handle missing");
    await page.mouse.move(rotateBox.x + 5, rotateBox.y + 5);
    await page.mouse.down();
    await page.mouse.move(rotateBox.x + 90, rotateBox.y + 40, { steps: 4 });
    await page.mouse.up();

    const rotated = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: Array<{ id: string; rotation: number }> } }).__LUMI_CANVAS_SPIKE__.nodes.find((node) => node.id === "node-1")?.rotation ?? 0);
    expect(Math.abs(rotated - before.rotation)).toBeGreaterThan(0.05);

    const countBeforePaste = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: unknown[] } }).__LUMI_CANVAS_SPIKE__.nodes.length);
    await page.getByTestId("copy").click();
    await page.getByTestId("paste").click();
    const countAfterPaste = await page.evaluate(() => (window as typeof window & { __LUMI_CANVAS_SPIKE__: { nodes: unknown[] } }).__LUMI_CANVAS_SPIKE__.nodes.length);
    expect(countAfterPaste).toBe(countBeforePaste + 1);

    await page.getByTestId("bring-forward").click();
    await page.getByTestId("send-backward").click();
  });

  test("runs 2k/10k/image/text/500-selection browser benchmark and releases textures", async ({ page }) => {
    test.setTimeout(150_000);
    const metrics = await page.evaluate(async () => {
      const spike = (window as typeof window & { __LUMI_CANVAS_SPIKE__: { runBenchmark: () => Promise<unknown> } }).__LUMI_CANVAS_SPIKE__;
      return spike.runBenchmark();
    }) as {
      pixi_version: string;
      scenarios: Record<string, { count?: number; samples: number; p95_ms: number }>;
      resource_release: { textures_before_release: number; textures_after_release: number };
    };

    expect(metrics.pixi_version).toBe("8.18.1");
    expect(metrics.scenarios.mixed2k.count).toBe(2000);
    expect(metrics.scenarios.simple10k.count).toBe(10_000);
    expect(metrics.scenarios.images1k.count).toBe(1000);
    expect(metrics.scenarios.text1k.count).toBe(1000);
    expect(metrics.scenarios.selection500.samples).toBeGreaterThanOrEqual(80);
    for (const scenario of Object.values(metrics.scenarios)) {
      expect(Number.isFinite(scenario.p95_ms)).toBe(true);
      expect(scenario.p95_ms).toBeGreaterThan(0);
    }
    expect(metrics.resource_release.textures_before_release).toBeGreaterThan(0);
    expect(metrics.resource_release.textures_after_release).toBe(0);

    await mkdir("reports/nodes/NODE-08/runtime", { recursive: true });
    await writeFile(
      "reports/nodes/NODE-08/runtime/browser-benchmark.json",
      `${JSON.stringify(metrics, null, 2)}\n`,
      "utf8",
    );
  });
});
