import { expect, test } from "@playwright/test";

test.describe("NODE-40 Canvas Engine production runtime", () => {
  test.setTimeout(120_000);

  test("renders real Pixi, commits Design IR operations, rejects hard constraints, and pans camera", async ({
    page,
  }) => {
    await page.goto("/canvas-engine");
    await page.waitForFunction(
      () => window.__LUMI_CANVAS_ENGINE__?.snapshot().ready === true,
      null,
      { timeout: 30_000 },
    );

    const canvas = page.locator('canvas[data-canvas-engine="pixi"]');
    await expect(canvas).toBeVisible();
    await expect(page.getByTestId("canvas-engine-status")).toHaveText("READY");

    const initial = await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.snapshot());
    expect(initial.shape_x).toBe(80);
    expect(initial.document_version).toBe(1);

    const moved = await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.moveShape(40));
    expect(moved).toBe(true);
    await expect(page.getByTestId("shape-x")).toHaveText("120");
    await expect(page.getByTestId("document-version")).toHaveText("2");
    await expect(page.getByTestId("constraint-decision")).toHaveText("ALLOW");

    const denied = await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.lockAndMove(50));
    expect(denied).toBe(false);
    await expect(page.getByTestId("shape-x")).toHaveText("120");
    await expect(page.getByTestId("document-version")).toHaveText("2");
    await expect(page.getByTestId("constraint-decision")).toHaveText("DENY");

    const beforePan = await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.snapshot().camera_x);
    await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.pan(100));
    const afterPan = await page.evaluate(() => window.__LUMI_CANVAS_ENGINE__!.snapshot().camera_x);
    expect(afterPan).not.toBe(beforePan);
    await expect(page.getByTestId("constraint-decision")).toHaveText("CAMERA");
  });
});
