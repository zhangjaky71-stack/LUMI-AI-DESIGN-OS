import { expect, test } from "@playwright/test";

const brandKit = "/app/brands";

test.describe("NODE-58 Brand Kit UI", () => {
  test("edits versioned palette tokens and warns on duplicate values", async ({ page }) => {
    await page.goto(brandKit);
    await expect(page.getByRole("heading", { name: "Brand Kit" })).toBeVisible();
    await expect(page.getByText("Published v1.0.0").first()).toBeVisible();
    await page.getByRole("button", { name: "+ Add color" }).click();
    const hex = page.getByLabel("Color 4 HEX");
    await hex.fill("#1c1917");
    await expect(page.getByText("Duplicate color value")).toHaveCount(2);
    await expect(page.getByText("Unsaved draft")).toBeVisible();
    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText(/草稿已保存/)).toBeVisible();
  });

  test("uploads logo through governed asset lifecycle and exposes variant constraints", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Assets & Type" }).click();
    const input = page.locator("label", { hasText: "Upload logo" }).locator("input[type=file]");
    await input.setInputFiles({
      name: "campaign-secondary.svg",
      mimeType: "image/svg+xml",
      buffer: Buffer.from("<svg></svg>"),
    });
    const row = page.getByText("campaign-secondary.svg").locator("xpath=ancestor::article");
    await expect(row).toBeVisible();
    await expect(row.getByText(/READY · USER_OWNED/)).toBeVisible();
    await expect(row.locator("select").first()).toHaveValue("SECONDARY");
  });

  test("unknown font rights are visible and block publishing while font is active", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Assets & Type" }).click();
    await page.getByLabel("上传资产授权声明").selectOption("UNKNOWN");
    const input = page.locator("label", { hasText: "Upload font" }).locator("input[type=file]");
    await input.setInputFiles({
      name: "UnknownBrand.woff2",
      mimeType: "font/woff2",
      buffer: Buffer.from("font"),
    });
    await expect(page.getByText("UnknownBrand")).toBeVisible();
    await expect(page.getByText(/License unknown/)).toBeVisible();
    await expect(page.getByText(/UNKNOWN 授权声明/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Publish BrandRuleSet" })).toBeDisabled();
  });

  test("Brand Guide import creates cited proposals that require complete human review", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Brand Guide" }).click();
    const input = page.locator("label", { hasText: "Choose PDF" }).locator("input[type=file]");
    await input.setInputFiles({
      name: "lumi-brand-guide.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("pdf"),
    });
    await expect(page.getByText("PROPOSED", { exact: true })).toBeVisible();
    await expect(page.getByText(/page 8/)).toBeVisible();
    const reviews = page.locator('select[aria-label$=" review"]');
    await expect(reviews).toHaveCount(3);
    await reviews.nth(0).selectOption("APPROVE");
    await page.locator('select[aria-label$=" severity"]').nth(0).selectOption("HARD");
    await reviews.nth(1).selectOption("REJECT");
    await page.getByRole("button", { name: "Apply human review" }).click();
    await expect(page.getByRole("alert")).toContainText("逐条确认");
    await reviews.nth(2).selectOption("REJECT");
    await page.getByRole("button", { name: "Apply human review" }).click();
    await expect(page.getByText("APPROVED", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Voice & Rules" }).click();
    await expect(page.getByText("APPROVED_GUIDE_EXTRACTION")).toBeVisible();
  });

  test("publishes a new immutable version, advances CURRENT binding and preserves PINNED", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Publish BrandRuleSet" }).click();
    await expect(page.getByText(/BrandRuleSet v2.0.0 已发布/)).toBeVisible();
    await page.getByRole("button", { name: "Projects & Compliance" }).click();
    const current = page.getByText("夏季新品发布").locator("xpath=ancestor::article");
    const pinned = page.getByText("门店导视更新").locator("xpath=ancestor::article");
    await expect(current.getByText("Resolved v2.0.0")).toBeVisible();
    await expect(pinned.getByText("Resolved v1.0.0")).toBeVisible();
  });

  test("checks exact ArtifactVersion and deep-links the violation to the exact Canvas node", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Projects & Compliance" }).click();
    await page.getByRole("button", { name: "Run Brand check" }).click();
    await expect(page.getByText("78", { exact: true })).toBeVisible();
    await expect(page.getByText("FAIL", { exact: true })).toBeVisible();
    const jump = page.getByRole("link", { name: "在 Canvas 中定位 →" }).first();
    await expect(jump).toHaveAttribute("href", /focusNode=node-offer/);
    await expect(jump).toHaveAttribute("href", /brandRuleVersion=1.0.0/);
    await jump.click();
    const canvas = page.getByLabel("Canvas preview");
    await expect(canvas).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Offer Badge", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.getByText("Compliance source v1.0.0", { exact: true })).toBeVisible();
  });

  test("rejects stale compliance versions instead of silently using the latest", async ({ page }) => {
    await page.goto(brandKit);
    await page.getByRole("button", { name: "Projects & Compliance" }).click();
    await page.getByLabel("Rule version").selectOption("0.0.0-stale");
    await page.getByRole("button", { name: "Run Brand check" }).click();
    await expect(page.getByRole("alert")).toContainText("BRAND_RULE_VERSION_STALE");
  });

  test("freezes the resolved BrandRuleSet version into a newly started Agent Run", async ({ page }) => {
    await page.goto("/app/projects/project-summer-launch/workspace");
    await expect(page.getByText("Brand v1.0.0 · next Run", { exact: true })).toBeVisible();
    await page.getByLabel("给 LUMI Agent 的指令").fill("按当前 Brand Kit 创建一个方向");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("Brand v1.0.0 · frozen", { exact: true }).first()).toBeVisible();
  });

  test("remains usable as a focused mobile settings surface", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(brandKit);
    await expect(page.getByRole("heading", { name: "Brand Kit" })).toBeVisible();
    await page.getByRole("button", { name: "Assets & Type" }).click();
    await expect(page.getByRole("heading", { name: "Fonts & rights" })).toBeVisible();
  });
});
