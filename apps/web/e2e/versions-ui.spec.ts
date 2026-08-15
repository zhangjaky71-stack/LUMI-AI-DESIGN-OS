import { expect, test } from "@playwright/test";

const versions = "/app/projects/project-summer-launch/versions";

test.describe("NODE-59 Versions UI", () => {
  test("shows immutable ArtifactVersion timeline with approval and head state", async ({ page }) => {
    await page.goto(versions);
    await expect(page.getByRole("heading", { name: /夏季新品发布 · Versions/ })).toBeVisible();
    await expect(page.getByLabel("Artifact")).toHaveValue("artifact-campaign-canvas");
    const timeline = page.getByLabel("Version timeline");
    await expect(timeline.getByText("v4", { exact: true })).toBeVisible();
    await expect(timeline.getByText("v2", { exact: true })).toBeVisible();
    await expect(timeline.getByText("APPROVED", { exact: true })).toBeVisible();
    await expect(timeline.getByText("HEAD", { exact: true })).toBeVisible();
  });

  test("compares exact Design IR versions and exposes structured semantic property changes", async ({ page }) => {
    await page.goto(versions);
    await page.getByLabel("Compare before").selectOption("design-v2");
    await page.getByLabel("Compare after").selectOption("design-v4");
    const compare = page.getByLabel("Version compare");
    await expect(compare.getByText("Offer Badge · x", { exact: true })).toBeVisible();
    await expect(compare.getByText("Headline · text", { exact: true })).toBeVisible();
    await expect(compare.getByText(/920 → 944/)).toBeVisible();
    await expect(compare.getByText(/SUMMER DROP → SUMMER FLAVOR DROP/)).toBeVisible();
  });

  test("restores v2 by appending DRAFT v5 while preserving approved v2 and later v4", async ({ page }) => {
    await page.goto(versions);
    await page.getByLabel("Restore source").selectOption("design-v2");
    await page.getByRole("button", { name: "创建恢复版本" }).click();
    await expect(page.getByRole("status")).toContainText("restored as new DRAFT v5");
    const timeline = page.getByLabel("Version timeline");
    await expect(timeline.getByText("v5", { exact: true })).toBeVisible();
    await expect(timeline.getByText("v4", { exact: true })).toBeVisible();
    await expect(timeline.getByText("v2", { exact: true })).toBeVisible();
    const v2 = timeline.locator("article").filter({ has: timeline.getByText("v2", { exact: true }) });
    await expect(v2.getByText("APPROVED", { exact: true })).toBeVisible();
    const v5 = timeline.locator("article").filter({ has: timeline.getByText("v5", { exact: true }) });
    await expect(v5.getByText("DRAFT", { exact: true })).toBeVisible();
    await expect(v5.getByText("HEAD", { exact: true })).toBeVisible();
  });

  test("forks an exact historical version into a named branch without creating a merge", async ({ page }) => {
    await page.goto(versions);
    await page.getByLabel("Compare after").selectOption("design-v3");
    await page.getByLabel("New branch name").fill("Dark Direction");
    await page.getByRole("button", { name: "Fork", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Branch dark-direction created from exact v3");
    await expect(page.getByLabel("Branch")).toHaveValue(/branch-artifact-campaign-canvas-/);
    await expect(page.getByText(/dark-direction ← design-v3 · head design-v3/)).toBeVisible();
  });

  test("notifies about a concurrent newer head without changing the selected compare pair", async ({ page }) => {
    await page.goto(versions);
    await page.getByLabel("Compare before").selectOption("design-v2");
    await page.getByLabel("Compare after").selectOption("design-v4");
    await page.getByRole("button", { name: "检查更新" }).click();
    await expect(page.getByRole("status")).toContainText("newer v5 exists");
    await expect(page.getByLabel("Compare before")).toHaveValue("design-v2");
    await expect(page.getByLabel("Compare after")).toHaveValue("design-v4");
    await expect(page.getByLabel("Version timeline").getByText("v5", { exact: true })).toBeVisible();
  });

  test("supports raster side-by-side and wipe compare modes", async ({ page }) => {
    await page.goto(versions);
    await page.getByLabel("Artifact").selectOption("artifact-hero-raster");
    await expect(page.getByLabel("Artifact")).toHaveValue("artifact-hero-raster");
    await page.getByLabel("Compare before").selectOption("raster-v1");
    await page.getByLabel("Compare after").selectOption("raster-v3");
    await page.getByRole("button", { name: "Wipe", exact: true }).click();
    await expect(page.getByLabel("Wipe compare")).toBeVisible();
    await page.getByLabel("Wipe position").evaluate((node) => {
      const input = node as HTMLInputElement;
      input.value = "70";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await expect(page.getByText(/After · 70%/)).toBeVisible();
  });

  test("shows safe provenance identity without rendering raw private execution content", async ({ page }) => {
    await page.goto(versions);
    const timeline = page.getByLabel("Version timeline");
    await timeline.locator("article", { hasText: "v4" }).getByRole("button", { name: "Provenance" }).click();
    const provenance = page.getByLabel("Version provenance");
    await expect(provenance.getByText("run-summer-21", { exact: true })).toBeVisible();
    await expect(provenance.getByText("backup-image-provider", { exact: true })).toBeVisible();
    await expect(provenance.getByText("d".repeat(64), { exact: true })).toBeVisible();
    await expect(provenance).not.toContainText("raw tool payload");
    await expect(provenance).not.toContainText("BEGIN PRIVATE");
  });

  test("honors provenance permission restrictions", async ({ page }) => {
    await page.goto("/app/projects/project-provenance-denied/versions");
    const provenance = page.getByLabel("Version provenance");
    await expect(provenance.getByText(/Provenance access is restricted/)).toBeVisible();
    await expect(provenance).not.toContainText("backup-image-provider");
  });

  test("remains usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(versions);
    await expect(page.getByRole("heading", { name: /Versions/ })).toBeVisible();
    await expect(page.getByLabel("Version timeline")).toBeVisible();
    await expect(page.getByLabel("Version compare")).toBeVisible();
    await expect(page.getByLabel("Version provenance")).toBeVisible();
  });
});
