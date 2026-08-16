import { expect, test, type Page } from "@playwright/test";

const criticalRoutes = [
  "/app/projects",
  "/app/projects/project-summer-launch/workspace",
  "/app/billing",
];

async function unnamedInteractiveControls(page: Page) {
  return page.locator("button, a[href], input:not([type='hidden']), select, textarea").evaluateAll(
    (elements) =>
      elements
        .filter((element) => element.getAttribute("aria-hidden") !== "true")
        .filter((element) => {
          const html = element as HTMLElement;
          const ariaLabel = element.getAttribute("aria-label")?.trim() ?? "";
          const title = element.getAttribute("title")?.trim() ?? "";
          const labelledBy = element.getAttribute("aria-labelledby") ?? "";
          const labelledText = labelledBy
            .split(/\s+/)
            .filter(Boolean)
            .map((id) => document.getElementById(id)?.textContent?.trim() ?? "")
            .join(" ")
            .trim();
          const nativeLabels =
            "labels" in element
              ? Array.from((element as HTMLInputElement).labels ?? [])
                  .map((label) => label.textContent?.trim() ?? "")
                  .join(" ")
                  .trim()
              : "";
          const text = html.innerText?.trim() ?? "";
          const value =
            element instanceof HTMLInputElement &&
            ["button", "submit", "reset"].includes(element.type)
              ? element.value.trim()
              : "";
          return !(ariaLabel || title || labelledText || nativeLabels || text || value);
        })
        .map((element) => ({
          tag: element.tagName.toLowerCase(),
          type: element.getAttribute("type"),
          id: element.id,
          className: element.getAttribute("class"),
        })),
  );
}

async function imagesMissingAlternative(page: Page) {
  return page.locator("img").evaluateAll((images) =>
    images
      .filter((image) => image.getAttribute("aria-hidden") !== "true")
      .filter((image) => image.getAttribute("role") !== "presentation")
      .filter((image) => !image.hasAttribute("alt"))
      .map((image) => ({ src: image.getAttribute("src"), className: image.className })),
  );
}

for (const route of criticalRoutes) {
  test(`critical route ${route} exposes named controls and semantic structure`, async ({ page }) => {
    await page.goto(route);
    await expect(page.locator("main")).toHaveCount(1);
    await expect(page.locator("h1, h2").first()).toBeVisible();

    const unnamed = await unnamedInteractiveControls(page);
    expect(unnamed, `unnamed interactive controls on ${route}: ${JSON.stringify(unnamed)}`).toEqual([]);

    const missingAlt = await imagesMissingAlternative(page);
    expect(missingAlt, `images without alt/presentation semantics on ${route}: ${JSON.stringify(missingAlt)}`).toEqual([]);
  });
}

test("keyboard entry point and command dialog preserve explicit focus", async ({ page }) => {
  await page.goto("/app/projects");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "跳到主要内容" })).toBeFocused();

  await page.keyboard.press("Control+K");
  const dialog = page.getByRole("dialog", { name: "命令面板" });
  await expect(dialog).toBeVisible();
  await expect(page.getByLabel("搜索命令")).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel("打开命令面板")).toBeFocused();
});

test("critical form controls retain explicit labels", async ({ page }) => {
  await page.goto("/app/projects/project-summer-launch/workspace");
  await expect(page.getByLabel("给 LUMI Agent 的指令")).toBeVisible();
  await expect(page.getByLabel("Canvas preview")).toBeVisible();
  await expect(page.getByLabel("Layers 与 Inspector")).toBeVisible();

  await page.goto("/app/billing");
  await expect(page.getByRole("heading", { name: "用量与账单" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create hosted checkout" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create hosted portal session" })).toBeVisible();
});
