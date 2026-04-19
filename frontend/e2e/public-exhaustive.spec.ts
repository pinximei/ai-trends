import { expect, test } from "@playwright/test";
import { expectApiEnvelope } from "./helpers";

/**
 * 公开站补充：元数据 API、资源排序、页脚、英文、健康检查（经 Vite 代理，与页面同源）
 */
test.describe("公开站 · 逐一补充", () => {
  test("元数据：industries / segments / metrics / health 经 fetch 返回 code=0", async ({ page }) => {
    await page.goto("/");
    await expectApiEnvelope(page, "/api/public/v1/meta/industries");
    await expectApiEnvelope(page, "/api/public/v1/meta/segments?industry_slug=ai");
    await expectApiEnvelope(page, "/api/public/v1/meta/metrics");
    await expectApiEnvelope(page, "/api/public/v1/health");
  });

  test("资源：热门（快照）与最新 两次请求参数不同且均 code=0", async ({ page }) => {
    const wHot = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/articles") && r.url().includes("sort=hot") && r.status() === 200
    );
    await page.goto("/resources");
    const hotRes = await wHot;
    const hotJ = (await hotRes.json()) as { code: number; data: { total?: number } };
    expect(hotJ.code).toBe(0);
    expect((hotJ.data?.total ?? 0) >= 0).toBeTruthy();

    const wLatest = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/articles") && r.url().includes("sort=latest") && r.status() === 200
    );
    await page.getByRole("button", { name: "最新" }).click();
    const latestRes = await wLatest;
    const latestJ = (await latestRes.json()) as { code: number };
    expect(latestJ.code).toBe(0);
  });

  test("页脚：完整说明链到 /about 且 CMS 数据正常", async ({ page }) => {
    await page.goto("/");
    const pg = page.waitForResponse((r) => r.url().includes("/api/public/v1/pages/about") && r.status() === 200);
    await page.getByRole("link", { name: /关于.*完整说明/u }).click();
    await expect(page).toHaveURL(/\/about$/);
    await pg;
    await expect(page.getByRole("heading", { name: "关于", exact: true }).first()).toBeVisible();
  });

  test("语言 EN：导航文案切换为 Trends / Resources / About", async ({ page }) => {
    await page.goto("/trends");
    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.locator("header").getByRole("link", { name: "Trends", exact: true })).toBeVisible();
    await expect(page.locator("header").getByRole("link", { name: "Resources", exact: true })).toBeVisible();
    await expect(page.locator("header").getByRole("link", { name: "About", exact: true })).toBeVisible();
    const sumP = page.waitForResponse((r) => r.url().includes("/api/public/v1/trends/summary") && r.status() === 200);
    await page.reload();
    const sumRes = await sumP;
    const j = (await sumRes.json()) as { code: number };
    expect(j.code).toBe(0);
  });
});
