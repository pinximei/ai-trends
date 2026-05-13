import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "package.json"), "utf-8")) as { version?: string };
const gitShort =
  (process.env.VITE_GIT_SHA || process.env.GITHUB_SHA || "").trim().slice(0, 7) || "local";
/** 本地无 SHA 时带构建时间戳，便于确认是否最新前端包 */
const devStamp = gitShort === "local" ? `t${Date.now().toString(36)}` : "";
const appRelease = [pkg.version ?? "0.0.0", gitShort, devStamp].filter(Boolean).join("+");
/** 本地默认直连宿主机 uvicorn；Docker 用 compose.local 注入 http://api:8000 */
const devProxyTarget = (process.env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/$/, "");

export default defineConfig({
  appType: "spa",
  plugins: [react()],
  define: {
    "import.meta.env.VITE_APP_RELEASE": JSON.stringify(appRelease),
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5172,
    proxy: {
      "/api": { target: devProxyTarget, changeOrigin: true },
      "/internal": { target: devProxyTarget, changeOrigin: true },
    },
  },
});
