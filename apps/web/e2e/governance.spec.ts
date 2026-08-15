import { expect, test } from "@playwright/test";

async function openGovernance(page: import("@playwright/test").Page) {
  await page.goto("/app/settings/governance");
  await expect(page.getByRole("heading", { name: "Audit, Retention & Data Governance" })).toBeVisible();
  await expect(page.getByText("Tenant scoped")).toBeVisible();
}

test("audit search is organization-scoped and exposes safe identity fields", async ({ page }) => {
  await openGovernance(page);
  await expect(page.getByText("admin queue requeued")).toBeVisible();
  await expect(page.getByText("designer-agent @ v7")).toBeVisible();
  await page.getByLabel("Result").selectOption("DENIED");
  await page.getByRole("button", { name: "Search audit" }).click();
  await expect(page.getByText("project archived")).toBeVisible();
  await expect(page.getByText("admin queue requeued")).toHaveCount(0);
});

test("retention view lists seven classes and publishes the next immutable version", async ({ page }) => {
  await openGovernance(page);
  await page.getByRole("button", { name: "Retention" }).click();
  for (const name of ["SECURITY_AUDIT", "BILLING", "CONTENT", "AGENT_TRACE", "TEMP_SANDBOX", "EXPORT", "ANALYTICS"]) {
    await expect(page.getByText(new RegExp(name)).first()).toBeVisible();
  }
  await expect(page.getByText("TEMP_SANDBOX:sandbox-old-65")).toBeVisible();
  await expect(page.getByText(/法律\/合规审查/)).toBeVisible();
  await page.getByLabel("Retention class").selectOption("CONTENT");
  await page.getByLabel("Retention days").fill("90");
  await page.getByLabel("Policy note").fill("Enterprise content policy revision");
  await expect(page.getByText("Next exact version: v2")).toBeVisible();
  await page.getByRole("button", { name: "Publish next version" }).click();
  await expect(page.getByText("CONTENT · v2")).toBeVisible();
});

test("legal hold blocks deletion until release and retained evidence stays counted", async ({ page }) => {
  await openGovernance(page);
  await page.getByRole("button", { name: "Legal Holds" }).click();
  await page.getByLabel("User scope ID").fill("subject-node65");
  await page.getByLabel("Reason code").fill("LITIGATION");
  await page.getByLabel("Ticket").fill("LEGAL-6501");
  await page.getByRole("button", { name: "Create hold" }).click();
  await expect(page.getByText(/LEGAL · USER:subject-node65/)).toBeVisible();

  await page.getByRole("button", { name: "Deletion" }).click();
  await page.getByLabel("Subject user ID").fill("subject-node65");
  await page.getByRole("button", { name: "Request deletion" }).click();
  await expect(page.getByText("BLOCKED_HOLD")).toBeVisible();
  await expect(page.getByText(/Blocked by hold-e2e/)).toBeVisible();

  await page.getByRole("button", { name: "Legal Holds" }).click();
  await page.getByRole("button", { name: "Release with reason + ticket" }).click();
  await expect(page.getByText("No active holds.")).toBeVisible();

  await page.getByRole("button", { name: "Deletion" }).click();
  await page.getByRole("button", { name: "Execute workflow" }).click();
  await expect(page.getByText("COMPLETED")).toBeVisible();
  await expect(page.getByText("deleted 1 · anonymized 1 · retained 1")).toBeVisible();
});

test("audit export returns a fresh signed lease without creating a second render job", async ({ page }) => {
  await openGovernance(page);
  await page.getByRole("button", { name: "Exports" }).click();
  await expect(page.getByText("audit-export-node65-ready")).toBeVisible();
  await page.getByRole("button", { name: "Export JSON" }).click();
  await expect(page.getByText(/audit-export-e2e-2/).first()).toBeVisible();
  const jobCardsBefore = await page.getByText(/audit-export-/).count();
  await page.getByRole("button", { name: "Get fresh download" }).first().click();
  const firstHref = await page.getByRole("link", { name: /Open fresh signed download/ }).getAttribute("href");
  await page.getByRole("button", { name: "Get fresh download" }).first().click();
  const secondHref = await page.getByRole("link", { name: /Open fresh signed download/ }).getAttribute("href");
  expect(firstHref).not.toBe(secondHref);
  expect(await page.getByText(/audit-export-/).count()).toBe(jobCardsBefore);
});

test("governance center remains usable on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openGovernance(page);
  await page.getByRole("button", { name: "Retention" }).click();
  await expect(page.getByText(/SECURITY_AUDIT/).first()).toBeVisible();
  await page.getByRole("button", { name: "Exports" }).click();
  await expect(page.getByRole("button", { name: "Export JSON" })).toBeVisible();
});
