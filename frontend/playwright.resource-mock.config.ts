import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * 仅测文章详情 + 内置 mock：只起 Vite（--mode mock），不依赖 Python/uvicorn。
 * 运行：npm run test:e2e:resource-mock
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /resource-detail-scroll-self\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev:mock -- --host 127.0.0.1 --port 5173",
    cwd: __dirname,
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
