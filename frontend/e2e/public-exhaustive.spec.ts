import { expect, test } from "@playwright/test";
import { expectApiEnvelope } from "./helpers";

/**
 * 公开站补充：核心 public API、feed、页脚、英文、健康检查（经 Vite 代理，与页面同源）
 */
test.describe("公开站 · 逐一补充", () => {
  test("元数据：software + articles/feed + health 经 fetch 返回 code=0", async ({ page }) => {
    await page.goto("/");
    await expectApiEnvelope(page, "/api/public/v1/software/categories");
    await expectApiEnvelope(page, "/api/public/v1/articles/feed?feed=apps&page_size=5");
    await expectApiEnvelope(page, "/api/public/v1/articles/categories?feed=apps&published_within_days=3650");
    await expectApiEnvelope(page, "/api/public/v1/health");
  });

  test("应用页：articles/feed 请求 code=0", async ({ page }) => {
    const w = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/articles/feed") && r.url().includes("feed=apps") && r.status() === 200
    );
    await page.goto("/apps");
    const feedRes = await w;
    const feedJ = (await feedRes.json()) as { code: number; data: { items?: unknown[] } };
    expect(feedJ.code).toBe(0);
    expect(Array.isArray(feedJ.data?.items)).toBeTruthy();
  });

  test("页脚：完整说明链到 /about 且 CMS 数据正常", async ({ page }) => {
    await page.goto("/");
    const pg = page.waitForResponse((r) => r.url().includes("/api/public/v1/pages/about") && r.status() === 200);
    await page.getByRole("link", { name: /关于.*完整说明/u }).click();
    await expect(page).toHaveURL(/\/about$/);
    await pg;
    await expect(page.getByRole("heading", { name: "关于", exact: true }).first()).toBeVisible();
  });

  test("语言 EN：导航文案为 AI apps / AI news / Downloads / About", async ({ page }) => {
    await page.goto("/apps");
    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.locator("header").getByRole("link", { name: "AI apps", exact: true })).toBeVisible();
    await expect(page.locator("header").getByRole("link", { name: "AI news", exact: true })).toBeVisible();
    await expect(page.locator("header").getByRole("link", { name: "Downloads", exact: true })).toBeVisible();
    await expect(page.locator("header").getByRole("link", { name: "About", exact: true })).toBeVisible();
    const feedP = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/articles/feed") && r.status() === 200
    );
    await page.reload();
    const feedRes = await feedP;
    const j = (await feedRes.json()) as { code: number };
    expect(j.code).toBe(0);
  });
});
