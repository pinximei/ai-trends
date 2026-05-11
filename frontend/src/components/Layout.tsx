import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Cpu, Sparkles, Sun } from "lucide-react";
import { useI18n } from "@/i18n";
import { Aurora } from "./Aurora";
import { TechAtmosphere } from "./TechAtmosphere";
import { NewsletterBar } from "./NewsletterBar";

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
    <div className="relative min-h-screen pb-28">
      <TechAtmosphere />
      <Aurora />
      <div className="relative z-[60] flex items-center justify-between border-b border-violet-200/40 bg-white/75 px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest text-violet-600/90 backdrop-blur-md sm:px-6">
        <span className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-50" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          {t("brand")} · {t("uplink")}
        </span>
        <span className="flex max-w-[62%] flex-wrap items-center justify-end gap-x-3 gap-y-1 sm:max-w-none">
          <span className="hidden items-center gap-1 text-sky-600/90 sm:flex">
            <Cpu className="h-3 w-3" /> link
          </span>
          <span
            className="max-w-full truncate normal-case tracking-normal text-slate-500 max-sm:text-[9px]"
            title={`UI ${uiRelease} · API ${apiRelease ?? "…"}`}
          >
            build <span className="text-violet-600">{uiRelease}</span>
            {apiRelease ? (
              <>
                {" "}
                · api <span className="text-sky-600">{apiRelease}</span>
              </>
            ) : (
              <span className="text-slate-400"> · api …</span>
            )}
          </span>
          <span className="text-slate-500 normal-case tracking-normal max-sm:text-[9px]">
            {new Date().toISOString().slice(0, 10)} UTC
          </span>
        </span>
      </div>
      <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/80 shadow-sm backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link to="/apps" className="group flex items-center gap-3">
            <motion.span
              className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 via-indigo-500 to-sky-400 text-lg shadow-lg shadow-violet-400/30 ring-1 ring-white/60"
              whileHover={{ rotate: [0, -6, 6, 0], scale: 1.04 }}
              transition={{ duration: 0.45 }}
            >
              <Sparkles className="relative h-5 w-5 text-white" />
            </motion.span>
            <div>
              <div className="font-semibold tracking-tight text-slate-900">{t("brand")}</div>
              <div className="text-xs text-slate-500">{t("tagline")}</div>
            </div>
          </Link>
          <nav className="flex flex-wrap items-center gap-1.5">
            {nav.map((item) => {
              const onResourceDetail = loc.pathname.startsWith("/resources/");
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) => {
                    const active = isActive || (item.to === "/apps" && onResourceDetail);
                    const base = "rounded-full px-4 py-2 text-sm font-medium transition-all active:scale-[0.98]";
                    return active
                      ? `${base} bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-md shadow-violet-500/25`
                      : `${base} text-slate-600 hover:bg-slate-100 hover:text-slate-900`;
                  }}
                >
                  {t(item.key)}
                </NavLink>
              );
            })}
          </nav>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-full border border-slate-200 bg-slate-50/90 p-1">
              <button
                type="button"
                onClick={() => setLang("zh")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                  lang === "zh" ? "bg-white text-violet-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                中文
              </button>
              <button
                type="button"
                onClick={() => setLang("en")}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-all ${
                  lang === "en" ? "bg-white text-violet-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                EN
              </button>
            </div>
            <button
              type="button"
              className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-amber-500 shadow-sm"
              title={t("themeLightHint")}
              aria-label={t("themeLightHint")}
            >
              <Sun className="h-5 w-5" strokeWidth={2} />
            </button>
          </div>
        </div>
      </header>
      <main className="relative z-10 mx-auto min-h-[calc(100vh-8rem)] w-full max-w-[1600px] px-4 py-8 sm:px-8 lg:px-12">
        <Outlet />
      </main>
      <footer className="relative z-10 border-t border-slate-200/80 bg-white/60 py-8 text-center text-[11px] text-slate-500 backdrop-blur-sm">
        <p className="font-medium text-slate-600">{t("footer")}</p>
        <p className="mt-2 text-[10px] text-slate-400">
          {lang === "zh" ? "版本" : "Release"}: UI {uiRelease}
          {apiRelease ? ` · API ${apiRelease}` : ""}
        </p>
        <Link to="/about" className="mt-2 inline-block text-violet-600 hover:underline">
          {t("navAbout")} · {t("footerAboutFull")}
        </Link>
      </footer>
      <NewsletterBar />
    </div>
  );
}
