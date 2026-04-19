import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  appType: "spa",
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // 与 uvicorn --port 一致（与 frontend/vite.config.ts 保持同一后端端口）
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
});
