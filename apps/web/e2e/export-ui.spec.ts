import { expect, test } from "@playwright/test";

const route = "/app/projects/project-summer-launch/export";

test.describe("NODE-60 Export Product UX", () => {
  test("locks an exact version and only shows supported format capabilities", async ({ page }) => {
    await page.goto(route);
    await expect(page.getByTestId("exact-version-lock")).toContainText("artifact-summer-launch-design-v4");
    await expect(page.getByTestId("exact-version-lock")).toContainText("design-summer-launch-v4");
    await expect(page.getByTestId("format-options")).toContainText("PNG");
    await expect(page.getByTestId("format-options")).toContainText("SVG");
    await expect(page.getByTestId("unsupported-hidden")).toContainText("CMYK");
    await expect(page.getByTestId("unsupported-hidden")).toContainText("PSD");
  });

  test("hides vector and batch-only options for a raster single-frame source", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("source-select").selectOption("source-raster-v3");
    await expect(page.getByTestId("format-options")).not.toContainText("SVG");
    await expect(page.getByTestId("format-options")).not.toContainText("ZIP Batch");
  });

  test("separates Crop/Scale from AI Adapt when the aspect ratio changes", async ({ page }) => {
    await page.goto(route);
    await page.getByRole("button", { name: "Preset" }).click();
    await expect(page.getByTestId("aspect-ratio-choice")).toContainText("Crop");
    await expect(page.getByTestId("aspect-ratio-choice")).toContainText("Scale");
    const adapt = page.getByTestId("ai-adapt-link");
    await expect(adapt).toContainText("new DesignVersion");
    await expect(adapt).toHaveAttribute("href", /adaptFromDesignVersion=design-summer-launch-v4/);
  });

  test("creates a lifecycle-shaped job and only downloads after READY", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("create-export").click();
    await expect(page.getByText("Exact source frozen:")).toBeVisible();
    await expect(page.getByLabel("Service reported progress 100")).toBeVisible({ timeout: 4_000 });
    await page.getByRole("button", { name: "Get fresh download" }).click();
    await expect(page.getByTestId("signed-download")).toContainText("Signed download ready");
  });

  test("refreshes an expired-style signed link without creating a new job", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("create-export").click();
    await expect(page.getByLabel("Service reported progress 100")).toBeVisible({ timeout: 4_000 });
    const jobCode = page.locator("code").filter({ hasText: /^export-job-/ }).first();
    const before = await jobCode.textContent();
    await page.getByRole("button", { name: "Get fresh download" }).click();
    const first = await page.getByTestId("signed-download").getByRole("link").getAttribute("href");
    await page.getByRole("button", { name: "Get fresh download" }).click();
    const second = await page.getByTestId("signed-download").getByRole("link").getAttribute("href");
    expect(first).not.toBe(second);
    await expect(jobCode).toHaveText(before ?? "");
  });

  test("shows zero AI export charge and a safe job-level failure boundary", async ({ page }) => {
    await page.goto(route);
    await expect(page.getByTestId("cost-estimate")).toContainText("No AI generation charge");
    const history = page.getByTestId("export-history");
    await expect(history).toContainText("Export could not be completed");
    await expect(history).not.toContainText("Retry failed frame");
  });

  test("batch source exposes only formats with real multi-frame support", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("source-select").selectOption("source-batch-v4");
    await expect(page.getByTestId("format-options")).toContainText("PDF");
    await expect(page.getByTestId("format-options")).toContainText("ZIP Batch");
    await expect(page.getByTestId("format-options")).toContainText("LUMI Project Package");
    await expect(page.getByTestId("format-options")).not.toContainText("PNG");
  });

  test("remains usable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: "Export Center" })).toBeVisible();
    await expect(page.getByTestId("create-export")).toBeVisible();
  });
});
