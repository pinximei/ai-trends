import { expect, test } from "@playwright/test";
import { loginAdmin } from "./helpers";

test.describe.configure({ mode: "serial" });

/**
 * 管理端串行烟测：总览热门重建 + 数据查询（admin 账号）
 */
test.describe("管理端 · 逐一（串行）", () => {
  test("总览：立即重建热门 → POST /product/hot/rebuild", async ({ page }) => {
    await loginAdmin(page);
    const rebuild = page.waitForResponse(
      (r) => r.url().includes("/api/admin/v1/product/hot/rebuild") && r.request().method() === "POST" && r.status() === 200
    );
    await page.getByRole("button", { name: "立即重建热门" }).click();
    const res = await rebuild;
    const j = (await res.json()) as { code?: number; data?: { snapshot_id?: number } };
    expect(j.code).toBe(0);
    expect(j.data?.snapshot_id).toBeGreaterThan(0);
  });

  test("数据查询：库表元数据 GET /data/tables", async ({ page }) => {
    await loginAdmin(page);
    const dtP = page.waitForResponse((r) => r.url().includes("/api/admin/v1/data/tables") && r.status() === 200);
    await page.getByRole("button", { name: "数据查询" }).click();
    const dtRes = await dtP;
    expect(((await dtRes.json()) as { code?: number }).code).toBe(0);
  });
});
