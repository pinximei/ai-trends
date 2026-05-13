import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Box, ChevronRight } from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { useI18n } from "@/i18n";
import { FeedSidebar } from "@/components/FeedSidebar";

const INDUSTRY = "ai";

function summarize(text: string, max: number) {
  const s = (text || "").trim();
  if (!s) return "—";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

export function HomePage() {
  const { t } = useI18n();
  const [news, setNews] = useState<ArticleFeedCard[]>([]);
  const [apps, setApps] = useState<ArticleFeedCard[]>([]);
  const [catNews, setCatNews] = useState<Array<{ label: string; count: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      publicApi.articlesFeed({
        feed: "news",
        industry_slug: INDUSTRY,
        page_size: 8,
        published_within_days: 30,
      }),
      publicApi.articlesFeed({
        feed: "apps",
        industry_slug: INDUSTRY,
        page_size: 8,
        published_within_days: 30,
      }),
      publicApi.articleCategories({ feed: "news", industry_slug: INDUSTRY, published_within_days: 30 }),
    ])
      .then(([n, a, cn]) => {
        if (cancelled) return;
        setNews(n.items ?? []);
        setApps(a.items ?? []);
        setCatNews(cn);
      })
      .catch(() => {
        if (!cancelled) {
          setNews([]);
          setApps([]);
          setCatNews([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="grid gap-8 xl:grid-cols-[1fr_300px] xl:items-start xl:gap-10">
      <div className="min-w-0 space-y-10">
        <section className="ui-card overflow-hidden">
          <div className="grid gap-8 p-6 lg:grid-cols-2 lg:gap-10 lg:p-10">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-brand-600">{t("homeHeroKicker")}</p>
              <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">
                {t("homeHeroTitle")}
              </h1>
              <p className="mt-4 max-w-xl text-sm leading-relaxed text-slate-600 sm:text-base">{t("homeHeroDesc")}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/apps" className="btn-accent inline-flex items-center gap-2 px-5 py-2.5 text-sm">
                  {t("homeHeroCtaApps")}
                  <ArrowRight className="h-4 w-4" strokeWidth={2} />
                </Link>
                <Link
                  to="/news"
                  className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-600"
                >
                  {t("homeHeroCtaNews")}
                  <ChevronRight className="h-4 w-4 text-slate-400" strokeWidth={2} />
                </Link>
              </div>
            </div>
            <div className="flex min-h-[200px] flex-col justify-center">
              {!loading && catNews.length > 0 ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4">
                  <p className="text-xs font-medium text-slate-500">{t("homeCategorySnapshot")}</p>
                  <ul className="mt-3 space-y-2">
                    {catNews.slice(0, 6).map((row) => (
                      <li key={row.label} className="flex items-center justify-between gap-3 text-sm">
                        <span className="min-w-0 truncate text-slate-800">{row.label}</span>
                        <span className="shrink-0 tabular-nums text-slate-500">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : !loading ? (
                <p className="text-sm text-slate-500">{t("homeCategoryEmpty")}</p>
              ) : (
                <p className="text-sm text-slate-500">{t("homeLoading")}</p>
              )}
            </div>
          </div>
        </section>

        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-900">{t("homeSectionNews")}</h2>
            <Link to="/news" className="text-sm font-medium text-brand-600 hover:underline">
              {t("homeViewAll")}
            </Link>
          </div>
          {loading ? (
            <p className="mt-6 text-sm text-slate-500">{t("homeLoading")}</p>
          ) : news.length === 0 ? (
            <p className="mt-6 text-sm text-slate-500">{t("homeEmpty")}</p>
          ) : (
            <ul className="ui-card mt-4 divide-y divide-slate-100">
              {news.map((item) => (
                <li key={item.id}>
                  <Link
                    to={`/resources/${item.id}`}
                    className="group flex items-start gap-4 px-4 py-4 transition hover:bg-slate-50 sm:px-5"
                  >
                    <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-slate-100 text-brand-600 ring-1 ring-slate-200/80">
                      <Box className="h-5 w-5" strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                        <span className="font-mono font-semibold uppercase tracking-wide text-emerald-700">
                          {item.platform_label || t("source")}
                        </span>
                        {item.published_at ? (
                          <span className="tabular-nums text-slate-400">{item.published_at.slice(0, 10)}</span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[15px] font-semibold leading-snug text-slate-900">{item.title}</p>
                      <p className="mt-1 line-clamp-2 text-sm text-slate-600">{summarize(item.summary, 120)}</p>
                    </div>
                    <ChevronRight className="mt-2 h-5 w-5 shrink-0 text-slate-300 transition group-hover:text-brand-600" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 className="text-lg font-bold text-slate-900">{t("homeSectionApps")}</h2>
            <Link to="/apps" className="text-sm font-medium text-brand-600 hover:underline">
              {t("homeViewAll")}
            </Link>
          </div>
          {!loading && apps.length > 0 ? (
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {apps.map((item) => (
                <Link
                  key={item.id}
                  to={`/resources/${item.id}`}
                  className="ui-card flex gap-3 p-4 transition-colors hover:border-brand-200"
                >
                  <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-brand-50 text-lg font-semibold text-brand-600 ring-1 ring-brand-100">
                    {(item.title || "?").slice(0, 1)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
                    <p className="mt-1 text-xs text-slate-500">
                      {item.categories?.[0] ?? item.platform_label ?? "—"}
                    </p>
                    {item.published_at ? (
                      <p className="mt-2 text-xs tabular-nums text-slate-400">{item.published_at.slice(0, 10)}</p>
                    ) : null}
                  </div>
                </Link>
              ))}
            </div>
          ) : !loading && apps.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">{t("homeEmpty")}</p>
          ) : null}
        </section>
      </div>

      <aside className="min-w-0 xl:sticky xl:top-24">
        <FeedSidebar mode="news" listLen={news.length} categoryOptions={catNews} />
      </aside>
    </div>
  );
}
