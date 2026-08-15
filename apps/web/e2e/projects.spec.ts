import { expect, test } from "@playwright/test";

test.describe("NODE-53 Projects UI", () => {
  test("search, cursor pagination and organization switch stay tenant scoped", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await expect(
      page.getByRole("heading", { name: "项目", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "加载更多" }),
    ).toBeVisible();

    const before = await page.locator("article").count();
    await page.getByRole("button", { name: "加载更多" }).click();
    await expect
      .poll(async () => page.locator("article").count())
      .toBeGreaterThan(before);

    await page.getByRole("searchbox", { name: "搜索项目" }).fill("菜单");
    await expect(
      page.getByRole("link", { name: "秋季菜单更新", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "夏季新品发布", exact: true }),
    ).toHaveCount(0);

    await page.getByRole("searchbox", { name: "搜索项目" }).fill("");
    await page.getByLabel("切换组织").selectOption("org-northstar");
    await expect(page).toHaveURL(/\/app\/projects$/);
    await expect(
      page.getByRole("link", { name: "Northstar Launch Kit", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "夏季新品发布", exact: true }),
    ).toHaveCount(0);
  });

  test("a natural-language sentence is sufficient to create and enter a project", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page.getByRole("button", { name: "新建项目" }).first().click();
    await page
      .getByLabel("一句话描述")
      .fill("为新品冷萃咖啡做一套高级极简夏季发布视觉");
    await page.getByRole("button", { name: "直接开始" }).click();
    await expect(
      page.getByRole("heading", { name: "项目已创建" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "进入项目" }).click();
    await expect(
      page.getByRole("heading", { name: /新品冷萃咖啡/ }),
    ).toBeVisible();
    await expect(page.getByText(/STRUCTURED BRIEF/i)).toBeVisible();
  });

  test("reference upload preserves an explicit scanner rejection", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page.getByRole("button", { name: "新建项目" }).first().click();
    await page
      .getByLabel("一句话描述")
      .fill("做一张产品主视觉并使用上传的 Logo");
    await page.locator('input[type="file"]').setInputFiles({
      name: "scan-fail-logo.png",
      mimeType: "image/png",
      buffer: Buffer.from("fixture"),
    });
    await page
      .getByLabel("scan-fail-logo.png 参考类型")
      .selectOption("logo");
    await page.getByRole("button", { name: "直接开始" }).click();
    await expect(page.getByText("不可用 · SCAN_FAILED")).toBeVisible();
  });

  test("optional Brand and deliverable context flow into the created project", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page.getByRole("button", { name: "新建项目" }).first().click();
    await page.getByLabel("一句话描述").fill("为会员活动做一套品牌海报");
    await page.getByRole("button", { name: "下一步" }).click();
    await page.getByLabel("Brand Kit").selectOption("brand-lumi");
    await page.getByLabel("主视觉").check();
    await page.getByRole("button", { name: "创建项目" }).click();
    await expect(
      page.getByRole("heading", { name: "项目已创建" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "进入项目" }).click();
    await expect(page.getByText(/LUMI Coffee/).first()).toBeVisible();
  });

  test("rename conflict rolls optimistic UI back instead of overwriting a newer version", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page
      .getByRole("searchbox", { name: "搜索项目" })
      .fill("门店物料升级");
    await expect(
      page.getByRole("link", { name: "门店物料升级", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "重命名" }).click();
    await page.getByLabel("项目名称").fill("门店物料升级 2.0");
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(
      "项目已在其他位置更新",
    );
    await expect(
      page.getByRole("link", { name: "门店物料升级", exact: true }),
    ).toBeVisible();
  });

  test("archive is confirmed and restore never restarts historical Agent runs", async ({
    page,
  }) => {
    await page.goto("/app/projects");
    await page
      .getByRole("searchbox", { name: "搜索项目" })
      .fill("秋季菜单更新");
    await page.getByRole("button", { name: "归档" }).click();
    await expect(page.getByRole("alertdialog")).toBeVisible();
    await page.getByRole("button", { name: "确认归档" }).click();
    await expect(page.getByRole("status")).toContainText("项目已归档");

    await page
      .getByRole("searchbox", { name: "搜索项目" })
      .fill("春季活动归档");
    await page.getByRole("button", { name: "恢复" }).click();
    await expect(page.getByRole("status")).toContainText(
      "历史 Agent Run 不会自动重启",
    );
  });

  test("significant Brief edits create a new BriefVersion", async ({ page }) => {
    await page.goto("/app/projects/project-summer-launch");
    await expect(page.getByText("Brief v2")).toBeVisible();
    await page.getByRole("button", { name: "编辑 Brief" }).click();
    await page.getByLabel("Objective").fill("更新后的夏季新品发布目标");
    await page
      .getByRole("button", { name: "保存为新 BriefVersion" })
      .click();
    await expect(page.getByRole("status")).toContainText("v3");
    await expect(page.getByText("更新后的夏季新品发布目标")).toBeVisible();
  });
});
