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

  test("根路径为首页；feed API code=0", async ({ page, request }) => {
    await page.goto("/");
    expect(new URL(page.url()).pathname).toBe("/");
    const feedApi = await request.get("http://127.0.0.1:8000/api/public/v1/articles/feed?feed=apps&page_size=5");
    await expectEnvelopeOk(feedApi);
    await expect(page.getByTestId("hero-graphic")).toBeVisible({ timeout: 30_000 });
  });

  test("应用页：feed 有数据时可进详情", async ({ page, request }) => {
    const listBody = await expectEnvelopeOk(
      await request.get("http://127.0.0.1:8000/api/public/v1/articles/feed?feed=apps&page_size=10&published_within_days=3650")
    );
    const items = (listBody.data as { items?: { id: number; title: string }[] })?.items ?? [];
    if (items.length === 0) {
      test.skip();
      return;
    }
    const w = page.waitForResponse(
      (r) => r.url().includes("/api/public/v1/articles/feed") && r.status() === 200
    );
    await page.goto("/apps");
    await w;
    const firstId = items[0].id;
    const detail = page.waitForResponse((r) => r.url().includes(`/api/public/v1/articles/${firstId}`) && r.status() === 200);
    await page.getByRole("link", { name: items[0].title }).first().click();
    const detailBody = await expectEnvelopeOk(await detail);
    expect((detailBody.data as { title?: string })?.title).toBeTruthy();
    await expect(page.getByRole("heading", { name: items[0].title })).toBeVisible();
  });

  test("关于：CMS 页面 API code=0，正文可见", async ({ page }) => {
    const pg = page.waitForResponse((r) => r.url().includes("/api/public/v1/pages/about") && r.status() === 200);
    await page.goto("/about");
    await expectEnvelopeOk(await pg);
    await expect(page.getByText(/网站介绍|AiTrends|免责/u).first()).toBeVisible({ timeout: 15_000 });
  });

  test("顶栏导航切换不报错", async ({ page }) => {
    await page.goto("/apps");
    await page.locator("header").getByRole("link", { name: /资讯|news/u }).click();
    await expect(page).toHaveURL(/\/news$/);
    await page.locator("header").getByRole("link", { name: /软件下载|Downloads/u }).click();
    await expect(page).toHaveURL(/\/downloads$/);
    await page.locator("header").getByRole("link", { name: /关于|About/u }).click();
    await expect(page).toHaveURL(/\/about$/);
    await page.locator("header nav").getByRole("link", { name: /应用|apps/u }).click();
    await expect(page).toHaveURL(/\/apps$/);
  });

  test("首页主视觉：轨道图标在光晕之上（命中测试）", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    const hero = page.getByTestId("hero-graphic");
    await expect(hero).toBeVisible();
    const homeIcon = hero.locator("svg.lucide-home").first();
    await expect(homeIcon).toBeVisible();
    const ok = await hero.evaluate((root) => {
      const svg = root.querySelector("svg.lucide-home");
      if (!svg) return { ok: false as const, reason: "no home nav svg in hero" };
      const r = svg.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const hits = document.elementsFromPoint(cx, cy);
      const firstInHero = hits.find((el) => root.contains(el));
      if (!firstInHero) return { ok: false as const, reason: "no element in hero at point", cx, cy };
      const onOrbitChip =
        firstInHero === svg || firstInHero.contains(svg) || (svg instanceof Element && svg.contains(firstInHero));
      const isGlowOnly =
        firstInHero.getAttribute("aria-hidden") === "true" &&
        typeof (firstInHero as HTMLElement).className === "string" &&
        /blur|shadow|inset|radial-gradient|mask-image/.test((firstInHero as HTMLElement).className);
      return { ok: onOrbitChip && !isGlowOnly, firstTag: firstInHero.tagName, cx, cy };
    });
    expect(ok.ok, JSON.stringify(ok)).toBe(true);
  });
});
