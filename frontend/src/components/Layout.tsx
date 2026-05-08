import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, Cpu, Sparkles } from "lucide-react";
import { useI18n } from "@/i18n";
import { Aurora } from "./Aurora";
import { TechAtmosphere } from "./TechAtmosphere";

function apiBasePrefix(): string {
  const b = (import.meta.env.VITE_API_BASE || "").trim().replace(/\/$/, "");
  return b;
}

async function fetchBackendRelease(): Promise<string | null> {
  try {
    const url = `${apiBasePrefix()}/api/public/v1/version`;
    const r = await fetch(url);
    const j = (await r.json()) as { code?: number; data?: { release?: string } };
    if (j.code === 0 && j.data?.release) return j.data.release;
  } catch {
    /* ignore */
  }
  return null;
}

const nav = [
  { to: "/apps", key: "navApps" },
  { to: "/news", key: "navNews" },
  { to: "/downloads", key: "navDownloads" },
  { to: "/about", key: "navAbout" },
] as const;

export function Layout() {
  const { t, lang, setLang } = useI18n();
  const loc = useLocation();
  const uiRelease = import.meta.env.VITE_APP_RELEASE || "—";
  const [apiRelease, setApiRelease] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchBackendRelease().then((v) => {
      if (!cancelled) setApiRelease(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="relative min-h-screen">
      <TechAtmosphere />
      <Aurora />
      {/* 顶栏状态条：科技感数据带 */}
      <div className="relative z-[60] flex items-center justify-between border-b border-cyan-500/20 bg-black/40 px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest text-cyan-500/80 sm:px-6">
        <span className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          AISoul · Uplink
        </span>
        <span className="flex max-w-[62%] flex-wrap items-center justify-end gap-x-3 gap-y-1 sm:max-w-none">
          <span className="hidden items-center gap-1 text-fuchsia-400/90 sm:flex">
            <Cpu className="h-3 w-3" /> inference
          </span>
          <span className="hidden items-center gap-1 text-amber-400/90 sm:flex">
            <Activity className="h-3 w-3" /> live
          </span>
          <span
            className="max-w-full truncate normal-case tracking-normal text-slate-500 max-sm:text-[9px]"
            title={`UI ${uiRelease} · API ${apiRelease ?? "…"}`}
          >
            build <span className="text-cyan-600/90">{uiRelease}</span>
            {apiRelease ? (
              <>
                {" "}
                · api <span className="text-fuchsia-400/80">{apiRelease}</span>
              </>
            ) : (
              <span className="text-slate-600"> · api …</span>
            )}
          </span>
          <span className="text-slate-500 normal-case tracking-normal max-sm:text-[9px]">
            {new Date().toISOString().slice(0, 10)} UTC
          </span>
        </span>
      </div>
      <header className="sticky top-0 z-50 border-b border-white/10 bg-night-950/80 shadow-[0_0_40px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link to="/apps" className="group flex items-center gap-2">
            <motion.span
              className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500/30 via-fuchsia-600/30 to-amber-500/25 text-lg shadow-[0_0_24px_rgba(34,211,238,0.25)] ring-1 ring-white/20"
              whileHover={{ rotate: [0, -8, 8, 0], scale: 1.05 }}
              transition={{ duration: 0.5 }}
            >
              <span className="absolute inset-0 animate-glow rounded-2xl opacity-50" />
              <Sparkles className="relative h-5 w-5 text-cyan-100" />
            </motion.span>
            <div>
              <div className="font-semibold tracking-tight text-white">{t("brand")}</div>
              <div className="text-xs text-slate-400">{t("tagline")}</div>
            </div>
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            {nav.map((item) => {
              const onResourceDetail = loc.pathname.startsWith("/resources/");
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => {
                    const active = isActive || (item.to === "/apps" && onResourceDetail);
                    const base =
                      "rounded-xl px-3 py-2 text-sm font-medium transition-colors active:scale-[0.98]";
                    return active
                      ? `${base} bg-gradient-to-r from-cyan-500/25 to-fuchsia-500/20 text-white shadow-[inset_0_0_20px_rgba(34,211,238,0.15)] ring-1 ring-cyan-400/40`
                      : `${base} text-slate-200 hover:text-white`;
                  }}
                >
                  {t(item.key)}
                </NavLink>
              );
            })}
          </nav>
          <div className="flex items-center gap-1 rounded-full border border-white/15 bg-slate-900/80 p-1">
            <button
              type="button"
              onClick={() => setLang("zh")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                lang === "zh" ? "bg-cyan-300 text-slate-900 shadow" : "text-slate-300 hover:text-white"
              }`}
            >
              中文
            </button>
            <button
              type="button"
              onClick={() => setLang("en")}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                lang === "en" ? "bg-cyan-300 text-slate-900 shadow" : "text-slate-300 hover:text-white"
              }`}
            >
              EN
            </button>
          </div>
        </div>
      </header>
      <main className="relative z-10 min-h-[calc(100vh-8rem)] w-full max-w-[1920px] mx-auto px-4 py-8 sm:px-8 lg:px-12">
        <Outlet />
      </main>
      <footer className="border-t border-cyan-500/15 bg-black/20 py-8 text-center font-mono text-[11px] text-slate-300/80">
        <p>{t("footer")}</p>
        <p className="mt-2 text-[10px] text-slate-500">
          {lang === "zh" ? "版本" : "Release"}: UI {uiRelease}
          {apiRelease ? ` · API ${apiRelease}` : ""}
        </p>
        <Link to="/about" className="mt-2 inline-block text-cyan-400/80 hover:underline">
          {t("navAbout")} · 完整说明
        </Link>
      </footer>
    </div>
  );
}
