import path from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "package.json"), "utf-8")) as { version?: string };
const gitShort =
  (process.env.VITE_GIT_SHA || process.env.GITHUB_SHA || "").trim().slice(0, 7) || "local";
const appRelease = `${pkg.version ?? "0.0.0"}+${gitShort}`;

// 生产环境挂在 https://域名/admin/：资源必须带 /admin/ 前缀，否则会请求到公开站的 /assets/。
// 开发仍用 base "/"，便于 http://127.0.0.1:5174/ 本地调试。
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/admin/" : "/",
  appType: "spa",
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_RELEASE": JSON.stringify(appRelease),
  },
  server: {
    port: 5174,
    proxy: {
      // 与 uvicorn --port 一致（与 frontend/vite.config.ts 保持同一后端端口）
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
}));
