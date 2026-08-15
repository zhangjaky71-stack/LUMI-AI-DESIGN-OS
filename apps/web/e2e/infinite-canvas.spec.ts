import { expect, test } from "@playwright/test";

const workspace = "/app/projects/project-summer-launch/workspace";

test.describe("NODE-55 Infinite Canvas UI", () => {
  test("loads multiple frames from the real CanvasController scene", async ({ page }) => {
    await page.goto(workspace);
    const canvas = page.getByLabel("Canvas preview");
    await expect(canvas).toBeVisible();
    await expect(canvas.getByRole("button", { name: /Square \/ 1:1/ })).toBeVisible();
    await expect(canvas.getByRole("button", { name: /Feed \/ 4:5/ })).toBeVisible();
    await expect(canvas.getByRole("button", { name: /Story \/ 9:16/ })).toBeVisible();
    await expect(canvas.getByText("Server v7", { exact: true })).toBeVisible();
  });

  test("creates a frame preset and autosaves one batched Design IR transaction", async ({ page }) => {
    await page.goto(workspace);
    const canvas = page.getByLabel("Canvas preview");
    await canvas.getByRole("button", { name: "+ Frame", exact: true }).click();
    await canvas.getByRole("button", { name: /16:9.*Wide/ }).click();
    await expect(canvas.getByText("Local v8", { exact: true })).toBeVisible();
    await expect(canvas.getByText("Server v8", { exact: true })).toBeVisible({ timeout: 5_000 });
    await expect(canvas.getByText(/^SAVED/)).toBeVisible();
  });

  test("Canvas selection becomes exact AI Edit context", async ({ page }) => {
    await page.goto(workspace);
    const canvas = page.getByLabel("Canvas preview");
    await canvas.getByRole("button", { name: /Headline/ }).click();
    await expect(page.getByText("1 selected", { exact: true })).toBeVisible();
    await expect(page.getByText("Headline", { exact: true }).first()).toBeVisible();
    await canvas.getByRole("button", { name: "AI Edit", exact: true }).click();
    await expect(page.getByLabel("给 LUMI Agent 的指令")).toHaveValue("针对当前选中对象进行 AI Edit：");
  });

  test("drags a READY Asset onto the Canvas and persists the created IMAGE node", async ({ page }) => {
    await page.goto(workspace);
    const canvas = page.getByLabel("Canvas preview");
    const source = canvas.getByText("hero-product.png", { exact: true });
    const viewport = canvas.locator('[data-tool="select"]');
    await source.dragTo(viewport, { targetPosition: { x: 500, y: 360 } });
    await expect(canvas.getByRole("button", { name: /hero-product\.png/ })).toBeVisible();
    await expect(canvas.getByText("Server v8", { exact: true })).toBeVisible({ timeout: 5_000 });
  });

  test("locked nodes expose safe context actions but cannot be deleted", async ({ page }) => {
    await page.goto(workspace);
    const canvas = page.getByLabel("Canvas preview");
    await canvas.getByRole("button", { name: /Hero Product/ }).click({ button: "right" });
    await expect(canvas.getByRole("button", { name: "Delete", exact: true })).toBeDisabled();
    await expect(canvas.getByRole("button", { name: "Unlock", exact: true })).toBeVisible();
  });

  test("version conflict is explicit and supports a real rebase flow", async ({ page }) => {
    await page.goto("/app/projects/project-canvas-conflict/workspace");
    const canvas = page.getByLabel("Canvas preview");
    await canvas.getByRole("button", { name: "+ Frame", exact: true }).click();
    await canvas.getByRole("button", { name: /1:1.*Square/ }).click();
    await expect(canvas.getByText(/Document version conflict/)).toBeVisible({ timeout: 5_000 });
    await canvas.getByRole("button", { name: "Rebase local commands", exact: true }).click();
    await expect(canvas.getByText("Server v9", { exact: true })).toBeVisible({ timeout: 5_000 });
    await expect(canvas.getByText(/^SAVED/)).toBeVisible();
  });

  test("mobile keeps the professional Canvas in the focused Canvas tab", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(workspace);
    await page.getByRole("button", { name: "Canvas", exact: true }).click();
    const canvas = page.getByLabel("Canvas preview");
    await expect(canvas).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Fit all", exact: true })).toBeVisible();
  });
});
