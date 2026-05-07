import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 生产环境挂在 https://域名/admin/：资源必须带 /admin/ 前缀，否则会请求到公开站的 /assets/。
// 开发仍用 base "/"，便于 http://127.0.0.1:5174/ 本地调试。
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/admin/" : "/",
  appType: "spa",
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // 与 uvicorn --port 一致（与 frontend/vite.config.ts 保持同一后端端口）
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
}));
