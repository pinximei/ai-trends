import { FormEvent, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { Download, Home, Info, LayoutGrid, Newspaper, Search, Sparkles } from "lucide-react";
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

export function Layout() {
  const { t } = useI18n();
  const navigate = useNavigate();
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

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-slate-200/90 bg-white/95 shadow-sm backdrop-blur-md">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-3 lg:gap-4 lg:px-8">
          <Link to="/" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-md bg-brand-500 text-white shadow-sm">
              <Sparkles className="h-5 w-5" strokeWidth={2} />
            </span>
            <div className="leading-tight">
              <div className="text-[15px] font-bold tracking-tight text-slate-900">{t("brand")}</div>
              <div className="text-[11px] text-slate-500">{t("tagline")}</div>
            </div>
          </Link>

          <nav className="order-3 flex w-full flex-wrap items-center gap-1 border-t border-slate-100 pt-3 lg:order-none lg:w-auto lg:border-0 lg:pt-0">
            {topNav.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) => {
                    const base =
                      "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors active:scale-[0.99]";
                    return isActive
                      ? `${base} bg-brand-500 text-white shadow-sm`
                      : `${base} text-slate-600 hover:bg-slate-100 hover:text-slate-900`;
                  }}
                >
                  <Icon className="h-4 w-4 opacity-90" strokeWidth={2} />
                  <span>{t(item.key)}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="ml-auto flex min-w-0 flex-1 items-center justify-end sm:max-w-md lg:max-w-sm">
            <form onSubmit={onSearch} className="relative min-w-0 w-full">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={headerQ}
                onChange={(e) => setHeaderQ(e.target.value)}
                placeholder={t("headerSearchPlaceholder")}
                className="w-full rounded-md border border-slate-200 bg-white py-2 pl-10 pr-3 text-sm text-slate-800 outline-none ring-brand-500/15 placeholder:text-slate-400 focus:border-brand-400 focus:ring-2"
                aria-label={t("headerSearchPlaceholder")}
              />
            </form>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-[1600px] flex-1">
        <aside className="hidden w-56 shrink-0 border-r border-slate-200/80 bg-white/80 lg:block">
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
                    ? `${base} bg-brand-50 text-brand-700 font-medium`
                    : `${base} text-slate-600 hover:bg-slate-50 hover:text-slate-900`;
                }}
              >
                {t(item.key)}
              </NavLink>
            ))}
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 py-6 pb-24 sm:px-6 lg:px-10 lg:py-8">
          <Outlet />
        </main>
      </div>

      <footer className="border-t border-slate-200/80 bg-white/90 py-8 text-center text-[11px] text-slate-500">
        <p className="font-medium text-slate-600">{t("footer")}</p>
        <p className="mt-2 text-[10px] text-slate-400">
          构建 {uiRelease}
          {apiRelease ? ` · 接口 ${apiRelease}` : ""}
        </p>
        <Link to="/about" className="mt-2 inline-block text-brand-600 hover:underline">
          {t("navAbout")} · {t("footerAboutFull")}
        </Link>
      </footer>
      <NewsletterBar />
    </div>
  );
}
