import type { HomeDashboardCachePayload } from "@/lib/homeDashboardCache";

declare global {
  interface Window {
    __AITRENDS_SSR_HOME__?: HomeDashboardCachePayload;
  }
}

const SSR_SCRIPT_ID = "aitrends-ssr-home";

/** 从 SSR 注入的 ``<script type="application/json">`` 读取首页初始数据。 */
export function readSsrHomeBootstrap(): HomeDashboardCachePayload | null {
  if (typeof window === "undefined") return null;
  const fromWin = window.__AITRENDS_SSR_HOME__;
  if (fromWin && Array.isArray(fromWin.news)) {
    return fromWin;
  }
  const el = document.getElementById(SSR_SCRIPT_ID);
  if (!el?.textContent?.trim()) return null;
  try {
    const parsed = JSON.parse(el.textContent) as HomeDashboardCachePayload;
    if (!parsed || !Array.isArray(parsed.news)) return null;
    window.__AITRENDS_SSR_HOME__ = parsed;
    return parsed;
  } catch {
    return null;
  }
}

export function hasSsrHomeMarkup(): boolean {
  if (typeof document === "undefined") return false;
  return Boolean(document.getElementById("ssr-home-fallback") || document.querySelector("[data-ssr='home']"));
}
