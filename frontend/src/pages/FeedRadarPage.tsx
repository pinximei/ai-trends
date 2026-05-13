import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Search, Box } from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import type { ArticlesFeedDayResponse } from "@/api/public/types";
import { useI18n } from "@/i18n";
import { FeedSidebar } from "@/components/FeedSidebar";

const INDUSTRY_SLUG = "ai";

type TimeKey = "latest_day" | "all" | "d7" | "d30" | "d90";

const TIME_FILTERS: Array<{ key: TimeKey; labelKey: string }> = [
  { key: "latest_day", labelKey: "resourcesLatestDay" },
  { key: "all", labelKey: "resourcesTimeAll" },
  { key: "d7", labelKey: "resourcesDays7" },
  { key: "d30", labelKey: "resourcesDays30" },
  { key: "d90", labelKey: "resourcesDays90" },
];

function timeKeyToArticleParams(timeKey: TimeKey): {
  published_within_days?: number;
  published_on_latest_day?: boolean;
} {
  if (timeKey === "latest_day") return { published_on_latest_day: true };
  if (timeKey === "all") return {};
  const n = timeKey === "d7" ? 7 : timeKey === "d30" ? 30 : 90;
  return { published_within_days: n };
}

function summarize(text: string, max: number) {
  const t = (text || "").trim();
  if (!t) return "—";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

function formatFeedDateLabel(isoDay: string): string {
  if (!isoDay || isoDay === "_") return "—";
  const d = new Date(`${isoDay}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDay;
  return d.toLocaleDateString("zh-CN", { dateStyle: "long", timeZone: "UTC" });
}

function isDayFeedResponse(d: unknown): d is ArticlesFeedDayResponse {
  return Boolean(d && typeof d === "object" && (d as ArticlesFeedDayResponse).paginate_by === "day");
}

export function FeedRadarPage({ mode }: { mode: "news" | "apps" }) {
  const { t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const [timeKey, setTimeKey] = useState<TimeKey>("latest_day");
  const [feedPage, setFeedPage] = useState(1);
  const [jumpDraft, setJumpDraft] = useState("1");
  const [list, setList] = useState<ArticleFeedCard[]>([]);
  const [pageMeta, setPageMeta] = useState({
    total_pages: 0,
    day_utc: null as string | null,
    has_prev: false,
    has_next: false,
    days_scan_truncated: false,
  });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [categoryKey, setCategoryKey] = useState<string | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<Array<{ label: string; count: number }>>([]);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQ, setSearchQ] = useState("");

  useEffect(() => {
    const raw = location.state as { q?: string } | undefined;
    const q = raw?.q?.trim();
    if (!q) return;
    setSearchDraft(q);
    setSearchQ(q);
    navigate(`${location.pathname}${location.search}`, { replace: true, state: {} });
  }, [location.state, location.pathname, location.search, navigate]);

  const timeParams = useMemo(() => timeKeyToArticleParams(timeKey), [timeKey]);

  useEffect(() => {
    const tm = window.setTimeout(() => setSearchQ(searchDraft.trim()), 350);
    return () => window.clearTimeout(tm);
  }, [searchDraft]);

  const pageTitle = mode === "apps" ? t("resourcesFeedApps") : t("resourcesFeedNews");

  const listByDate = useMemo((): [string, ArticleFeedCard[]][] => {
    const m = new Map<string, ArticleFeedCard[]>();
    for (const a of list) {
      const day = (a.published_at || "").slice(0, 10) || "_";
      if (!m.has(day)) m.set(day, []);
      m.get(day)!.push(a);
    }
    return Array.from(m.entries()).sort((x, y) => (x[0] < y[0] ? 1 : x[0] > y[0] ? -1 : 0));
  }, [list]);

  useEffect(() => {
    setFeedPage(1);
  }, [mode, timeKey, categoryKey, searchQ]);

  useEffect(() => {
    let cancelled = false;
    publicApi
      .articleCategories({ feed: mode, industry_slug: INDUSTRY_SLUG, ...timeParams, q: searchQ || null })
      .then((rows) => {
        if (!cancelled) setCategoryOptions(rows);
      })
      .catch(() => {
        if (!cancelled) setCategoryOptions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, timeParams, searchQ]);

  useEffect(() => {
    if (categoryKey && !categoryOptions.some((x) => x.label === categoryKey)) {
      setCategoryKey(null);
    }
  }, [categoryOptions, categoryKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr("");

    publicApi
      .articlesFeed({
        feed: mode,
        industry_slug: INDUSTRY_SLUG,
        paginate_by: "day",
        page: feedPage,
        ...timeParams,
        category: categoryKey,
        q: searchQ || null,
      })
      .then((d) => {
        if (cancelled) return;
        if (!isDayFeedResponse(d)) {
          setErr("Unexpected feed response");
          setLoading(false);
          return;
        }
        if (d.total_pages > 0 && feedPage > d.total_pages) {
          setFeedPage(d.total_pages);
          return;
        }
        setList(d.items);
        setPageMeta({
          total_pages: d.total_pages,
          day_utc: d.day_utc,
          has_prev: d.has_prev,
          has_next: d.has_next,
          days_scan_truncated: d.days_scan_truncated,
        });
        setJumpDraft(String(Math.min(feedPage, Math.max(1, d.total_pages)) || 1));
        setLoading(false);
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(String(e));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [mode, timeParams, categoryKey, searchQ, feedPage]);

  useEffect(() => {
    if (!loading) {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [feedPage, loading]);

  const onJump = () => {
    const n = Number.parseInt(jumpDraft.trim(), 10);
    if (!Number.isFinite(n) || pageMeta.total_pages < 1) return;
    const clamped = Math.min(Math.max(1, Math.floor(n)), pageMeta.total_pages);
    setFeedPage(clamped);
    setJumpDraft(String(clamped));
  };

  const pageSummaryText =
    pageMeta.total_pages > 0
      ? t("resourcesPageSummary").replace("{page}", String(feedPage)).replace("{total}", String(pageMeta.total_pages))
      : "";

  const filterPanel = (
    <div className="glass-light relative overflow-hidden rounded-lg border-slate-200 p-0 shadow-sm">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-brand-50/50 via-transparent to-slate-50/40" />

      <div className="relative border-b border-slate-100/90 p-5 sm:p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-3xl">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-brand-600/85">
              {mode === "apps" ? t("navApps") : t("navNews")}
            </p>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{pageTitle}</h1>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">{t("resourcesFeedDayHint")}</p>
          </div>
          <div
            className="relative hidden h-[5.25rem] w-[5.25rem] shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-brand-50 shadow-sm sm:flex"
            aria-hidden
          >
            <Box className="h-10 w-10 text-brand-500 opacity-90" strokeWidth={1.25} />
          </div>
        </div>
      </div>

      <div className="relative p-5 sm:p-6 sm:pt-5">
        <div className="rounded-2xl border border-slate-100/90 bg-slate-50/45 p-4 ring-1 ring-slate-100/70 sm:p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <Search className="h-3.5 w-3.5 text-brand-500" strokeWidth={2.5} />
            {t("resourcesSearchLabel")}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-stretch">
            <div className="relative min-w-0 flex-1 sm:max-w-xl">
              <Search className="pointer-events-none absolute bottom-3 left-4 h-4 w-4 text-slate-400" />
              <input
                type="search"
                enterKeyHint="search"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
                placeholder={t("resourcesSearchPlaceholder")}
                className="w-full rounded-full border border-slate-200 bg-white/90 py-3 pl-11 pr-4 text-sm text-slate-800 shadow-inner outline-none ring-brand-400/20 placeholder:text-slate-400 focus:border-brand-300 focus:ring-2"
                aria-label={t("resourcesSearchPlaceholder")}
              />
            </div>
            {searchDraft.trim() ? (
              <button
                type="button"
                onClick={() => {
                  setSearchDraft("");
                  setSearchQ("");
                }}
                className="shrink-0 self-center rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50"
              >
                {t("resourcesSearchClear")}
              </button>
            ) : null}
          </div>
        </div>

        <div className="mt-6 grid gap-5 lg:grid-cols-2 lg:gap-6">
          <div className="flex flex-col rounded-2xl border border-slate-100/90 bg-white/60 p-4 shadow-inner ring-1 ring-slate-50/80 sm:p-4">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t("resourcesTimeFilter")}</span>
            <div className="mt-3 flex flex-wrap gap-2">
              {TIME_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => {
                    setTimeKey(f.key);
                    setCategoryKey(null);
                  }}
                  className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                    timeKey === f.key ? "pill-active shadow-md" : "pill-idle"
                  }`}
                >
                  {t(f.labelKey)}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-col rounded-2xl border border-slate-100/90 bg-white/60 p-4 shadow-inner ring-1 ring-slate-50/80 sm:p-4">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t("resourcesCategoryFilter")}</span>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setCategoryKey(null)}
                className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                  categoryKey == null ? "pill-active shadow-md" : "pill-idle"
                }`}
              >
                {t("resourcesCategoryAll")}
              </button>
              {categoryOptions.map((row) => (
                <button
                  key={row.label}
                  type="button"
                  onClick={() => setCategoryKey(row.label)}
                  className={`rounded-full px-3.5 py-2 text-sm font-medium transition ${
                    categoryKey === row.label ? "pill-active shadow-md" : "pill-idle"
                  }`}
                >
                  {row.label}
                  <span className="ml-1 font-mono text-[10px] text-slate-500/90">({row.count})</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {!loading && pageMeta.total_pages > 0 ? (
          <div className="mt-6 flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-3.5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:px-5">
            <div className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{pageSummaryText}</span>
              {pageMeta.day_utc ? (
                <span className="ml-2 text-slate-500">· 世界时 {formatFeedDateLabel(pageMeta.day_utc)}</span>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={!pageMeta.has_prev || loading}
                onClick={() => setFeedPage((p) => Math.max(1, p - 1))}
                className="rounded-full border border-slate-200/90 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {t("resourcesPagePrev")}
              </button>
              <button
                type="button"
                disabled={!pageMeta.has_next || loading}
                onClick={() => setFeedPage((p) => p + 1)}
                className="rounded-full border border-slate-200/90 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {t("resourcesPageNext")}
              </button>
              <label className="flex items-center gap-2 text-xs text-slate-500">
                <span className="sr-only">{t("resourcesPageJumpPlaceholder")}</span>
                <input
                  type="number"
                  min={1}
                  max={Math.max(1, pageMeta.total_pages)}
                  value={jumpDraft}
                  onChange={(e) => setJumpDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onJump();
                  }}
                  className="w-20 rounded-xl border border-slate-200 bg-white px-2 py-1.5 font-mono text-sm text-slate-800 shadow-inner"
                  aria-label={t("resourcesPageJumpPlaceholder")}
                />
                <button
                  type="button"
                  onClick={() => onJump()}
                  className="rounded-md bg-brand-500 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-brand-400"
                >
                  {t("resourcesPageGo")}
                </button>
              </label>
            </div>
          </div>
        ) : null}

        {pageMeta.days_scan_truncated ? (
          <p className="mt-4 text-xs font-medium text-amber-700">{t("resourcesDaysTruncated")}</p>
        ) : null}
      </div>
    </div>
  );

  const listSection = (
    <>
      {err ? <p className="mt-6 text-sm font-medium text-rose-600">{err}</p> : null}
      {loading ? <p className="mt-8 text-sm text-slate-500">{t("resourcesLoading")}</p> : null}

      {!loading ? (
        <>
          <p className="mt-10 text-center text-[11px] font-medium uppercase tracking-wider text-slate-400">{t("resourcesByDate")}</p>
          <div className="mt-6 space-y-14">
            {listByDate.map(([dayKey, rows]) => (
              <Fragment key={dayKey}>
                <div className="flex items-center gap-4 px-1">
                  <span className="shrink-0 rounded-md border border-slate-200 bg-white px-3 py-1 text-[11px] font-medium uppercase tracking-wide text-slate-600">
                    {formatFeedDateLabel(dayKey)}
                  </span>
                  <span className="h-px flex-1 bg-slate-200" aria-hidden />
                </div>
                <div
                  className={
                    mode === "apps"
                      ? "mt-5 grid gap-5 sm:grid-cols-2 sm:gap-6 lg:grid-cols-3 xl:grid-cols-4"
                      : "mt-5 grid gap-6 sm:grid-cols-2 sm:gap-7"
                  }
                >
                  {rows.map((a) => {
                    const pub = a.published_at ? a.published_at.slice(0, 10) : null;
                    return (
                      <Link
                        key={a.id}
                        to={`/resources/${a.id}`}
                        className={`group relative flex overflow-hidden rounded-lg border border-slate-200 bg-white text-left shadow-sm transition hover:border-brand-300 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/40 focus-visible:ring-offset-2 ${
                          mode === "apps" ? "flex-col sm:flex-row" : "flex-col"
                        }`}
                      >
                        <div
                          className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-brand-500 opacity-0 transition-opacity group-hover:opacity-100"
                          aria-hidden
                        />
                        <div
                          className={
                            mode === "apps"
                              ? "relative flex min-h-0 flex-1 flex-col sm:flex-row"
                              : "relative flex min-h-0 flex-1 flex-col"
                          }
                        >
                          {mode === "apps" ? (
                            <div className="flex shrink-0 items-center justify-center border-b border-slate-100 bg-slate-50 py-5 sm:w-24 sm:border-b-0 sm:border-r sm:border-slate-100 sm:py-0">
                              <span className="text-2xl font-semibold text-brand-600">{(a.title || "?").slice(0, 1)}</span>
                            </div>
                          ) : null}
                          <div className="flex min-h-0 flex-1 flex-col px-5 pb-5 pt-4 sm:px-6 sm:pb-6 sm:pt-5">
                          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-slate-100 pb-3">
                            <span className="inline-flex max-w-[min(100%,18rem)] items-center truncate rounded-md bg-gradient-to-r from-emerald-50/90 to-white px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-emerald-800 ring-1 ring-emerald-100/90">
                              {a.platform_label || t("source")}
                            </span>
                            {pub ? (
                              <time
                                className="shrink-0 text-[11px] font-medium tabular-nums text-slate-400"
                                dateTime={a.published_at || undefined}
                              >
                                {pub}
                              </time>
                            ) : null}
                          </div>

                          {a.categories && a.categories.length > 0 ? (
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {a.categories.slice(0, 4).map((c) => (
                                <span
                                  key={c}
                                  className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-700"
                                >
                                  {c}
                                </span>
                              ))}
                            </div>
                          ) : null}

                          <h2 className="mt-3 text-[1.05rem] font-semibold leading-snug tracking-tight text-slate-900 sm:text-lg sm:leading-snug group-hover:text-brand-600">
                            {a.title}
                          </h2>
                          <p className="mt-2 line-clamp-4 flex-1 text-sm leading-relaxed text-slate-600">{summarize(a.summary, 168)}</p>

                          {a.tab_summaries && a.tab_summaries.length > 0 ? (
                            <ul className="mt-4 space-y-2.5 border-t border-slate-100 pt-4">
                              {a.tab_summaries.slice(0, 3).map((tab) => (
                                <li
                                  key={tab.label}
                                  className="border-l-2 border-brand-200 pl-3 text-[12px] leading-snug text-slate-600"
                                >
                                  <span className="font-medium text-brand-700">{tab.label}</span>
                                  <span className="text-slate-300"> · </span>
                                  {summarize(tab.summary, 88)}
                                </li>
                              ))}
                            </ul>
                          ) : null}

                          <div className="mt-4 flex items-center gap-1.5 text-xs font-medium text-brand-600">
                            <span>{t("listViewDetail")}</span>
                            <span
                              className="inline-block transition-transform duration-300 group-hover:translate-x-0.5"
                              aria-hidden
                            >
                              →
                            </span>
                          </div>
                          </div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </Fragment>
            ))}
          </div>

          {list.length === 0 ? (
            <p className="mt-10 text-center text-sm text-slate-500">
              {searchQ ? t("resourcesEmptySearch") : t("resourcesEmptyTopic")}
            </p>
          ) : null}

          {list.length > 0 && pageMeta.total_pages > 0 ? (
            <div className="mt-10 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
              <button
                type="button"
                disabled={!pageMeta.has_prev}
                onClick={() => setFeedPage((p) => Math.max(1, p - 1))}
                className="rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {t("resourcesPagePrev")}
              </button>
              <button
                type="button"
                disabled={!pageMeta.has_next}
                onClick={() => setFeedPage((p) => p + 1)}
                className="rounded-md bg-brand-500 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-brand-400 disabled:cursor-not-allowed disabled:opacity-35"
              >
                {t("resourcesPageNext")}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );

  return (
    <div className="mx-auto max-w-[1400px] px-2 sm:px-4">
      <div className="grid gap-8 lg:grid-cols-[1fr_300px] lg:items-start xl:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-6">
          {filterPanel}
          {listSection}
        </div>
        <aside className="min-w-0">
          <div className="lg:sticky lg:top-24">
            <FeedSidebar mode={mode} listLen={list.length} categoryOptions={categoryOptions} />
          </div>
        </aside>
      </div>
    </div>
  );
}
