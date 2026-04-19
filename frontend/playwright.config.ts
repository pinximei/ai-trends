import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "public",
      testMatch: /public.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5172",
      },
    },
    {
      name: "admin",
      testMatch: /admin.*\.spec\.ts/,
      use: {
        ...devices["Desktop Chrome"],
        baseURL: "http://127.0.0.1:5174",
      },
    },
  ],
  webServer: [
    {
      command: "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
      cwd: path.join(repoRoot, "backend"),
      url: "http://127.0.0.1:8000/api/public/v1/health",
      env: {
        ...process.env,
        AISOU_SKIP_API_SIGNATURE: "1",
        AISOU_ENV: "dev",
      },
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5172",
      cwd: __dirname,
      url: "http://127.0.0.1:5172",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5174",
      cwd: path.join(repoRoot, "frontend", "admin"),
      url: "http://127.0.0.1:5174",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
