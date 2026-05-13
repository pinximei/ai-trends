import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useI18n } from "@/i18n";
import { TOP_NAV_ITEMS } from "@/navConfig";
import { NewsletterBar } from "./NewsletterBar";

function apiBasePrefix(): string {
  return (import.meta.env.VITE_API_BASE || "").trim().replace(/\/$/, "");
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

const sideNav = TOP_NAV_ITEMS.map(({ to, key }) => ({ to, key }));

/** 首页：随屏宽加宽内容区；其它页保持 1200px 阅读宽 */
function contentShellClass(isHome: boolean): string {
  if (isHome) {
    return "mx-auto w-full max-w-[min(1920px,100%)] px-4 sm:px-6 lg:px-10 xl:px-14 2xl:px-20";
  }
  return "mx-auto w-full max-w-[1200px] px-4 lg:px-8";
}

export function Layout() {
  const { t } = useI18n();
  const location = useLocation();
  const isHome = location.pathname === "/";
  const hideSidebar = isHome;
  const hideFloatingNewsletter = isHome;
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

  const shell = contentShellClass(isHome);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-slate-200/70 bg-white/92 shadow-[0_1px_0_rgba(15,23,42,0.04)] backdrop-blur-xl">
        <div className={`relative flex flex-col gap-3 py-3.5 sm:gap-3.5 md:flex-row md:items-center md:justify-between ${shell}`}>
          <Link to="/" className="flex shrink-0 items-center gap-3 transition-opacity hover:opacity-95">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-600 text-sm font-black tracking-tight text-white shadow-lg shadow-violet-500/20 ring-2 ring-white">
              AI
            </span>
            <div className="leading-tight">
              <div className="text-base font-bold tracking-tight text-slate-900">{t("brand")}</div>
              <div className="text-[11px] font-medium text-slate-500">{t("tagline")}</div>
            </div>
          </Link>

          <nav className="order-last flex w-full flex-wrap items-center justify-center gap-1 md:absolute md:left-1/2 md:top-1/2 md:order-none md:w-auto md:max-w-[min(720px,72vw)] md:-translate-x-1/2 md:-translate-y-1/2 md:flex-nowrap md:justify-center">
            {TOP_NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => {
                    const base =
                      "flex items-center gap-2 whitespace-nowrap rounded-full px-3.5 py-2 text-[13px] font-medium tracking-wide transition-all duration-200 active:scale-[0.98] sm:px-4 sm:text-sm md:px-5 md:text-[15px]";
                    return isActive
                      ? `${base} bg-gradient-to-r from-violet-600 to-indigo-600 font-semibold text-white shadow-md shadow-violet-500/25 ring-1 ring-white/25`
                      : `${base} text-slate-600 hover:bg-slate-100/90 hover:text-slate-900`;
                  }}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0 opacity-85 md:h-4 md:w-4" strokeWidth={2} />
                  <span>{t(item.key)}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="order-1 flex w-full min-w-0 shrink-0 items-center justify-center md:order-none md:w-auto md:max-w-[14rem] md:justify-end">
            <span
              className="max-w-full truncate rounded-lg border border-violet-200/90 bg-violet-50/90 px-2.5 py-1.5 text-[10px] font-semibold leading-none text-violet-800 shadow-sm tabular-nums ring-1 ring-white/80"
              title="前端构建版本（部署后看此处是否变化）"
            >
              UI {uiRelease}
            </span>
          </div>
        </div>
      </header>

      <div className={`flex flex-1 ${shell} ${isHome ? "" : "gap-6 lg:gap-8"}`}>
        {!hideSidebar ? (
          <aside className="hidden w-52 shrink-0 border-r border-slate-200/80 bg-white/80 lg:block">
            <div className="sticky top-[4.75rem] space-y-1 px-3 py-6">
              <p className="px-3 pb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">{t("sidebarNavTitle")}</p>
              {sideNav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => {
                    const base = "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors";
                    return isActive
                      ? `${base} bg-violet-50 text-violet-800 font-medium`
                      : `${base} text-slate-600 hover:bg-slate-50 hover:text-slate-900`;
                  }}
                >
                  {t(item.key)}
                </NavLink>
              ))}
            </div>
          </aside>
        ) : null}

        <main
          className={
            isHome
              ? "min-w-0 flex-1 py-6 pb-28 sm:py-8 xl:py-10"
              : "min-w-0 flex-1 px-4 py-6 pb-28 sm:px-6 lg:px-8 lg:py-8"
          }
        >
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-slate-200/80 bg-slate-50/90">
        <div
          className={`flex flex-col items-center gap-4 py-8 text-center text-[11px] text-slate-500 md:flex-row md:items-start md:justify-between md:text-left ${shell}`}
        >
          <div className="max-w-xl">
            <p className="font-medium text-slate-600">{t("footer")}</p>
            <p className="mt-1 text-[10px] text-slate-500">
              <span className="font-semibold text-slate-600">UI 版本</span> {uiRelease}
              {apiRelease ? ` · 接口 ${apiRelease}` : ""}
            </p>
            <p className="mt-1 text-[10px] text-slate-400">{t("footerIcpNote")}</p>
          </div>
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 text-slate-600 md:justify-end">
            <Link to="/about" className="hover:text-violet-600 hover:underline">
              {t("footerPrivacy")}
            </Link>
            <Link to="/about" className="hover:text-violet-600 hover:underline">
              {t("footerTerms")}
            </Link>
            <Link to="/about" className="hover:text-violet-600 hover:underline">
              {t("footerContact")}
            </Link>
            <Link to="/about" className="hover:text-violet-600 hover:underline">
              {t("navAbout")}
            </Link>
          </div>
        </div>
      </footer>
      {!hideFloatingNewsletter ? <NewsletterBar /> : null}
    </div>
  );
}
