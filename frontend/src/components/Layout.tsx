import { motion } from "framer-motion";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Activity, Cpu, Sparkles } from "lucide-react";
import { useI18n } from "@/i18n";
import { Aurora } from "./Aurora";
import { TechAtmosphere } from "./TechAtmosphere";

const nav = [
  { to: "/trends", key: "navTrends" },
  { to: "/resources", key: "navResources" },
  { to: "/about", key: "navAbout" },
] as const;

export function Layout() {
  const { t, lang, setLang } = useI18n();
  const loc = useLocation();

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
        <span className="hidden items-center gap-4 sm:flex">
          <span className="flex items-center gap-1 text-fuchsia-400/90">
            <Cpu className="h-3 w-3" /> inference
          </span>
          <span className="flex items-center gap-1 text-amber-400/90">
            <Activity className="h-3 w-3" /> live
          </span>
          <span className="text-slate-500">{new Date().toISOString().slice(0, 10)} UTC</span>
        </span>
      </div>
      <header className="sticky top-0 z-50 border-b border-white/10 bg-night-950/80 shadow-[0_0_40px_rgba(0,0,0,0.5)] backdrop-blur-2xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <Link to="/trends" className="group flex items-center gap-2">
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
              const active = loc.pathname === item.to || loc.pathname.startsWith(`${item.to}/`);
              return (
                <Link key={item.to} to={item.to}>
                  <motion.span
                    className={`rounded-xl px-3 py-2 text-sm font-medium transition-colors ${
                      active
                        ? "bg-gradient-to-r from-cyan-500/25 to-fuchsia-500/20 text-white shadow-[inset_0_0_20px_rgba(34,211,238,0.15)] ring-1 ring-cyan-400/40"
                        : "text-slate-200 hover:text-white"
                    }`}
                    whileTap={{ scale: 0.97 }}
                  >
                    {t(item.key)}
                  </motion.span>
                </Link>
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
        <Link to="/about" className="mt-2 inline-block text-cyan-400/80 hover:underline">
          {t("navAbout")} · 完整说明
        </Link>
      </footer>
    </div>
  );
}
