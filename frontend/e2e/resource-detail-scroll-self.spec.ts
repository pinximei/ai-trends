import { expect, test } from "@playwright/test";

/**
 * 依赖 `npm run dev:mock`（VITE_MOCK_PUBLIC_API），由 playwright.resource-mock.config.ts 单独拉起。
 * 正文在 `[data-testid=resource-detail-article]` 内滚动；整页 document 通常不纵向滚动。
 */
test.describe("详情页 · 内置 mock 与滚轮", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("lang", "zh");
    });
  });

  test("大屏：正文区域滚轮增加右侧栏 scrollTop", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/resources/7");

    await expect(page.getByRole("heading", { name: /Mock 文章 #7/u })).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText("模拟长文").first()).toBeVisible();

    const panel = page.getByTestId("resource-detail-article");
    await expect(panel).toBeVisible();
    const canScroll = await panel.evaluate((el) => el.scrollHeight > el.clientHeight + 80);
    expect(canScroll, "mock 长文应在正文容器内产生可滚动高度").toBeTruthy();

    const st0 = await panel.evaluate((el) => el.scrollTop);
    await page.mouse.move(960, 420);
    await page.mouse.wheel(0, 900);

    await expect
      .poll(async () => panel.evaluate((el) => el.scrollTop), {
        timeout: 8000,
        message: "在右侧正文区域滚轮后正文容器 scrollTop 应增加",
      })
      .toBeGreaterThan(st0 + 40);
  });

  test("大屏：正文列偏左（非侧栏）滚轮仍能滚动正文容器", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/resources/7");
    await expect(page.getByRole("heading", { name: /Mock 文章 #7/u })).toBeVisible({ timeout: 60_000 });

    const panel = page.getByTestId("resource-detail-article");
    await panel.evaluate((el) => {
      el.scrollTop = 0;
    });
    const st0 = await panel.evaluate((el) => el.scrollTop);

    await page.mouse.move(520, 420);
    await page.mouse.wheel(0, 700);

    await expect
      .poll(async () => panel.evaluate((el) => el.scrollTop), {
        timeout: 8000,
        message: "正文列偏左滚轮后正文容器 scrollTop 应增加",
      })
      .toBeGreaterThan(st0 + 30);
  });
});
