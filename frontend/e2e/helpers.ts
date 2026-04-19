import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

export async function expectApiEnvelope(page: Page, path: string): Promise<{ code: number; data: unknown }> {
  const j = await page.evaluate(async (p) => {
    const r = await fetch(p);
    return r.json() as Promise<{ code: number; data: unknown }>;
  }, path);
  expect(j.code).toBe(0);
  return j;
}

export async function loginAdmin(page: Page): Promise<void> {
  await page.goto("/");
  const loginWait = page.waitForResponse(
    (r) => r.url().includes("/api/admin/v1/auth/login") && r.request().method() === "POST" && r.status() === 200
  );
  await page.getByPlaceholder("请输入用户名").fill("admin");
  await page.getByPlaceholder("请输入密码").fill("admin123456");
  await page.getByRole("button", { name: "登录" }).click();
  const res = await loginWait;
  expect(((await res.json()) as { code?: number }).code).toBe(0);
  await expect(page.getByRole("heading", { name: "后台管理中心" })).toBeVisible({ timeout: 20_000 });
}
