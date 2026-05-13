import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Crown, Download, Home, Info, LayoutGrid, Newspaper, Search } from "lucide-react";
import { useI18n } from "@/i18n";
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

const topNav = [
  { to: "/", key: "navHome", icon: Home },
  { to: "/apps", key: "navApps", icon: LayoutGrid },
  { to: "/news", key: "navNews", icon: Newspaper },
  { to: "/downloads", key: "navDownloads", icon: Download },
  { to: "/about", key: "navAbout", icon: Info },
] as const;

const sideNav = [
  { to: "/", key: "navHome" },
  { to: "/apps", key: "navApps" },
  { to: "/news", key: "navNews" },
  { to: "/downloads", key: "navDownloads" },
  { to: "/about", key: "navAbout" },
] as const;

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
  const navigate = useNavigate();
  const isHome = location.pathname === "/";
  const hideSidebar = isHome;
  const hideFloatingNewsletter = isHome;
  const uiRelease = import.meta.env.VITE_APP_RELEASE || "—";
  const [apiRelease, setApiRelease] = useState<string | null>(null);
  const [headerQ, setHeaderQ] = useState("");

  useEffect(() => {
    let cancelled = false;
    void fetchBackendRelease().then((v) => {
      if (!cancelled) setApiRelease(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    const q = headerQ.trim();
    navigate("/news", q ? { state: { q } } : undefined);
  };

  const shell = contentShellClass(isHome);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-slate-200/90 bg-white/95 shadow-sm backdrop-blur-md">
        <div className={`flex flex-wrap items-center gap-3 py-3 lg:gap-6 ${shell}`}>
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 text-sm font-black tracking-tight text-white shadow-md ring-2 ring-violet-200/60">
              AI
            </span>
            <div className="leading-tight">
              <div className="text-[15px] font-bold tracking-tight text-slate-900">{t("brand")}</div>
              <div className="text-[11px] text-slate-500">{t("tagline")}</div>
            </div>
          </Link>

          <nav className="order-3 flex w-full flex-wrap items-center justify-center gap-0.5 border-t border-slate-100 pt-3 md:order-none md:flex-1 md:border-0 md:pt-0">
            {topNav.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => {
                    const base =
                      "relative flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition-colors active:scale-[0.99]";
                    return isActive
                      ? `${base} font-semibold text-violet-700 after:absolute after:bottom-1 after:left-3 after:right-3 after:h-0.5 after:rounded-full after:bg-violet-600`
                      : `${base} text-slate-600 hover:bg-slate-50 hover:text-slate-900`;
                  }}
                >
                  <Icon className="h-4 w-4 shrink-0 opacity-90" strokeWidth={2} />
                  <span>{t(item.key)}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="ml-auto flex min-w-0 flex-1 items-center justify-end gap-2 md:max-w-sm md:flex-none">
            <form onSubmit={onSearch} className="relative min-w-0 flex-1 md:w-56 md:flex-none lg:w-64">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={headerQ}
                onChange={(e) => setHeaderQ(e.target.value)}
                placeholder={t("headerSearchPlaceholder")}
                className="w-full rounded-full border border-slate-200 bg-slate-50 py-2 pl-10 pr-3 text-sm text-slate-800 outline-none ring-violet-500/15 placeholder:text-slate-400 focus:border-violet-300 focus:bg-white focus:ring-2"
                aria-label={t("headerSearchPlaceholder")}
              />
            </form>
            <button
              type="button"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-amber-200/80 bg-gradient-to-b from-amber-50 to-amber-100 text-amber-600 shadow-sm transition hover:brightness-105"
              title="会员"
              aria-label="会员"
            >
              <Crown className="h-5 w-5" strokeWidth={1.75} />
            </button>
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
            <p className="mt-1 text-[10px] text-slate-400">{t("footerIcpNote")}</p>
            <p className="mt-1 text-[10px] text-slate-400">
              构建 {uiRelease}
              {apiRelease ? ` · 接口 ${apiRelease}` : ""}
            </p>
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
