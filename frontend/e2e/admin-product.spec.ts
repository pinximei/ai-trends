import { expect, test } from "@playwright/test";

test.describe("管理端 · 登录与数据查询", () => {
  test("登录后可打开数据查询并拉取库表与板块元数据", async ({ page }) => {
    await page.goto("/");

    const loginWait = page.waitForResponse(
      (r) => r.url().includes("/api/admin/v1/auth/login") && r.request().method() === "POST" && r.status() === 200
    );
    await page.getByPlaceholder("请输入用户名").fill("admin");
    await page.getByPlaceholder("请输入密码").fill("admin123456");
    await page.getByRole("button", { name: "登录" }).click();
    const loginRes = await loginWait;
    const loginJson = (await loginRes.json()) as { code?: number };
    expect(loginJson.code).toBe(0);

    await expect(page.getByRole("heading", { name: "后台管理中心" })).toBeVisible({ timeout: 15_000 });

    const tablesWait = page.waitForResponse((r) => r.url().includes("/api/admin/v1/data/tables") && r.status() === 200);
    const segWait = page.waitForResponse((r) => r.url().includes("/api/admin/v1/product/segments") && r.status() === 200);
    await page.getByRole("button", { name: "数据查询" }).click();
    const tablesRes = await tablesWait;
    expect(((await tablesRes.json()) as { code?: number }).code).toBe(0);
    const segRes = await segWait;
    expect(((await segRes.json()) as { code?: number }).code).toBe(0);

    await expect(page.getByRole("heading", { name: "数据查询" })).toBeVisible();
  });
});
