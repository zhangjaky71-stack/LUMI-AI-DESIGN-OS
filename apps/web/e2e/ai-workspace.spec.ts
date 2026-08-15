import { expect, test, type Page } from "@playwright/test";

const workspace = "/app/projects/project-summer-launch/workspace";

async function startRun(page: Page) {
  await page.getByRole("button", { name: /Hero Product/ }).click();
  await page.getByRole("button", { name: /Headline/ }).click();
  await page
    .getByLabel("给 LUMI Agent 的指令")
    .fill("只改选中的标题与构图，产品身份保持不变，先给我一个可评审方向");
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

test.describe("NODE-54 AI Design Workspace", () => {
  test("chat and Canvas share one project workspace with explicit selection context", async ({ page }) => {
    await page.goto(workspace);
    await expect(page.getByRole("heading", { name: "夏季新品发布" })).toBeVisible();
    await expect(page.getByLabel("Canvas preview")).toBeVisible();
    await page.getByRole("button", { name: /Hero Product/ }).click();
    await page.getByRole("button", { name: /Headline/ }).click();
    await expect(page.getByText("2 selected", { exact: true })).toBeVisible();
    await expect(page.getByText(/Document v7/).first()).toBeVisible();
    await expect(page.getByText(/Hero Product · locked identity/)).toBeVisible();
  });

  test("streamed run deduplicates events and ends on an actionable approval", async ({ page }) => {
    await page.goto(workspace);
    await startRun(page);
    await expect(page.getByText("正在分析 Brief、Brand Kit 与选中对象。")).toBeVisible();
    await expect(page.getByText("已锁定产品身份约束，正在生成视觉方向。")).toHaveCount(1);
    await expect(page.getByRole("heading", { name: "夏季新品主视觉方向 A" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "确认主视觉方向" })).toBeVisible();
    await expect(page.getByText("已暂停", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("APPROVED", { exact: true })).toBeVisible();
  });

  test("stale approval is visible but cannot submit an old decision", async ({ page }) => {
    await page.goto(workspace);
    const stale = page.getByRole("heading", { name: "旧方向确认" }).locator("xpath=ancestor::article");
    await expect(stale.getByText("已过期", { exact: true })).toBeVisible();
    await expect(stale.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    await expect(stale.getByText(/旧审批不会被提交/)).toBeVisible();
  });

  test("pause, resume and stop use versioned run controls", async ({ page }) => {
    await page.goto(workspace);
    await startRun(page);
    await page.getByRole("button", { name: "暂停", exact: true }).click();
    await expect(page.getByText("已暂停", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Resume", exact: true }).click();
    await expect(page.getByText("运行中", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Stop", exact: true }).first().click();
    await expect(page.getByText("已停止", { exact: true })).toBeVisible();
  });

  test("artifact placement binds exact artifact and document versions", async ({ page }) => {
    await page.goto(workspace);
    await startRun(page);
    await expect(page.getByRole("heading", { name: "夏季新品主视觉方向 A" })).toBeVisible();
    await page.getByRole("button", { name: "放到 Canvas", exact: true }).click();
    await expect(page.getByText("Document v8").first()).toBeVisible();
    await expect(page.getByText(/已将 夏季新品主视觉方向 A v1 放到 Canvas/)).toBeVisible();
  });

  test("provider fallback warning is explicit without exposing internal reasoning", async ({ page }) => {
    await page.goto(workspace);
    await expect(page.getByText(/主图像 Provider 当前处于降级状态/)).toBeVisible();
    await expect(page.getByText(/不会暴露 system prompt 或内部 chain-of-thought/)).toBeVisible();
    await expect(page.getByText(/reasoning trace/i)).toHaveCount(0);
  });

  test("mobile uses focused panels instead of squeezing the desktop three-column layout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(workspace);
    await expect(page.getByRole("button", { name: "Agent", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Canvas", exact: true }).click();
    await expect(page.getByLabel("Canvas preview")).toBeVisible();
    await page.getByRole("button", { name: "Context", exact: true }).click();
    await expect(page.getByLabel("Inspector 与 Context")).toBeVisible();
  });
});
