import { expect, test, type Page } from "@playwright/test";

const workspace = "/app/projects/project-summer-launch/workspace";

function inspector(page: Page) {
  return page.getByLabel("Layers 与 Inspector");
}

function agent(page: Page) {
  return page.getByLabel("Agent 对话与运行");
}

function layerRow(page: Page, id: string) {
  return inspector(page).locator(`[data-layer-id='${id}']`);
}

function selectLayer(page: Page, id: string, shift = false) {
  return layerRow(page, id).locator("button").nth(1).click(shift ? { modifiers: ["Shift"] } : undefined);
}

test.describe("NODE-56 Layers / Inspector UI", () => {
  test("Layers selection is the same selection used by Canvas and Agent context", async ({ page }) => {
    await page.goto(workspace);
    await selectLayer(page, "node-headline");
    await expect(agent(page).getByText("1 selected", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Canvas preview").getByRole("button", { name: "Headline", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(layerRow(page, "node-headline")).toHaveAttribute("data-layer-selected", "true");
  });

  test("visibility and lock edits persist through the NODE-55 autosave channel", async ({ page }) => {
    await page.goto(workspace);
    const panel = inspector(page);
    await panel.getByRole("button", { name: "Headline 隐藏", exact: true }).click();
    await expect(page.getByLabel("Canvas preview").getByRole("button", { name: "Headline", exact: true })).toHaveCount(0);
    await expect(page.getByLabel("Canvas preview").getByText("Server v8", { exact: true })).toBeVisible({ timeout: 5_000 });
    await panel.getByRole("button", { name: "Headline 显示", exact: true }).click();
    await expect(page.getByLabel("Canvas preview").getByRole("button", { name: "Headline", exact: true })).toBeVisible();
    await panel.getByRole("button", { name: "Headline 锁定", exact: true }).click();
    await expect(panel.getByRole("button", { name: "Headline 解锁", exact: true })).toBeVisible();
  });

  test("Design inspector edits transform and typography as semantic DesignOperations", async ({ page }) => {
    await page.goto(workspace);
    const panel = inspector(page);
    await selectLayer(page, "node-headline");
    await panel.getByRole("button", { name: "design", exact: true }).click();
    const x = panel.getByLabel("X");
    await x.fill("140");
    await x.blur();
    const content = panel.getByLabel("Content");
    await content.fill("LUMI SUMMER");
    await content.blur();
    const font = panel.getByLabel("Font");
    await font.fill("64");
    await font.blur();
    await expect(page.getByLabel("Canvas preview").getByText("LUMI SUMMER", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Canvas preview").getByText(/Server v\d+/)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByLabel("Canvas preview").getByText(/^SAVED/)).toBeVisible({ timeout: 5_000 });
  });

  test("Group and Ungroup preserve editable hierarchy instead of creating UI-only grouping", async ({ page }) => {
    await page.goto(workspace);
    const panel = inspector(page);
    await selectLayer(page, "node-headline");
    await selectLayer(page, "node-offer", true);
    await expect(agent(page).getByText("2 selected", { exact: true })).toBeVisible();
    await panel.getByRole("button", { name: "Group", exact: true }).click();
    const groupRow = panel.locator("[data-layer-id^='group-']");
    await expect(groupRow).toHaveCount(1);
    await expect(groupRow).toHaveAttribute("data-layer-selected", "true");
    await expect(agent(page).getByText("1 selected", { exact: true })).toBeVisible();
    await panel.getByRole("button", { name: "Ungroup", exact: true }).click();
    await expect(agent(page).getByText("2 selected", { exact: true })).toBeVisible();
    await expect(layerRow(page, "node-headline")).toBeVisible();
    await expect(layerRow(page, "node-offer")).toBeVisible();
  });

  test("inline layer rename and z-order controls update the same document", async ({ page }) => {
    await page.goto(workspace);
    const panel = inspector(page);
    await layerRow(page, "node-headline").getByText("Headline", { exact: true }).dblclick();
    const rename = panel.getByLabel("Headline 重命名");
    await rename.fill("Campaign Title");
    await rename.press("Enter");
    await expect(layerRow(page, "node-headline").getByText("Campaign Title", { exact: true })).toBeVisible();
    await selectLayer(page, "node-headline");
    await panel.getByRole("button", { name: "design", exact: true }).click();
    await panel.getByRole("button", { name: "Bring forward", exact: true }).click();
    await expect(page.getByLabel("Canvas preview").getByText(/Server v\d+/)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByLabel("Canvas preview").getByText(/^SAVED/)).toBeVisible({ timeout: 5_000 });
  });

  test("Context tab preserves Brand / reference selection and safe-context disclosure", async ({ page }) => {
    await page.goto(workspace);
    const panel = inspector(page);
    await panel.getByRole("button", { name: "context", exact: true }).click();
    await expect(panel.getByText(/LUMI Coffee/)).toBeVisible();
    await expect(panel.getByText("hero-product.png", { exact: true })).toBeVisible();
    await expect(panel.getByText(/never exposes system prompts or private chain-of-thought/i)).toBeVisible();
  });

  test("mobile Inspector tab remains usable without compressing the desktop tree", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(workspace);
    await page.getByRole("button", { name: "Inspector", exact: true }).click();
    const panel = inspector(page);
    await expect(panel).toBeVisible();
    await expect(layerRow(page, "node-headline")).toBeVisible();
    await panel.getByRole("button", { name: "design", exact: true }).click();
    await expect(panel.getByText(/选择 Canvas 对象/)).toBeVisible();
  });
});
