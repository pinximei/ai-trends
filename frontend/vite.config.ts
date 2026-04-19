import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  appType: "spa",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5172,
    proxy: {
      // 与 uvicorn --port 一致（Windows 上 8000 常被保留时可改用 8080）
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
      "/internal": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
});
