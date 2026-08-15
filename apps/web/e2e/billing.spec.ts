import { expect, test } from "@playwright/test";

test.describe("NODE-63 Billing", () => {
  test.beforeEach(async ({ page }) => { await page.goto("/app/billing"); });

  test("shows exact plan version, credits and strict truth boundary", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "用量与账单" })).toBeVisible();
    const currentPlan = page.getByRole("article", { name: "Current billing plan" });
    await expect(currentPlan.getByRole("heading", { name: "Pro · v2" })).toBeVisible();
    await expect(currentPlan.getByText("Pinned PlanVersion: pro-v2")).toBeVisible();
    await expect(page.getByText("870", { exact: true })).toBeVisible();
    await expect(page.getByText(/Provider Cost Ledger ≠ Customer Usage/)).toBeVisible();
    await expect(page.getByText(/mock_inv_63 · pro-v2/)).toBeVisible();
  });

  test("uses hosted checkout and never renders payment-card inputs", async ({ page }) => {
    await page.getByRole("button", { name: "Create hosted checkout" }).click();
    await expect(page.getByRole("link", { name: /Open hosted checkout/ })).toHaveAttribute(
      "href", /checkout\.mock\.invalid/,
    );
    await expect(page.locator("input")).toHaveCount(0);
  });

  test("creates hosted portal and schedules cancellation", async ({ page }) => {
    await page.getByRole("button", { name: "Create hosted portal session" }).click();
    await expect(page.getByRole("link", { name: /Open hosted portal/ })).toHaveAttribute(
      "href", /portal\.mock\.invalid/,
    );
    await page.getByRole("button", { name: "Cancel at period end" }).click();
    await expect(page.getByText("CANCEL_AT_PERIOD_END", { exact: true })).toBeVisible();
  });

  test("is usable on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole("heading", { name: "用量与账单" })).toBeVisible();
    await expect(page.getByText("Credit ledger")).toBeVisible();
  });
});
