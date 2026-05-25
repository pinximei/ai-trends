import { expect, test } from "@playwright/test";
import { buildMockArticleDetail, buildMockArticlesFeed } from "../src/api/public/mockPublicData";

function envelope(data: unknown) {
  return JSON.stringify({ code: 0, message: "ok", data });
}

test.describe("公开站 · 详情 mock（不依赖后端文章 id）", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("lang", "zh");
    });

    await page.route(/\/api\/public\/v1\/articles\/feed/, async (route) => {
      const url = route.request().url();
      const feed = url.includes("feed=apps") ? "apps" : "news";
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: envelope(buildMockArticlesFeed(feed)),
      });
    });

    await page.route(/\/api\/public\/v1\/articles\/7(?:\?|$)/, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json; charset=utf-8",
        body: envelope(buildMockArticleDetail(7)),
      });
    });
  });

  test("mock 详情：标题与长文可见（大屏）", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/resources/7");
    await expect(page.getByRole("heading", { name: /Mock 文章 #7/u })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("模拟长文", { exact: false }).first()).toBeVisible();
  });

  test("mock 详情：数据支撑表格渲染为 table 而非乱序纯文本", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/resources/7");
    const dataSection = page.getByTestId("resource-detail-section-data");
    await expect(dataSection).toBeVisible({ timeout: 30_000 });
    const table = dataSection.getByTestId("article-md-table-wrap").locator("table");
    await expect(table).toBeVisible();
    await expect(table.locator("th")).toHaveCount(3);
    await expect(table.getByRole("cell", { name: "指标" })).toBeVisible();
    await expect(table.getByRole("cell", { name: "MIT" })).toBeVisible();
  });
});
