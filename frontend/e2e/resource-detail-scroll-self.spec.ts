import { expect, test } from "@playwright/test";

/**
 * 依赖 `npm run dev:mock`（VITE_MOCK_PUBLIC_API），由 playwright.resource-mock.config.ts 单独拉起。
 * 断言：长文详情下滚轮能带动 document 滚动（避免「只能拖滚动条」回归）。
 */
test.describe("详情页 · 内置 mock 与滚轮", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("lang", "zh");
    });
  });

  test("大屏：正文区域滚轮使 scrollY 增加", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/resources/7");

    await expect(page.getByRole("heading", { name: /Mock 文章 #7/u })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("模拟长文").first()).toBeVisible();

    const maxY = await page.evaluate(
      () => document.documentElement.scrollHeight - window.innerHeight,
    );
    expect(maxY, "mock 长文应撑出可滚动高度").toBeGreaterThan(200);

    const y0 = await page.evaluate(() => window.scrollY);
    await page.mouse.move(960, 420);
    await page.mouse.wheel(0, 900);

    await expect
      .poll(async () => page.evaluate(() => window.scrollY), {
        timeout: 8000,
        message: "在右侧正文区域滚轮后 window.scrollY 应增加",
      })
      .toBeGreaterThan(Math.max(0, y0) + 40);
  });

  test("大屏：正文列偏左（非侧栏）滚轮仍能带动页面", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/resources/7");
    await expect(page.getByRole("heading", { name: /Mock 文章 #7/u })).toBeVisible({ timeout: 60_000 });

    await page.evaluate(() => window.scrollTo(0, 0));
    const y0 = await page.evaluate(() => window.scrollY);

    // 1280 宽下 ~280px 侧栏 + gap：x≈520 落在正文列左侧，避免命中侧栏内部滚动区
    await page.mouse.move(520, 420);
    await page.mouse.wheel(0, 700);

    await expect
      .poll(async () => page.evaluate(() => window.scrollY), {
        timeout: 8000,
        message: "正文列偏左滚轮后 window.scrollY 应增加",
      })
      .toBeGreaterThan(y0 + 30);
  });
});
