import { expect, test } from "@playwright/test";

test.describe("NODE-52 App Shell", () => {
  test("anonymous requests are redirected to the generic login route", async ({
    context,
    page,
  }) => {
    await context.addCookies([
      {
        name: "lumi_e2e_anon",
        value: "1",
        url: "http://127.0.0.1:3000",
      },
    ]);
    await page.goto("/app/projects");
    await expect(page).toHaveURL(/\/login\?reason=session-required/);
    await expect(
      page.getByRole("heading", { name: "登录 LUMI" }),
    ).toBeVisible();
  });

  test("authenticated session enters a stable server-rendered product shell", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await expect(
      page.getByRole("navigation", { name: "主导航" }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "项目" })).toBeVisible();
    await expect(page.getByLabel("切换组织")).toHaveValue("org-lumi");
  });

  test("organization switch resets shell scope and routes to the project root", async ({
    page,
  }) => {
    await page.goto("/app/brands");
    await page.getByLabel("切换组织").selectOption("org-northstar");
    await expect(page).toHaveURL(/\/app\/projects$/);
    await expect(page.getByLabel("切换组织")).toHaveValue("org-northstar");
  });

  test("command palette and skip navigation are keyboard reachable", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page.keyboard.press("Tab");
    await expect(
      page.getByRole("link", { name: "跳到主要内容" }),
    ).toBeFocused();
    await page.keyboard.press("Control+K");
    await expect(
      page.getByRole("dialog", { name: "命令面板" }),
    ).toBeVisible();
    await expect(page.getByLabel("搜索命令")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("dialog", { name: "命令面板" }),
    ).toHaveCount(0);
    await expect(page.getByLabel("打开命令面板")).toBeFocused();
  });

  test("mobile viewport keeps primary navigation reachable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/projects");
    await expect(
      page.getByRole("navigation", { name: "主导航" }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "品牌" })).toBeVisible();
  });
});
