import { expect, test } from "@playwright/test";

async function fillSupportContext(page: import("@playwright/test").Page) {
  await page.getByLabel("Reason").fill("incident mitigation");
  await page.getByLabel("Ticket / reference").fill("INC-6401");
}

async function confirmAction(page: import("@playwright/test").Page) {
  await page.getByLabel("Second confirmation").fill("CONFIRM");
  await page.getByRole("button", { name: "Confirm action" }).click();
  await expect(page.getByRole("dialog", { name: "Confirm sensitive admin action" })).toBeHidden();
}

test.beforeEach(async ({ page }) => {
  await page.goto("/app/admin");
  await expect(page.getByRole("heading", { name: "Operations Console" })).toBeVisible();
});

test("platform admin is separate, overview is service-backed and PII starts masked", async ({ page }) => {
  await expect(page.getByText("PLATFORM ADMIN").first()).toBeVisible();
  await expect(page.getByText("Daily generations")).toBeVisible();
  await expect(page.getByText("2.75%")).toBeVisible();
  await page.getByRole("button", { name: "Users & Orgs" }).click();
  await expect(page.getByText("n•••@example.test")).toBeVisible();
  await expect(page.getByText("operator@example.test")).toHaveCount(0);
});

test("PII reveal requires reason and ticket while View-as is readonly", async ({ page }) => {
  await page.getByRole("button", { name: "Users & Orgs" }).click();
  await page.getByRole("button", { name: "Reveal PII" }).first().click();
  await expect(page.getByRole("alert")).toContainText("Reason and ticket");
  await fillSupportContext(page);
  await page.getByRole("button", { name: "Reveal PII" }).first().click();
  await expect(page.getByText(/PII REVEALED/)).toBeVisible();
  await page.getByRole("button", { name: "View-as readonly" }).first().click();
  await expect(page.getByText(/VIEW-AS · READ ONLY/)).toBeVisible();
});

test("provider disable and queue requeue use sensitive confirmation", async ({ page }) => {
  await fillSupportContext(page);
  await page.getByRole("button", { name: "Providers" }).click();
  await page.getByRole("button", { name: "Disable 1 hour" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("provider:image-primary");
  await confirmAction(page);
  await expect(page.getByText("DISABLED").first()).toBeVisible();

  await fillSupportContext(page);
  await page.getByRole("button", { name: "Queue" }).click();
  const payload = page.getByText(/payload:\/\/task-64\/v1/);
  await expect(payload).toBeVisible();
  await page.getByRole("button", { name: "Requeue original payload" }).click();
  await confirmAction(page);
  await expect(payload).toBeVisible();
});

test("registry and billing writes use the same guarded action panel", async ({ page }) => {
  await fillSupportContext(page);
  await page.getByRole("button", { name: "Registry" }).click();
  await page.getByRole("button", { name: "Disable via registry service" }).first().click();
  await confirmAction(page);

  await fillSupportContext(page);
  await page.getByRole("button", { name: "Billing" }).click();
  await page.getByRole("button", { name: "Grant +100 credits to org-lumi" }).click();
  await expect(page.getByRole("dialog")).toContainText("organization:org-lumi");
  await confirmAction(page);
});

test("mobile admin console remains usable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Operations Console" })).toBeVisible();
  await page.getByRole("button", { name: "Queue" }).click();
  await expect(page.getByText("queue-64")).toBeVisible();
});
