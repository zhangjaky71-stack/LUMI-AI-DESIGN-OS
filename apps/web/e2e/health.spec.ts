import { expect, test } from "@playwright/test";

test("health page renders", async ({ page }) => {
  await page.goto("/health");
  await expect(page.getByRole("heading", { name: "ok" })).toBeVisible();
});
