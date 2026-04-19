import { expect, test } from "@playwright/test";

async function expectEnvelopeOk(res: { ok(): boolean; json: () => Promise<unknown> }) {
  expect(res.ok()).toBeTruthy();
  const j = (await res.json()) as { code?: number; data?: unknown };
  expect(j.code).toBe(0);
  return j;
}

test.describe("公开站 · 接口与交互", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("lang", "zh");
    });
  });

  test("根路径重定向到趋势；热门快照 API 与页面文案", async ({ page, request }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/trends$/);
    const hotApi = await request.get("http://127.0.0.1:8000/api/public/v1/hot/current");
    await expectEnvelopeOk(hotApi);
    await expect(page.locator("main")).toContainText("趋势", { timeout: 30_000 });
    await expect(page.getByText(/热门快照/u)).toBeVisible({ timeout: 30_000 });
  });

  test("趋势：摘要与多序列 API 正常；切换时间范围触发新请求", async ({ page, request }) => {
    const sumApi = await request.get("http://127.0.0.1:8000/api/public/v1/trends/summary?days=30");
    await expectEnvelopeOk(sumApi);
    await page.goto("/trends");
    await expect(page.locator("main")).toContainText("趋势", { timeout: 30_000 });

    const s2p = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/trends/series") && r.url().includes("days=7") && r.status() === 200
    );
    await page.getByRole("button", { name: /7\s*天/u }).click();
    const s2 = await s2p;
    const j2 = await expectEnvelopeOk(s2);
    expect(((j2.data as { points?: unknown[] })?.points ?? []).length).toBeGreaterThanOrEqual(0);
  });

  test("资源：列表 API 有文章；进入详情文章 API 正常", async ({ page }) => {
    const art = page.waitForResponse((r) => r.url().includes("/api/public/v1/articles") && !r.url().match(/articles\/\d+/) && r.status() === 200);
    await page.goto("/resources");
    const listRes = await art;
    const listBody = await expectEnvelopeOk(listRes);
    const items = (listBody.data as { items?: { id: number; title: string }[] })?.items ?? [];
    expect(items.length).toBeGreaterThan(0);
    const firstId = items[0].id;

    const detail = page.waitForResponse((r) => r.url().includes(`/api/public/v1/articles/${firstId}`) && r.status() === 200);
    await page.getByRole("link", { name: items[0].title }).first().click();
    const detailRes = await detail;
    const detailBody = await expectEnvelopeOk(detailRes);
    expect((detailBody.data as { title?: string })?.title).toBeTruthy();
    await expect(page.getByRole("heading", { name: items[0].title })).toBeVisible();
  });

  test("关于：CMS 页面 API code=0，正文可见", async ({ page }) => {
    const pg = page.waitForResponse((r) => r.url().includes("/api/public/v1/pages/about") && r.status() === 200);
    await page.goto("/about");
    await expectEnvelopeOk(await pg);
    await expect(page.getByText(/网站介绍|AISoul|免责/u).first()).toBeVisible({ timeout: 15_000 });
  });

  test("顶栏导航切换不报错", async ({ page }) => {
    await page.goto("/trends");
    await page.locator("header").getByRole("link", { name: /资源|Resources/u }).click();
    await expect(page).toHaveURL(/\/resources$/);
    await page.locator("header").getByRole("link", { name: /关于|About/u }).click();
    await expect(page).toHaveURL(/\/about$/);
    await page.locator("header nav").getByRole("link", { name: /趋势|Trends/u }).click();
    await expect(page).toHaveURL(/\/trends$/);
  });
});
