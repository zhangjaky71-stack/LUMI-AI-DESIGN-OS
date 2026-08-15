import { expect, test } from "@playwright/test";

const route = "/app/projects/project-node62/approvals";

test("shows exact pending approval, superseded history and canonical boundary", async ({ page }) => {
  await page.goto(route);
  await expect(page.getByRole("heading", { name: "Approval Center" })).toBeVisible();
  await expect(page.getByTestId("approval-truth-boundary")).toContainText("exact version");
  await expect(page.getByTestId("approval-approval-node62-pending")).toContainText("artifact-v4");
  await page.getByRole("button", { name: /History/ }).click();
  await expect(page.getByTestId("approval-approval-node62-v3")).toContainText("SUPERSEDED");
  await expect(page.getByTestId("approval-approval-node62-v3")).toContainText("artifact-v3");
});

test("approves exact version and moves it to immutable history", async ({ page }) => {
  await page.goto(route);
  await page.getByRole("button", { name: "Approve exact version" }).click();
  await expect(page.getByText("No approvals in this view.")).toBeVisible();
  await page.getByRole("button", { name: /History/ }).click();
  await expect(page.getByTestId("approval-approval-node62-pending")).toContainText("APPROVED");
  await expect(page.getByTestId("approval-approval-node62-pending")).toContainText("artifact-v4");
});

test("request changes requires feedback and re-enters workflow", async ({ page }) => {
  await page.goto(route);
  await page.getByRole("button", { name: "Request changes" }).click();
  const textarea = page.getByLabel("Structured feedback");
  await textarea.fill("Reduce density and move CTA lower.");
  await page.getByRole("button", { name: "Send changes to workflow" }).click();
  await page.getByRole("button", { name: /History/ }).click();
  await expect(page.getByTestId("approval-approval-node62-pending")).toContainText("CHANGES REQUESTED");
  await expect(page.getByTestId("approval-approval-node62-pending")).toContainText("Reduce density");
});

test("mobile approval center preserves the exact subject and actions", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(route);
  await expect(page.getByTestId("exact-subject").first()).toContainText("artifact-v4");
  await expect(page.getByRole("button", { name: "Approve exact version" })).toBeVisible();
});
