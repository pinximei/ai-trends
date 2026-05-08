import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(path.resolve(__dirname, "package.json"), "utf-8")) as { version?: string };
const gitShort =
  (process.env.VITE_GIT_SHA || process.env.GITHUB_SHA || "").trim().slice(0, 7) || "local";
const appRelease = `${pkg.version ?? "0.0.0"}+${gitShort}`;

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
      // 与 uvicorn --port 一致（Windows 上 8000 常被保留时可改用 8080）
      "/api": { target: "http://127.0.0.1:8080", changeOrigin: true },
      "/internal": { target: "http://127.0.0.1:8080", changeOrigin: true },
    },
  },
});
