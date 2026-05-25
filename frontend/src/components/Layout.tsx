import { useEffect, useState } from "react";
import { Github } from "lucide-react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useI18n } from "@/i18n";
import { TOP_NAV_ITEMS } from "@/navConfig";
import { SITE_GITHUB_REPO_URL } from "@/siteLinks";

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

/** 首页、资讯/工具 feed、软件下载、关于、文章详情：宽版内容区；其它页 1200px */
function contentShellClass(wide: boolean): string {
  if (wide) {
    return "mx-auto w-full max-w-[min(1920px,100%)] px-4 sm:px-6 lg:px-10 xl:px-14 2xl:px-20";
  }
  return "mx-auto w-full max-w-[1200px] px-4 lg:px-8";
}

export function Layout() {
  const { t } = useI18n();
  const location = useLocation();
  const path = location.pathname;
  const isHome = path === "/";
  const isFeedHub = path === "/apps" || path === "/news";
  const isResourceDetail = /^\/resources\/[^/]+$/.test(path);
  /** 资讯/应用 feed 与文章详情：整页高度锁定，左栏固定、右栏独立滚动 */
  const isSplitScrollPage = isResourceDetail || isFeedHub;
  const isWideHub = isHome || isFeedHub || path === "/downloads" || path === "/about" || isResourceDetail;
  const useWideShell = isWideHub;
  const hideSidebar = isWideHub;
  const isHubTightTop = isFeedHub || path === "/downloads" || path === "/about" || isResourceDetail;
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

  const shell = contentShellClass(useWideShell);

  return (
    <div
      className={
        isSplitScrollPage
          ? "flex h-svh max-h-svh min-h-0 flex-col overflow-hidden"
          : "flex min-h-screen flex-col"
      }
    >
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

          <div className="order-1 flex w-full min-w-0 shrink-0 items-center justify-center gap-2 md:order-none md:w-auto md:max-w-[18rem] md:justify-end">
            <a
              href={SITE_GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200/90 bg-white text-slate-600 shadow-sm transition-colors hover:border-violet-200 hover:bg-violet-50 hover:text-violet-700"
              title={t("footerGithub")}
              aria-label={t("footerGithub")}
            >
              <Github className="h-4 w-4" strokeWidth={2} aria-hidden />
            </a>
            <span
              className="max-w-full truncate rounded-lg border border-violet-200/90 bg-violet-50/90 px-2.5 py-1.5 text-[10px] font-semibold leading-none text-violet-800 shadow-sm tabular-nums ring-1 ring-white/80"
              title="前端构建版本（部署后看此处是否变化）"
            >
              UI {uiRelease}
            </span>
          </div>
        </div>
      </header>

      <div
        className={
          isSplitScrollPage
            ? "mx-auto flex min-h-0 min-w-0 w-full max-w-[min(1920px,100%)] flex-1 flex-row px-0"
            : `flex min-h-0 min-w-0 flex-1 flex-row ${shell} ${isWideHub ? "" : "gap-6 lg:gap-8"}`
        }
      >
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
              ? "min-w-0 flex-1 py-6 pb-4 sm:py-8 sm:pb-5 xl:py-10"
              : isSplitScrollPage
                ? "flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-slate-50 pt-2 pb-0 sm:pt-3 lg:bg-[#eef0f4] lg:pt-2"
                : isHubTightTop
                  ? "min-w-0 flex-1 pt-2 pb-4 sm:pt-3 lg:pt-4"
                  : "min-w-0 flex-1 px-4 py-6 pb-4 sm:px-6 lg:px-8 lg:py-8"
          }
        >
          <Outlet />
        </main>
      </div>

      <footer className="shrink-0 border-t border-slate-200/70 bg-white/95">
        <div
          className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-2 text-[10px] leading-snug text-slate-500 sm:py-2.5 ${shell}`}
        >
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="font-medium text-slate-600">{t("footer")}</span>
            <span className="hidden text-slate-300 sm:inline" aria-hidden>
              ·
            </span>
            <span className="tabular-nums text-slate-400">
              UI {uiRelease}
              {apiRelease ? ` · API ${apiRelease}` : ""}
            </span>
            <span className="hidden min-w-0 truncate text-slate-400 md:inline" title={t("footerIcpNote")}>
              · {t("footerIcpNote")}
            </span>
          </div>
          <nav
            className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-0.5 text-slate-600"
            aria-label={t("navAbout")}
          >
            <a
              href={SITE_GITHUB_REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md px-1 py-0.5 font-medium text-slate-700 transition-colors hover:bg-slate-100 hover:text-violet-700"
              title={SITE_GITHUB_REPO_URL}
            >
              <Github className="h-3.5 w-3.5 shrink-0" strokeWidth={2} aria-hidden />
              {t("footerGithub")}
            </a>
            <Link to="/about" className="hover:text-violet-600">
              {t("footerPrivacy")}
            </Link>
            <Link to="/about" className="hover:text-violet-600">
              {t("footerTerms")}
            </Link>
            <Link to="/about" className="hover:text-violet-600">
              {t("footerContact")}
            </Link>
            <Link to="/about" className="hover:text-violet-600">
              {t("navAbout")}
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
