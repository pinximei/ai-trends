import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

function formatFeedDateLabel(isoDay: string, locale: "zh" | "en"): string {
  if (!isoDay || isoDay === "_") return "—";
  const d = new Date(`${isoDay}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return isoDay;
  return d.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { dateStyle: "long", timeZone: "UTC" });
}

function isDayFeedResponse(d: unknown): d is ArticlesFeedDayResponse {
  return Boolean(d && typeof d === "object" && (d as ArticlesFeedDayResponse).paginate_by === "day");
}

export function FeedRadarPage({ mode }: { mode: "news" | "apps" }) {
  const { t, lang } = useI18n();
  const [timeKey, setTimeKey] = useState<TimeKey>("d30");
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
    <div className="glass-light relative overflow-hidden p-5 sm:p-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{pageTitle}</h1>
          <p className="mt-1 max-w-xl text-sm text-slate-500">{t("resourcesFeedDayHint")}</p>
        </div>
        <div
          className="relative hidden h-24 w-24 shrink-0 items-center justify-center rounded-3xl border border-violet-200/80 bg-gradient-to-br from-violet-100/90 via-white to-sky-100/80 shadow-ui sm:flex"
          aria-hidden
        >
          <Box className="h-12 w-12 text-violet-500 opacity-90 drop-shadow-md" strokeWidth={1.25} />
        </div>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="relative min-w-0 flex-1 sm:max-w-xl">
          <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            {t("resourcesSearchLabel")}
          </span>
          <Search className="pointer-events-none absolute bottom-3 left-4 h-4 w-4 text-slate-400" />
          <input
            type="search"
            enterKeyHint="search"
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
            placeholder={t("resourcesSearchPlaceholder")}
            className="w-full rounded-full border border-slate-200 bg-slate-50/90 py-3 pl-11 pr-4 text-sm text-slate-800 shadow-inner outline-none ring-violet-400/25 placeholder:text-slate-400 focus:border-violet-300 focus:ring-2"
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
            className="shrink-0 rounded-full border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50"
          >
            {t("resourcesSearchClear")}
          </button>
        ) : null}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <span className="w-full text-xs font-semibold uppercase tracking-wider text-slate-500 sm:w-auto sm:mr-1">
          {t("resourcesTimeFilter")}
        </span>
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

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
        <span className="w-full text-xs font-semibold uppercase tracking-wider text-slate-500 sm:w-auto sm:mr-1">
          {t("resourcesCategoryFilter")}
        </span>
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
            <span className="ml-1 font-mono text-[10px] text-slate-500">({row.count})</span>
          </button>
        ))}
      </div>

      {!loading && pageMeta.total_pages > 0 ? (
        <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
          <div className="text-sm text-slate-600">
            <span className="font-semibold text-violet-700">{pageSummaryText}</span>
            {pageMeta.day_utc ? (
              <span className="ml-2 text-slate-500">· UTC {formatFeedDateLabel(pageMeta.day_utc, lang)}</span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!pageMeta.has_prev || loading}
              onClick={() => setFeedPage((p) => Math.max(1, p - 1))}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
            >
              {t("resourcesPagePrev")}
            </button>
            <button
              type="button"
              disabled={!pageMeta.has_next || loading}
              onClick={() => setFeedPage((p) => p + 1)}
              className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-35"
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
                className="w-20 rounded-xl border border-slate-200 bg-white px-2 py-1.5 font-mono text-sm text-slate-800"
                aria-label={t("resourcesPageJumpPlaceholder")}
              />
              <button
                type="button"
                onClick={() => onJump()}
                className="rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm"
              >
                {t("resourcesPageGo")}
              </button>
            </label>
          </div>
        </div>
      ) : null}

      {pageMeta.days_scan_truncated ? (
        <p className="mt-3 text-xs font-medium text-amber-700">{t("resourcesDaysTruncated")}</p>
      ) : null}
    </div>
  );

  const listSection = (
    <>
      {err ? <p className="mt-6 text-sm font-medium text-rose-600">{err}</p> : null}
      {loading ? <p className="mt-8 text-sm text-slate-500">{t("resourcesLoading")}</p> : null}

      {!loading ? (
        <>
          <p className="mt-8 text-center text-[11px] font-medium uppercase tracking-wider text-slate-400">{t("resourcesByDate")}</p>
          <div className="mt-6 space-y-12">
            {listByDate.map(([dayKey, rows]) => (
              <Fragment key={dayKey}>
                <div className="flex items-center gap-3 px-1">
                  <span className="text-xs font-bold uppercase tracking-wider text-violet-600">
                    {formatFeedDateLabel(dayKey, lang)}
                  </span>
                  <span className="h-px flex-1 bg-gradient-to-r from-violet-200 to-transparent" aria-hidden />
                </div>
                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  {rows.map((a) => (
                    <Link
                      key={a.id}
                      to={`/resources/${a.id}`}
                      className="group relative flex min-h-[200px] flex-col overflow-hidden rounded-3xl border border-slate-200/90 bg-white p-5 shadow-card transition duration-300 hover:-translate-y-0.5 hover:border-violet-200 hover:shadow-ui"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="inline-flex max-w-[72%] truncate rounded-lg bg-emerald-50 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-emerald-700 ring-1 ring-emerald-200">
                          {a.platform_label || t("source")}
                        </span>
                        {a.published_at ? (
                          <span className="shrink-0 font-mono text-[10px] text-slate-400">{a.published_at.slice(0, 10)}</span>
                        ) : null}
                      </div>
                      {a.categories && a.categories.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {a.categories.slice(0, 4).map((c) => (
                            <span
                              key={c}
                              className="rounded-lg bg-violet-50 px-2 py-0.5 text-[10px] font-semibold text-violet-800 ring-1 ring-violet-100"
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-3 text-base font-bold leading-snug text-slate-900 group-hover:text-violet-700">{a.title}</div>
                      <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-600">{summarize(a.summary, 160)}</p>
                      {a.tab_summaries && a.tab_summaries.length > 0 ? (
                        <div className="mt-3 space-y-1.5 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
                          {a.tab_summaries.slice(0, 3).map((tab) => (
                            <div key={tab.label} className="text-[11px] leading-snug text-slate-600">
                              <span className="font-semibold text-violet-700">{tab.label}</span>
                              <span className="text-slate-400"> · </span>
                              {summarize(tab.summary, 96)}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-3 text-xs font-semibold text-violet-600 opacity-0 transition group-hover:opacity-100">
                        {t("trendViewDetail")} →
                      </div>
                    </Link>
                  ))}
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
                className="rounded-full bg-gradient-to-r from-violet-600 to-sky-500 px-5 py-2.5 text-sm font-semibold text-white shadow-md disabled:cursor-not-allowed disabled:opacity-35"
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
      <div className="grid gap-8 xl:grid-cols-[1fr_300px] xl:items-start">
        <div className="min-w-0 space-y-6">
          {filterPanel}
          {listSection}
        </div>
        <aside className="hidden min-w-0 xl:block">
          <div className="sticky top-24">
            <FeedSidebar mode={mode} listLen={list.length} categoryOptions={categoryOptions} />
          </div>
        </aside>
      </div>
      <aside className="mt-10 xl:hidden">
        <FeedSidebar mode={mode} listLen={list.length} categoryOptions={categoryOptions} />
      </aside>
    </div>
  );
}
