import { expect, test, type Page } from "@playwright/test";

const workspace = "/app/projects/project-summer-launch/workspace";

async function startRun(page: Page) {
  const canvas = page.getByLabel("Canvas preview");
  await canvas.getByRole("button", { name: "Headline", exact: true }).click();
  await page.getByLabel("给 LUMI Agent 的指令").fill("生成一个可评审方向并展示安全执行进度");
  await page.getByRole("button", { name: "Send", exact: true }).click();
}

test.describe("NODE-57 Agent Timeline", () => {
  test("projects streamed safe stages, deduplicates realtime delivery and pins waiting approval", async ({ page }) => {
    await page.goto(workspace);
    await startRun(page);
    const timeline = page.getByLabel("Agent Timeline");
    await expect(timeline).toBeVisible();
    await expect(timeline.getByText("正在分析 Brief、Brand Kit 与选中对象。")).toBeVisible();
    await expect(timeline.getByText("已锁定产品身份约束，正在生成视觉方向。")).toHaveCount(1);
    await expect(timeline.getByRole("heading", { name: "夏季新品主视觉方向 A" })).toBeVisible();
    await expect(timeline.getByLabel("Waiting for user")).toBeVisible();
    await expect(timeline.getByRole("heading", { name: "确认主视觉方向" })).toBeVisible();
  });

  test("filters provider fallback without exposing raw execution payload", async ({ page }) => {
    await page.goto(workspace);
    const timeline = page.getByLabel("Agent Timeline");
    await timeline.getByRole("button", { name: "Generation", exact: true }).click();
    await expect(timeline.getByText("Provider fallback", { exact: true })).toBeVisible();
    await expect(timeline.getByText(/主图像 Provider 当前处于降级状态/)).toBeVisible();
    await expect(timeline.getByText(/Bearer secret|raw_tool_payload|reasoning trace/i)).toHaveCount(0);
  });

  test("failed task shows real progress, safe error, fallback and retry", async ({ page }) => {
    await page.goto("/app/projects/project-agent-retry/workspace");
    const timeline = page.getByLabel("Agent Timeline");
    await expect(timeline.getByText("2/4", { exact: true })).toBeVisible();
    await expect(timeline.getByText("PROVIDER_TIMEOUT", { exact: true })).toBeVisible();
    await expect(timeline.getByText(/req-timeline-retry-01/)).toBeVisible();
    await expect(timeline.getByText(/Backup provider available on retry/)).toBeVisible();
    await timeline.getByRole("button", { name: "Retry 生成视觉方向", exact: true }).click();
    await expect(timeline.getByText("Run RUNNING", { exact: true })).toBeVisible();
  });

  test("canonical seeded timeline restores after refresh without browser event history", async ({ page }) => {
    await page.goto("/app/projects/project-agent-retry/workspace");
    const timeline = page.getByLabel("Agent Timeline");
    await expect(timeline.getByText("2/4", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Agent Timeline").getByText("2/4", { exact: true })).toBeVisible();
    await expect(page.getByText(/req-timeline-retry-01/)).toBeVisible();
  });

  test("cancelled canonical run has an explicit terminal state and no invented spinner", async ({ page }) => {
    await page.goto("/app/projects/project-agent-cancelled/workspace");
    const timeline = page.getByLabel("Agent Timeline");
    await expect(timeline.getByText("Run CANCELED", { exact: true })).toBeVisible();
    await expect(timeline.getByText(/Run 已由用户停止/)).toBeVisible();
    await expect(timeline.getByText("CANCELED", { exact: true }).first()).toBeVisible();
    await expect(timeline.getByText(/99%|100%/)).toHaveCount(0);
  });

  test("artifact timeline handoff preserves exact ArtifactVersion and focuses Canvas on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(workspace);
    await startRun(page);
    const timeline = page.getByLabel("Agent Timeline");
    await expect(timeline.getByText(/artifact-version-.*-1/)).toBeVisible();
    await timeline.getByRole("button", { name: "查看 Canvas", exact: true }).click();
    await expect(page.getByLabel("Canvas preview")).toBeVisible();
  });

  test("approval action resumes canonical UI without leaking private reasoning", async ({ page }) => {
    await page.goto(workspace);
    await startRun(page);
    const timeline = page.getByLabel("Agent Timeline");
    await timeline.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(timeline.getByText("APPROVED", { exact: true })).toBeVisible();
    await expect(timeline.getByText(/private reasoning|raw tool payload|stack trace/i)).toHaveCount(0);
  });
});
