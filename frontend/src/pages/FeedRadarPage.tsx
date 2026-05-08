import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { useI18n } from "@/i18n";

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

export function FeedRadarPage({ mode }: { mode: "news" | "apps" }) {
  const { t, lang } = useI18n();
  const [timeKey, setTimeKey] = useState<TimeKey>("d30");
  const [list, setList] = useState<ArticleFeedCard[]>([]);
  const [fingerprints, setFingerprints] = useState<string[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [categoryKey, setCategoryKey] = useState<string | null>(null);
  const [categoryOptions, setCategoryOptions] = useState<Array<{ label: string; count: number }>>([]);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQ, setSearchQ] = useState("");

  const timeParams = useMemo(() => timeKeyToArticleParams(timeKey), [timeKey]);

  useEffect(() => {
    const t = window.setTimeout(() => setSearchQ(searchDraft.trim()), 350);
    return () => window.clearTimeout(t);
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
    setList([]);
    setFingerprints([]);
    setNextCursor(null);
    setHasMore(false);

    publicApi
      .articlesFeed({
        feed: mode,
        industry_slug: INDUSTRY_SLUG,
        page_size: 18,
        ...timeParams,
        category: categoryKey,
        q: searchQ || null,
      })
      .then((d) => {
        if (cancelled) return;
        const fp = new Set<string>();
        const items: ArticleFeedCard[] = [];
        for (const it of d.items) {
          if (fp.has(it.fingerprint)) continue;
          fp.add(it.fingerprint);
          items.push(it);
        }
        setList(items);
        setFingerprints(Array.from(fp));
        setNextCursor(d.next_cursor);
        setHasMore(Boolean(d.has_more));
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
  }, [mode, timeKey, timeParams, categoryKey, searchQ]);

  const onLoadMore = async () => {
    if (loadingMore || !nextCursor) return;
    setLoadingMore(true);
    setErr("");
    try {
      const excludeCsv = fingerprints.slice(-120).join(",") || undefined;
      const d = await publicApi.articlesFeed({
        feed: mode,
        industry_slug: INDUSTRY_SLUG,
        page_size: 18,
        cursor: nextCursor,
        exclude_fp: excludeCsv,
        ...timeParams,
        category: categoryKey,
        q: searchQ || null,
      });
      setList((prev) => {
        const seen = new Set(prev.map((x) => x.fingerprint));
        const add = d.items.filter((x) => !seen.has(x.fingerprint));
        return [...prev, ...add];
      });
      setFingerprints((prev) => {
        const s = new Set(prev);
        for (const x of d.items) s.add(x.fingerprint);
        return Array.from(s);
      });
      setNextCursor(d.next_cursor);
      if (d.items.length === 0 && !d.has_more) {
        setNextCursor(null);
      }
      setHasMore(Boolean(d.has_more));
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 text-slate-100 sm:px-6 sm:py-8">
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-4 shadow-[inset_0_0_32px_rgba(0,0,0,0.2)] sm:px-6 sm:py-5">
        <h1 className="text-lg font-semibold tracking-tight text-white sm:text-xl">{pageTitle}</h1>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-xl">
            <span className="text-xs uppercase tracking-wider text-slate-500">{t("resourcesSearchLabel")}</span>
            <input
              type="search"
              enterKeyHint="search"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              placeholder={t("resourcesSearchPlaceholder")}
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] px-3.5 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
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
              className="shrink-0 rounded-xl border border-white/15 bg-white/[0.06] px-3.5 py-2.5 text-sm font-medium text-slate-300 hover:bg-white/10 hover:text-white"
            >
              {t("resourcesSearchClear")}
            </button>
          ) : null}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-slate-500">{t("resourcesTimeFilter")}</span>
          {TIME_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => {
                setTimeKey(f.key);
                setCategoryKey(null);
              }}
              className={`rounded-xl px-3.5 py-2 text-sm font-medium transition ${
                timeKey === f.key
                  ? "bg-gradient-to-r from-fuchsia-500/30 to-cyan-500/20 text-white shadow-[inset_0_0_20px_rgba(217,70,239,0.15)] ring-1 ring-fuchsia-400/35"
                  : "bg-white/[0.06] text-slate-300 hover:bg-white/10 hover:text-white"
              }`}
            >
              {t(f.labelKey)}
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-4">
          <span className="text-xs uppercase tracking-wider text-slate-500">{t("resourcesCategoryFilter")}</span>
          <button
            type="button"
            onClick={() => setCategoryKey(null)}
            className={`rounded-xl px-3.5 py-2 text-sm font-medium transition ${
              categoryKey == null
                ? "bg-gradient-to-r from-cyan-500/25 to-violet-500/20 text-white ring-1 ring-cyan-400/35"
                : "bg-white/[0.06] text-slate-300 hover:bg-white/10 hover:text-white"
            }`}
          >
            {t("resourcesCategoryAll")}
          </button>
          {categoryOptions.map((row) => (
            <button
              key={row.label}
              type="button"
              onClick={() => setCategoryKey(row.label)}
              className={`rounded-xl px-3.5 py-2 text-sm font-medium transition ${
                categoryKey === row.label
                  ? "bg-gradient-to-r from-cyan-500/25 to-violet-500/20 text-white ring-1 ring-cyan-400/35"
                  : "bg-white/[0.06] text-slate-300 hover:bg-white/10 hover:text-white"
              }`}
            >
              {row.label}
              <span className="ml-1 font-mono text-[10px] text-slate-500">({row.count})</span>
            </button>
          ))}
        </div>
      </div>

      {err ? <p className="mt-6 text-sm text-red-400">{err}</p> : null}
      {loading ? <p className="mt-8 text-sm text-slate-500">{t("resourcesLoading")}</p> : null}

      {!loading ? (
        <>
          <p className="mt-6 text-center text-[11px] text-slate-500">{t("resourcesByDate")}</p>
          <div className="mt-6 space-y-12">
            {listByDate.map(([dayKey, rows]) => (
              <Fragment key={dayKey}>
                <div className="flex items-center gap-3 px-1">
                  <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400/90">
                    {formatFeedDateLabel(dayKey, lang)}
                  </span>
                  <span className="h-px flex-1 bg-gradient-to-r from-cyan-500/35 to-transparent" aria-hidden />
                </div>
                <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                  {rows.map((a) => (
                    <Link
                      key={a.id}
                      to={`/resources/${a.id}`}
                      className="group relative flex min-h-[210px] flex-col overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.07] via-night-950/40 to-night-950/90 p-5 shadow-[0_16px_48px_rgba(0,0,0,0.35),inset_0_1px_0_rgba(255,255,255,0.06)] transition duration-300 hover:border-cyan-400/30 hover:shadow-[0_20px_56px_rgba(34,211,238,0.08)]"
                    >
                      <span
                        className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-cyan-500/10 blur-2xl transition group-hover:bg-cyan-400/15"
                        aria-hidden
                      />
                      <div className="flex items-start justify-between gap-2">
                        <span className="inline-flex max-w-[70%] truncate rounded-lg bg-slate-900/80 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-cyan-300/90 ring-1 ring-cyan-500/25">
                          {a.platform_label || t("source")}
                        </span>
                        {a.published_at ? (
                          <span className="shrink-0 font-mono text-[10px] text-slate-500">{a.published_at.slice(0, 10)}</span>
                        ) : null}
                      </div>
                      {a.categories && a.categories.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {a.categories.slice(0, 4).map((c) => (
                            <span
                              key={c}
                              className="rounded-md bg-fuchsia-500/15 px-2 py-0.5 text-[10px] font-medium text-fuchsia-200/90 ring-1 ring-fuchsia-500/25"
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-3 text-base font-semibold leading-snug text-white group-hover:text-cyan-100">{a.title}</div>
                      <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-400">{summarize(a.summary, 160)}</p>
                      {a.tab_summaries && a.tab_summaries.length > 0 ? (
                        <div className="mt-3 space-y-1.5 rounded-xl border border-cyan-500/10 bg-gradient-to-br from-cyan-950/20 to-transparent p-2.5 ring-1 ring-white/5">
                          {a.tab_summaries.slice(0, 3).map((tab) => (
                            <div key={tab.label} className="text-[11px] leading-snug text-slate-400">
                              <span className="font-semibold text-cyan-300/95">{tab.label}</span>
                              <span className="text-slate-600"> · </span>
                              {summarize(tab.summary, 96)}
                            </div>
                          ))}
                        </div>
                      ) : null}
                      <div className="mt-3 text-xs font-medium text-cyan-400/80 opacity-0 transition group-hover:opacity-100">
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

          {list.length > 0 && hasMore && nextCursor ? (
            <div className="mt-10 flex flex-col items-center gap-2">
              <button
                type="button"
                disabled={loadingMore}
                onClick={() => void onLoadMore()}
                className="rounded-xl border border-cyan-500/35 bg-cyan-500/10 px-6 py-2.5 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-500/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {loadingMore ? t("resourcesLoadingMore") : t("resourcesLoadMore")}
              </button>
              <p className="max-w-lg text-center text-[11px] text-slate-500">{t("resourcesCursorHint")}</p>
            </div>
          ) : list.length > 0 ? (
            <p className="mt-8 text-center text-xs text-slate-500">{t("resourcesNoMore")}</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
