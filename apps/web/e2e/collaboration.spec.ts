import { expect, test } from "@playwright/test";

const route = "/app/projects/project-summer-launch/collaboration";

test.describe("NODE-61 Collaboration", () => {
  test("shows same-project presence and distinguishable AI actor", async ({ page }) => {
    await page.goto(route);
    await expect(page.getByTestId("connection-status")).toHaveText("Connected");
    const team = page.getByTestId("team-presence");
    await expect(team).toContainText("2 online");
    await expect(team).toContainText("LUMI Agent");
    await expect(team).toContainText("AI Agent");
    await expect(team).toContainText("collaboration-e2e-…");
  });

  test("posts a mention on the exact current version", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("comment-composer").fill("@LUMI please review the protected headline treatment.");
    await page.getByTestId("mention-select").selectOption("agent-lumi");
    await page.getByTestId("post-comment").click();
    await expect(page.getByTestId("review-threads")).toContainText("please review the protected headline");
    await expect(page.getByTestId("review-threads")).toContainText("artifact-summer-launch-design-v4");
    await expect(page.getByTestId("review-threads")).toContainText("design-summer-launch-v4");
  });

  test("keeps old-version comments visible after their node is gone", async ({ page }) => {
    await page.goto(route);
    const oldAnchor = page.getByTestId("anchor-thread-historical-node");
    await expect(oldAnchor).toContainText("artifact-summer-launch-design-v2");
    await expect(oldAnchor).toContainText("design-summer-launch-v2");
    await expect(oldAnchor).toContainText("Historical snapshot retained");
    await expect(page.getByTestId("review-threads")).toContainText("legacy-price-chip");
  });

  test("resolves and reopens a review thread", async ({ page }) => {
    await page.goto(route);
    const current = page.locator("article").filter({ hasText: "hero-title" });
    await current.getByRole("button", { name: "Resolve" }).click();
    await expect(current).toHaveAttribute("data-status", "RESOLVED");
    await current.getByRole("button", { name: "Reopen" }).click();
    await expect(current).toHaveAttribute("data-status", "REOPENED");
  });

  test("commits different-property edit to a new canonical version", async ({ page }) => {
    await page.goto(route);
    await expect(page.getByTestId("canonical-version")).toContainText("design-summer-launch-v4");
    await page.getByTestId("safe-edit").click();
    await expect(page.getByTestId("canonical-version")).toContainText("design-summer-launch-v5");
    await expect(page.getByTestId("notice")).toContainText("canonical Design Operation API");
  });

  test("reconnect conflict preserves local edit instead of silent overwrite", async ({ page }) => {
    await page.goto(route);
    await page.getByTestId("reconnect-conflict").click();
    const conflict = page.getByTestId("conflict-banner");
    await expect(conflict).toContainText("local edit preserved");
    await expect(conflict).toContainText("hero-title.text");
    await expect(conflict).toContainText("user-editor");
    await expect(page.getByTestId("notice")).toContainText("local edit remains buffered");
  });

  test("states the realtime versus canonical truth boundary", async ({ page }) => {
    await page.goto(route);
    const boundary = page.getByTestId("truth-boundary");
    await expect(boundary).toContainText("Presence/cursor/selection are ephemeral");
    await expect(boundary).toContainText("HTTP Design Operation API");
    await expect(boundary).toContainText("CRDT/realtime state is never the sole design history");
    await expect(page.getByTestId("concurrent-safety")).toContainText("Hard Constraints execute server-side");
  });

  test("remains usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: "Collaboration" })).toBeVisible();
    await expect(page.getByTestId("comment-composer")).toBeVisible();
    await expect(page.getByTestId("concurrent-safety")).toBeVisible();
  });
});
