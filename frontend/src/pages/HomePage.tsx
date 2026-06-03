import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Flame, Mail, Newspaper, Radar, Sparkles, TrendingUp, Wrench } from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { IndustryWindPanel, type IndustryWindData } from "@/components/home/IndustryWindPanel";
import { HomeArticleTile } from "@/components/home/HomeArticleTile";
import { HomeSection } from "@/components/home/HomeSection";
import { mergeSourceLanes, platformAccent, radarGridClass, type SourceLane } from "@/components/home/homeUtils";
import { useNewsletterSubscribe } from "@/hooks/useNewsletterSubscribe";
import { useI18n } from "@/i18n";
import { NEWSLETTER_SUBSCRIBE_ENABLED } from "@/lib/newsletterConfig";
import {
  homePayloadHasContent,
  mergeHomeDashboardPayload,
  readHomeDashboardCache,
  readHomeDashboardCacheAgeMs,
  readHomePageBoot,
  writeHomeDashboardCache,
  type HomeDashboardCachePayload,
  type HomeTrendOverview,
} from "@/lib/homeDashboardCache";

const INDUSTRY = "ai";

/** 首页资讯情报墙展示条数（与侧栏应用榜高度大致对齐） */
const HOME_NEWS_WALL_LIMIT = 8;

type SparkPoint = { day: string; count: number };

const SPARK_W = 400;
const SPARK_H = 188;
const SPARK_ML = 42;
const SPARK_MR = 14;
/** 顶部留白略大，避免「篇/日」与最高刻度数字重叠 */
const SPARK_MT = 16;
const SPARK_MB = 30;

function formatSparkDayShort(day: string): string {
  const parts = day.split("-");
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
  return day;
}

function formatSparkDayLabel(day: string): string {
  const d = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return day;
  return d.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric", timeZone: "UTC" });
}

function buildYTicks(maxVal: number): number[] {
  const max = Math.max(maxVal, 1);
  if (max <= 4) return Array.from({ length: max + 1 }, (_, i) => i);
  const mid = Math.round(max / 2);
  return [...new Set([0, mid, max])].sort((a, b) => a - b);
}

function layoutSparkline(points: SparkPoint[]) {
  const counts = points.map((p) => p.count);
  const max = Math.max(...counts, 1);
  const yTicks = buildYTicks(max);
  const yMax = yTicks[yTicks.length - 1] ?? max;
  const innerW = SPARK_W - SPARK_ML - SPARK_MR;
  const innerH = SPARK_H - SPARK_MT - SPARK_MB;
  const yAt = (v: number) => SPARK_MT + innerH - (v / yMax) * innerH;
  const xAt = (i: number) =>
    points.length === 1 ? SPARK_ML + innerW / 2 : SPARK_ML + (i / (points.length - 1)) * innerW;

  const coords = points.map((p, i) => ({
    ...p,
    x: xAt(i),
    y: yAt(p.count),
    index: i,
  }));

  const line = coords.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `${line} L${coords[coords.length - 1]?.x ?? SPARK_ML} ${SPARK_MT + innerH} L${coords[0]?.x ?? SPARK_ML} ${SPARK_MT + innerH} Z`;

  const xLabelIdx =
    points.length <= 1
      ? [0]
      : points.length === 2
        ? [0, points.length - 1]
        : [0, Math.floor((points.length - 1) / 2), points.length - 1];

  return { coords, line, area, yTicks, yMax, innerH, xLabelIdx };
}

function TrendSparkline({
  points,
  tall = false,
  metricNote,
}: {
  points: SparkPoint[];
  tall?: boolean;
  metricNote?: string | null;
}) {
  const { t } = useI18n();
  const [hover, setHover] = useState<number | null>(null);

  const blockW = tall ? "w-full" : "w-full max-w-[20rem]";
  const chartH = tall ? "h-[15rem] sm:h-[17rem] lg:h-[19rem]" : "h-44";
  const plotLeftPct = `${(SPARK_ML / SPARK_W) * 100}%`;
  const plotWidthPct = `${((SPARK_W - SPARK_ML - SPARK_MR) / SPARK_W) * 100}%`;

  if (!points.length) {
    return (
      <div className={`flex items-center justify-center text-sm text-slate-400 ${tall ? "min-h-[20rem]" : "h-44"}`}>
        —
      </div>
    );
  }

  const layout = layoutSparkline(points);
  const { coords, line, area, yTicks, yMax, innerH, xLabelIdx } = layout;
  const counts = points.map((p) => p.count);
  const sum = counts.reduce((a, n) => a + n, 0);
  const peak = Math.max(...counts);
  const avg = points.length ? Math.round((sum / points.length) * 10) / 10 : 0;
  const active = hover != null ? coords[hover] : null;
  const baselineY = SPARK_MT + innerH;
  const plotPct = (x: number) => `${((x - SPARK_ML) / (SPARK_W - SPARK_ML - SPARK_MR)) * 100}%`;

  return (
    <div className={`flex w-full flex-col items-center ${blockW}`}>
      <header className="w-full text-center">
        <h3 className="text-base font-bold text-slate-900 sm:text-lg">
          {t("homeAiTrend")}：{t("homeTrendChartTitle")}
        </h3>
        <p className="mt-2 text-sm text-slate-700">
          {t("homeTrendFootSum")}{" "}
          <span className="font-bold tabular-nums text-violet-700">{formatCount(sum)}</span>
          <span className="mx-2 text-slate-300">·</span>
          {t("homeTrendFootAvg")} <span className="font-bold tabular-nums text-violet-700">{avg}</span>
          <span className="mx-2 text-slate-300">·</span>
          {t("homeTrendFootPeak")}{" "}
          <span className="font-bold tabular-nums text-violet-700">{formatCount(peak)}</span>
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-slate-500">{t("homeTrendLegend")}</p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">{t("homeTrendVsWindHint")}</p>
        <p className="mt-0.5 text-xs text-slate-400">{metricNote?.trim() || t("homeTrendDataNote")}</p>
      </header>

      <div className="relative mt-4 w-full">
        <svg
          viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
          className={`block w-full text-violet-600 ${chartH}`}
          role="img"
          aria-label={`${t("homeAiTrend")}：${t("homeTrendChartTitle")}，${t("homeTrendFootSum")} ${formatCount(sum)}`}
        >
          <defs>
            <linearGradient id="home-trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(139 92 246)" stopOpacity="0.2" />
              <stop offset="100%" stopColor="rgb(139 92 246)" stopOpacity="0" />
            </linearGradient>
          </defs>

          <line
            x1={SPARK_ML}
            y1={SPARK_MT}
            x2={SPARK_ML}
            y2={baselineY}
            stroke="rgb(148 163 184)"
            strokeWidth="1.5"
          />
          <line
            x1={SPARK_ML}
            y1={baselineY}
            x2={SPARK_W - SPARK_MR}
            y2={baselineY}
            stroke="rgb(148 163 184)"
            strokeWidth="1.5"
          />

          {yTicks.map((tick) => {
            const y = SPARK_MT + innerH - (tick / yMax) * innerH;
            return (
              <g key={tick}>
                <line
                  x1={SPARK_ML}
                  y1={y}
                  x2={SPARK_W - SPARK_MR}
                  y2={y}
                  stroke="rgb(241 245 249)"
                  strokeWidth="1"
                />
                <text
                  x={SPARK_ML - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="fill-slate-500 text-[11px] font-medium tabular-nums"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          <text
            x={SPARK_ML - 8}
            y={5}
            textAnchor="end"
            dominantBaseline="hanging"
            className="fill-slate-400 text-[9px] font-semibold"
          >
            {t("homeTrendYUnit")}
          </text>

          <path d={area} fill="url(#home-trend-fill)" />
          <path
            d={line}
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {active ? (
            <line
              x1={active.x}
              y1={SPARK_MT}
              x2={active.x}
              y2={baselineY}
              stroke="rgb(196 181 253)"
              strokeWidth="1"
              strokeDasharray="3 3"
            />
          ) : null}

          {coords.map((p) => {
            const on = hover === p.index;
            return (
              <g key={p.day}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={on ? 5.5 : 4}
                  fill="currentColor"
                  stroke="white"
                  strokeWidth="2"
                />
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={20}
                  fill="transparent"
                  className="cursor-pointer"
                  onMouseEnter={() => setHover(p.index)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(p.index)}
                  onBlur={() => setHover(null)}
                  tabIndex={0}
                  role="button"
                  aria-label={`${formatSparkDayLabel(p.day)} ${t("homeTrendHoverPublished")} ${p.count} ${t("homeTrendUnitShort")}`}
                />
              </g>
            );
          })}
        </svg>

        {active ? (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-md bg-slate-800 px-2.5 py-1.5 text-center text-white shadow-md"
            style={{
              left: `${(active.x / SPARK_W) * 100}%`,
              top: `${Math.max(8, (active.y / SPARK_H) * 100 - 12)}%`,
            }}
          >
            <p className="text-[11px] opacity-90">{formatSparkDayLabel(active.day)}</p>
            <p className="text-sm font-bold tabular-nums">
              {formatCount(active.count)}
              {t("homeTrendUnitShort")}
            </p>
          </div>
        ) : null}

        <div
          className="relative mt-0.5 h-6 tabular-nums text-slate-600"
          style={{ marginLeft: plotLeftPct, width: plotWidthPct }}
        >
          {xLabelIdx.map((idx) => {
            const c = coords[idx];
            if (!c) return null;
            const edge =
              idx === 0 ? "-translate-x-0" : idx === points.length - 1 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <span
                key={points[idx]?.day ?? idx}
                className={`absolute top-0 text-sm font-medium ${edge}`}
                style={{ left: plotPct(c.x) }}
              >
                {formatSparkDayShort(points[idx]?.day ?? "")}
              </span>
            );
          })}
        </div>
        <p className="mt-0.5 text-center text-xs text-slate-400" style={{ marginLeft: plotLeftPct, width: plotWidthPct }}>
          {t("homeTrendXAxis")}
        </p>
      </div>
    </div>
  );
}

function formatCount(n: number): string {
  return n.toLocaleString("zh-CN");
}

function formatGrowth(pct: number | null | undefined): string | null {
  if (pct == null || Number.isNaN(pct)) return null;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct}%`;
}

function applyHomeDashboardPayload(
  p: HomeDashboardCachePayload,
  set: {
    setNews: (v: ArticleFeedCard[]) => void;
    setApps: (v: ArticleFeedCard[]) => void;
    setEditorialNews: (v: ArticleFeedCard[]) => void;
    setEditorialApps: (v: ArticleFeedCard[]) => void;
    setHighlightApps: (v: ArticleFeedCard[]) => void;
    setHighlightMonetization: (v: ArticleFeedCard[]) => void;
    setNewsLanes: (v: SourceLane[]) => void;
    setAppsLanes: (v: SourceLane[]) => void;
    setSourceFacets: (v: HomeDashboardCachePayload["sourceFacets"]) => void;
    setTopCategories: (v: HomeDashboardCachePayload["topCategories"]) => void;
    setActiveSourceCount: (v: number) => void;
    setActiveSourceKeys: (v: string[]) => void;
    setTrendOverview: (v: HomeTrendOverview | null) => void;
    setIndustryWind: (v: IndustryWindData | null) => void;
  },
) {
  set.setNews(p.news);
  set.setApps(p.apps);
  set.setEditorialNews(p.editorialNews);
  set.setEditorialApps(p.editorialApps);
  set.setHighlightApps(p.highlightApps);
  set.setHighlightMonetization(p.highlightMonetization);
  set.setNewsLanes(p.newsLanes);
  set.setAppsLanes(p.appsLanes);
  set.setSourceFacets(p.sourceFacets);
  set.setTopCategories(p.topCategories);
  set.setActiveSourceCount(p.activeSourceCount);
  set.setActiveSourceKeys(p.activeSourceKeys);
  set.setTrendOverview(p.trendOverview);
  if (p.industryWind != null && (p.industryWind.industries?.length ?? 0) > 0) {
    set.setIndustryWind(p.industryWind);
  }
}

export function HomePage() {
  const { t } = useI18n();
  const [boot] = useState(() => readHomePageBoot());
  const [news, setNews] = useState<ArticleFeedCard[]>(() => boot?.news ?? []);
  const [apps, setApps] = useState<ArticleFeedCard[]>(() => boot?.apps ?? []);
  const [highlightApps, setHighlightApps] = useState<ArticleFeedCard[]>(() => boot?.highlightApps ?? []);
  const [highlightMonetization, setHighlightMonetization] = useState<ArticleFeedCard[]>(
    () => boot?.highlightMonetization ?? [],
  );
  const [newsLanes, setNewsLanes] = useState<SourceLane[]>(() => boot?.newsLanes ?? []);
  const [appsLanes, setAppsLanes] = useState<SourceLane[]>(() => boot?.appsLanes ?? []);
  const [sourceFacets, setSourceFacets] = useState<HomeDashboardCachePayload["sourceFacets"]>(
    () => boot?.sourceFacets ?? [],
  );
  const [topCategories, setTopCategories] = useState<HomeDashboardCachePayload["topCategories"]>(
    () => boot?.topCategories ?? [],
  );
  const [activeSourceCount, setActiveSourceCount] = useState(() => boot?.activeSourceCount ?? 6);
  const [activeSourceKeys, setActiveSourceKeys] = useState<string[]>(() => boot?.activeSourceKeys ?? []);
  const [loading, setLoading] = useState(() => !homePayloadHasContent(boot));
  const [refreshing, setRefreshing] = useState(false);
  const { email, setEmail, sent, submitting, subscribeErr, clearError, onSubscribe } = useNewsletterSubscribe();
  const [editorialApps, setEditorialApps] = useState<ArticleFeedCard[]>(() => boot?.editorialApps ?? []);
  const [editorialNews, setEditorialNews] = useState<ArticleFeedCard[]>(() => boot?.editorialNews ?? []);
  const [editorialPickFallback, setEditorialPickFallback] = useState(false);
  const [trendOverview, setTrendOverview] = useState<HomeTrendOverview | null>(
    () => boot?.trendOverview ?? null,
  );
  const [industryWind, setIndustryWind] = useState<IndustryWindData | null>(
    () => boot?.industryWind ?? null,
  );
  const [windLoading, setWindLoading] = useState(
    () => !((boot?.industryWind?.industries?.length ?? 0) > 0),
  );

  const sparkSummary = useMemo(() => {
    const spark = trendOverview?.sparkline ?? [];
    if (!spark.length) return null;
    const counts = spark.map((p) => p.count);
    return {
      sum: counts.reduce((a, n) => a + n, 0),
      peak: Math.max(...counts),
      last: counts[counts.length - 1] ?? 0,
    };
  }, [trendOverview]);

  const mergedLanes = useMemo(
    () => mergeSourceLanes(newsLanes, appsLanes, activeSourceKeys.length ? activeSourceKeys : undefined),
    [newsLanes, appsLanes, activeSourceKeys],
  );
  const radarCount = mergedLanes.length || activeSourceCount;

  useEffect(() => {
    let cancelled = false;
    const instant = readHomePageBoot();
    if (instant && homePayloadHasContent(instant)) {
      applyHomeDashboardPayload(instant, {
        setNews,
        setApps,
        setEditorialNews,
        setEditorialApps,
        setHighlightApps,
        setHighlightMonetization,
        setNewsLanes,
        setAppsLanes,
        setSourceFacets,
        setTopCategories,
        setActiveSourceCount,
        setActiveSourceKeys,
        setTrendOverview,
        setIndustryWind,
      });
      setLoading(false);
      if ((instant.industryWind?.industries?.length ?? 0) > 0) {
        setWindLoading(false);
      }
    }
    const sessionCache = readHomeDashboardCache();
    const cacheAgeMs = readHomeDashboardCacheAgeMs();
    const hadInstant = Boolean(instant ?? sessionCache);
    const cacheFresh = cacheAgeMs != null && cacheAgeMs < 90_000;

    const stateSetters = {
      setNews,
      setApps,
      setEditorialNews,
      setEditorialApps,
      setHighlightApps,
      setHighlightMonetization,
      setNewsLanes,
      setAppsLanes,
      setSourceFacets,
      setTopCategories,
      setActiveSourceCount,
      setActiveSourceKeys,
      setTrendOverview,
      setIndustryWind,
    };

    const commitPayload = (incoming: Partial<HomeDashboardCachePayload>) => {
      const prev = readHomeDashboardCache();
      const merged = mergeHomeDashboardPayload(prev, incoming);
      applyHomeDashboardPayload(merged, stateSetters);
      writeHomeDashboardCache(merged);
      if ((merged.industryWind?.industries?.length ?? 0) > 0) {
        setWindLoading(false);
      }
    };

    const loadFeedFallback = async (feed: "news" | "apps", limit: number) => {
      const res = await publicApi.articlesFeed({
        feed,
        industry_slug: INDUSTRY,
        paginate_by: "heat",
        heat_page_size: limit,
        heat_max_ranked: limit * 3,
        published_within_days: 30,
        ...(feed === "apps"
          ? { replication_complete: true, sort_by_value: true }
          : {}),
      });
      return "items" in res && Array.isArray(res.items) ? res.items : [];
    };

    const mergeWindIntoCache = (wind: IndustryWindData) => {
      const merged = mergeHomeDashboardPayload(readHomeDashboardCache(), { industryWind: wind });
      writeHomeDashboardCache(merged);
    };

    const fetchIndustryWind = async () => {
      try {
        setWindLoading(true);
        const wind = await publicApi.homeIndustryWind({ industry_slug: INDUSTRY });
        if (cancelled) return;
        if ((wind?.industries?.length ?? 0) > 0) {
          setIndustryWind(wind);
          mergeWindIntoCache(wind);
        }
      } catch {
        /* keep SSR/cache */
      } finally {
        if (!cancelled) setWindLoading(false);
      }
    };

    void fetchIndustryWind();

    const fetchDashboard = () =>
      publicApi
        .homeDashboard({
          industry_slug: INDUSTRY,
          news_limit: HOME_NEWS_WALL_LIMIT,
          apps_limit: 10,
          replicable_apps_limit: 4,
          monetization_apps_limit: 4,
          published_within_days: 30,
        })
        .then(async (data) => {
          if (cancelled) return;
          let nextNews = data.news ?? [];
          let nextApps = data.apps ?? [];
          if (nextNews.length === 0) {
            try {
              nextNews = await loadFeedFallback("news", HOME_NEWS_WALL_LIMIT);
            } catch {
              /* keep empty */
            }
          }
          if (nextApps.length === 0) {
            try {
              nextApps = await loadFeedFallback("apps", 10);
            } catch {
              /* keep empty */
            }
          }
          if (cancelled) return;
          setEditorialPickFallback(data.editorial_pick_window === "recent_fallback");
          commitPayload({
            news: nextNews,
            apps: nextApps,
            editorialNews: data.editorial_news ?? [],
            editorialApps: data.editorial_apps ?? [],
            highlightApps: data.highlight_replicable_apps ?? [],
            highlightMonetization: data.highlight_monetization_apps ?? [],
            newsLanes: data.news_source_lanes ?? [],
            appsLanes: data.apps_source_lanes ?? [],
            sourceFacets: data.source_facets ?? [],
            topCategories: data.top_categories ?? [],
            activeSourceCount: data.active_source_count ?? data.active_source_keys?.length ?? 6,
            activeSourceKeys: data.active_source_keys ?? [],
            trendOverview: data.trend ?? null,
          });
        });

    const runFetch = () => {
      fetchDashboard().catch(async () => {
        if (cancelled) return;
        if (hadInstant) return;
        try {
          const [nextNews, nextApps] = await Promise.all([
            loadFeedFallback("news", HOME_NEWS_WALL_LIMIT),
            loadFeedFallback("apps", 10),
          ]);
          if (cancelled) return;
          commitPayload({
            news: nextNews,
            apps: nextApps,
            editorialNews: [],
            editorialApps: [],
            highlightApps: [],
            highlightMonetization: [],
            newsLanes: [],
            appsLanes: [],
            sourceFacets: [],
            topCategories: [],
            activeSourceCount: 6,
            activeSourceKeys: [],
            trendOverview: null,
          });
        } catch {
          if (!cancelled) {
            setNews([]);
            setApps([]);
            setHighlightApps([]);
          }
        }
      }).finally(() => {
        if (!cancelled) {
          setLoading(false);
          setRefreshing(false);
        }
      });
    };

    if (!hadInstant) {
      setLoading(true);
      runFetch();
      return () => {
        cancelled = true;
      };
    }

    setLoading(false);
    if (cacheFresh) {
      const delayMs = instant ? 2500 : 8000;
      const timer = window.setTimeout(() => {
        if (!cancelled) {
          setRefreshing(true);
          runFetch();
        }
      }, delayMs);
      return () => {
        cancelled = true;
        window.clearTimeout(timer);
      };
    }

    setRefreshing(true);
    runFetch();
    return () => {
      cancelled = true;
    };
  }, []);

  const newsWall = news.slice(0, HOME_NEWS_WALL_LIMIT);
  const appLeaderboard = apps.slice(0, 6);
  const totalInWindow = (trendOverview?.news_count ?? 0) + (trendOverview?.apps_count ?? 0);

  const editorialAppsShow = editorialApps.slice(0, 3);
  const editorialNewsShow = editorialNews.slice(0, 3);
  const hasHomeData = homePayloadHasContent({
    news,
    apps,
    editorialNews,
    editorialApps,
    highlightApps,
    highlightMonetization,
    newsLanes,
    appsLanes,
    sourceFacets,
    topCategories,
    industryWind,
    activeSourceCount,
    activeSourceKeys,
    trendOverview,
  });
  const showBlockingLoad = loading && !hasHomeData;

  return (
    <div className="w-full space-y-5 lg:space-y-7">
      <section className="ui-card overflow-hidden p-5 sm:p-6" data-testid="home-hero">
        <div className="min-w-0 text-center sm:text-left">
          {refreshing ? (
            <p className="mb-2 text-right text-[11px] font-medium text-slate-400 sm:text-left">{t("homeRefreshing")}</p>
          ) : null}
          <h1 className="text-2xl font-bold leading-tight tracking-tight text-slate-900 sm:text-3xl lg:text-4xl">
            {t("homeMainHeroTitle")}
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-slate-600 sm:mx-0 sm:text-[15px] lg:text-base">
            {t("homeMainHeroDesc")}
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-3 sm:justify-start">
            <Link
              to="/news"
              className="inline-flex items-center rounded-full bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700"
            >
              {t("homeMainHeroCta1")}
            </Link>
            <Link
              to="/apps"
              state={{ replicationFilter: "high_value" }}
              className="inline-flex items-center rounded-full border border-slate-200 bg-white px-5 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
            >
              {t("homeMainHeroCta2")}
            </Link>
            <a
              href="#industry-wind"
              className="inline-flex items-center rounded-full border border-orange-200 bg-orange-50 px-5 py-2.5 text-sm font-semibold text-orange-800 transition hover:bg-orange-100"
            >
              {t("homeHeroCtaWind")}
            </a>
          </div>
        </div>
      </section>

      <HomeSection
        className="ui-card overflow-hidden p-4 sm:p-5 ring-1 ring-orange-100/80"
        title={t("homeEditorialPicksTitle")}
        subtitle={
          editorialPickFallback ? t("homeEditorialPicksSubFallback") : t("homeEditorialPicksSub")
        }
        icon={<Flame className="h-5 w-5 text-orange-500" strokeWidth={2} />}
        action={{ label: t("homeEditorialPicksCta"), to: "/news" }}
      >
        {showBlockingLoad ? (
          <p className="text-sm text-slate-500">{t("homeLoading")}</p>
        ) : editorialAppsShow.length === 0 && editorialNewsShow.length === 0 ? (
          <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <p className="mb-3 text-xs font-bold uppercase tracking-wider text-sky-700">{t("homeEditorialApps")}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                {editorialAppsShow.map((item) => (
                  <HomeArticleTile key={item.id} item={item} variant="tile" />
                ))}
              </div>
            </div>
            <div>
              <p className="mb-3 text-xs font-bold uppercase tracking-wider text-violet-700">{t("homeEditorialNews")}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
                {editorialNewsShow.map((item) => (
                  <HomeArticleTile key={item.id} item={item} variant="tile" />
                ))}
              </div>
            </div>
          </div>
        )}
      </HomeSection>

      <div className="grid gap-5 lg:grid-cols-12 lg:gap-6">
        <div className="lg:col-span-8">
          <HomeSection
            className="ui-card h-full overflow-hidden p-4 sm:p-5"
            title={t("homeNewsWall")}
            subtitle={t("homeNewsWallSub")}
            icon={<Newspaper className="h-5 w-5 text-violet-600" strokeWidth={2} />}
            action={{ label: t("homeNewsWallCta"), to: "/news" }}
          >
            {showBlockingLoad ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : newsWall.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {newsWall.map((item) => (
                  <HomeArticleTile key={item.id} item={item} variant="tile" />
                ))}
              </div>
            )}
          </HomeSection>
        </div>
        <aside className="lg:col-span-4">
          <HomeSection
            className="ui-card h-full overflow-hidden p-4 sm:p-5"
            title={t("homeAppsLeaderboard")}
            subtitle={t("homeAppsLeaderboardSub")}
            icon={<Wrench className="h-5 w-5 text-sky-600" strokeWidth={2} />}
            action={{ label: t("homeAppsLeaderboardCta"), to: "/apps" }}
          >
            {showBlockingLoad ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : appLeaderboard.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <div className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-100 bg-white">
                {appLeaderboard.map((item, idx) => (
                  <HomeArticleTile key={item.id} item={item} variant="rank" rank={idx + 1} />
                ))}
              </div>
            )}
          </HomeSection>
        </aside>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 lg:gap-6">
        <HomeSection
          className="ui-card overflow-hidden p-4 sm:p-5"
          title={t("homeHighlightReplicableApps")}
          subtitle={t("homeHighlightReplicableAppsSub")}
          icon={<Sparkles className="h-5 w-5 text-sky-600" strokeWidth={2} />}
          action={{
            label: t("homeHighlightReplicableAppsCta"),
            to: "/apps",
            state: { replicationFilter: "complete" },
          }}
        >
          {showBlockingLoad ? (
            <p className="text-sm text-slate-500">{t("homeLoading")}</p>
          ) : highlightApps.length === 0 ? (
            <p className="rounded-xl border border-dashed border-sky-200 bg-sky-50/50 px-4 py-8 text-center text-sm text-slate-600">
              {t("homeHighlightReplicableAppsEmpty")}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {highlightApps.map((item) => (
                <HomeArticleTile key={item.id} item={item} variant="tile" />
              ))}
            </div>
          )}
        </HomeSection>

        <HomeSection
          className="ui-card overflow-hidden p-4 sm:p-5"
          title={t("homeHighlightMonetizationApps")}
          subtitle={t("homeHighlightMonetizationAppsSub")}
          icon={<TrendingUp className="h-5 w-5 text-emerald-600" strokeWidth={2} />}
          action={{
            label: t("homeHighlightMonetizationAppsCta"),
            to: "/apps",
            state: { replicationFilter: "complete", category: "变现案例" },
          }}
        >
          {showBlockingLoad ? (
            <p className="text-sm text-slate-500">{t("homeLoading")}</p>
          ) : highlightMonetization.length === 0 ? (
            <p className="rounded-xl border border-dashed border-emerald-200 bg-emerald-50/50 px-4 py-8 text-center text-sm text-slate-600">
              {t("homeHighlightMonetizationAppsEmpty")}
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {highlightMonetization.map((item) => (
                <HomeArticleTile key={item.id} item={item} variant="tile" />
              ))}
            </div>
          )}
        </HomeSection>
      </div>

      <IndustryWindPanel data={industryWind} loading={windLoading && !industryWind} />

      <HomeSection
        className="ui-card overflow-hidden p-4 sm:p-5"
        title={radarCount > 0 ? `${radarCount}路雷达` : t("homeSourceRadar")}
        subtitle={
          radarCount > 0
            ? `${radarCount} 路已配置数据源各 1 条（与上方精选区不重复 id，按源单独取热度最高）`
            : t("homeSourceRadarSub")
        }
        icon={<Radar className="h-5 w-5" strokeWidth={2} />}
      >
        {showBlockingLoad ? (
          <p className="text-sm text-slate-500">{t("homeLoading")}</p>
        ) : (
          <div className={radarGridClass(radarCount)}>
            {mergedLanes.map((lane) => {
              const item = lane.items[0];
              const accent = platformAccent(lane.source_key);
              const facet = sourceFacets.find((f) => f.key === lane.source_key);
              if (!item) {
                return (
                  <div
                    key={lane.source_key}
                    className={`ui-card p-3 sm:p-4 ring-1 ring-dashed ${accent.ring} bg-slate-50/80`}
                  >
                    <div className="flex items-center gap-2">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${accent.dot} opacity-50`} aria-hidden />
                      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase ${accent.badge}`}>
                        {lane.source_label}
                      </span>
                    </div>
                    <p className="mt-3 text-xs leading-relaxed text-slate-500">{t("homeSourceRadarNoData")}</p>
                  </div>
                );
              }
              return (
                <Link
                  key={lane.source_key}
                  to={`/resources/${item.id}`}
                  className={`ui-card block p-3 transition hover:shadow-md sm:p-4 ring-1 ${accent.ring}`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${accent.dot}`} aria-hidden />
                    <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold uppercase ${accent.badge}`}>
                      {lane.source_label}
                    </span>
                    {facet ? (
                      <span className="ml-auto text-[10px] tabular-nums text-slate-400">
                        {facet.news_count + facet.apps_count}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm font-semibold leading-snug text-slate-900">{item.title}</p>
                  <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-slate-500">
                    {(item.card_highlights || item.card_description || item.summary || "").slice(0, 88)}
                  </p>
                </Link>
              );
            })}
          </div>
        )}
      </HomeSection>

      <section className="ui-card overflow-hidden p-4 sm:p-5">
        <p className="mb-4 text-xs font-bold uppercase tracking-wider text-slate-400">{t("homeDataOverviewTitle")}</p>
        <div className="grid gap-5 lg:grid-cols-2 lg:items-stretch lg:gap-6">
          {trendOverview ? (
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">{t("homeLiveStats")}</p>
              <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{t("homeLiveStatsSub")}</p>
              <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3 sm:gap-3">
                <div className="rounded-xl bg-violet-50/80 px-3 py-2.5 ring-1 ring-violet-100">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-700/80">{t("homeStatNewArticles")}</p>
                  <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">
                    {formatCount(trendOverview.news_count)}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatGrowth(trendOverview.news_growth_pct) ? (
                      <span className="font-semibold text-emerald-600">
                        {formatGrowth(trendOverview.news_growth_pct)} {t("homeStatGrowth")}
                      </span>
                    ) : (
                      t("homeStatNoCompare")
                    )}
                  </p>
                </div>
                <div className="rounded-xl bg-sky-50/80 px-3 py-2.5 ring-1 ring-sky-100">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-sky-800/80">{t("homeStatActiveTools")}</p>
                  <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">
                    {formatCount(trendOverview.apps_count)}
                  </p>
                  <p className="text-xs text-slate-500">
                    {formatGrowth(trendOverview.apps_growth_pct) ? (
                      <span className="font-semibold text-emerald-600">
                        {formatGrowth(trendOverview.apps_growth_pct)} {t("homeStatGrowth")}
                      </span>
                    ) : (
                      t("homeStatNoCompare")
                    )}
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 px-3 py-2.5 ring-1 ring-slate-200">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">{t("homeStatTotalItems")}</p>
                  <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">{formatCount(totalInWindow)}</p>
                </div>
                <div className="rounded-xl bg-indigo-50/80 px-3 py-2.5 ring-1 ring-indigo-100">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-indigo-800/80">{t("homeStatSources")}</p>
                  <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">
                    {sourceFacets.length}
                    <span className="text-sm font-semibold text-slate-400">/{activeSourceCount}</span>
                  </p>
                </div>
                {sparkSummary ? (
                  <>
                    <div className="rounded-xl bg-emerald-50/80 px-3 py-2.5 ring-1 ring-emerald-100">
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-emerald-800/80">
                        {t("homeStatTrendSum")}
                      </p>
                      <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">
                        {formatCount(sparkSummary.sum)}
                      </p>
                    </div>
                    <div className="rounded-xl bg-amber-50/80 px-3 py-2.5 ring-1 ring-amber-100">
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800/80">
                        {t("homeStatTrendPeak")}
                      </p>
                      <p className="mt-1 text-lg font-bold tabular-nums text-slate-900 sm:text-xl">
                        {formatCount(sparkSummary.peak)}
                      </p>
                      <p className="text-xs text-slate-500">
                        {t("homeTrendChartTitle")} · {formatCount(sparkSummary.last)}
                      </p>
                    </div>
                  </>
                ) : null}
              </div>

              {sourceFacets.length > 0 ? (
                <>
                  <p className="mt-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">{t("homeStatPerSource")}</p>
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {sourceFacets.map((f) => {
                      const accent = platformAccent(f.key);
                      const label = f.label || f.key;
                      const total = f.news_count + f.apps_count;
                      return (
                        <div
                          key={f.key}
                          className={`rounded-lg border-l-[3px] bg-slate-50/90 px-2.5 py-2 ring-1 ring-slate-200/90 ${accent.border}`}
                        >
                          <span className={`inline-block max-w-full truncate rounded px-1.5 py-0.5 text-[9px] font-bold uppercase ${accent.badge}`}>
                            {label}
                          </span>
                          <p className="mt-1 text-base font-bold tabular-nums text-slate-900">{formatCount(total)}</p>
                          <p className="text-[10px] text-slate-500">
                            {t("homeStatNewArticles")} {f.news_count} · {t("homeStatActiveTools")} {f.apps_count}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : null}

            </div>
          ) : showBlockingLoad ? (
            <div className="flex min-h-[8rem] items-center justify-center text-sm text-slate-500">{t("homeLoading")}</div>
          ) : null}

          <div
            className={`flex min-w-0 flex-col ${!showBlockingLoad && trendOverview ? "border-t border-slate-100 pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0" : ""}`}
          >
            <div className="flex flex-1 flex-col items-center justify-center px-1 py-2">
              {showBlockingLoad && !trendOverview ? (
                <div className="flex min-h-[16rem] flex-1 items-center justify-center text-sm text-slate-400">
                  {t("homeLoading")}
                </div>
              ) : (
                <TrendSparkline
                  points={trendOverview?.sparkline ?? []}
                  tall
                  metricNote={trendOverview?.metric_note}
                />
              )}
            </div>
          </div>
        </div>
      </section>

      {NEWSLETTER_SUBSCRIBE_ENABLED ? (
        <section className="overflow-hidden rounded-2xl bg-gradient-to-r from-violet-600 via-indigo-600 to-sky-600 p-[1px] shadow-lg">
          <form
            onSubmit={onSubscribe}
            className="grid gap-4 rounded-2xl bg-gradient-to-r from-violet-600/95 via-indigo-600/95 to-sky-600/95 px-5 py-6 sm:px-8 sm:py-7 md:grid-cols-[minmax(0,1fr)_minmax(0,18rem)_auto] md:items-center md:gap-6 lg:gap-8"
          >
            <div className="flex min-w-0 items-start gap-3 text-white md:items-center">
              <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25 md:mt-0">
                <Mail className="h-5 w-5" strokeWidth={2} />
              </span>
              <p className="min-w-0 text-sm font-medium leading-relaxed md:text-[15px] lg:text-base">{t("homeSubscribeBarTitle")}</p>
            </div>
            <input
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (subscribeErr) clearError();
              }}
              placeholder={t("newsletterPlaceholder")}
              className="w-full min-w-0 rounded-full border border-white/30 bg-white py-2.5 pl-4 pr-4 text-sm text-slate-900 shadow-inner outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-white/50"
              autoComplete="email"
            />
            <button
              type="submit"
              disabled={submitting}
              className="rounded-full bg-indigo-950/90 px-8 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-indigo-950 disabled:cursor-not-allowed disabled:opacity-60 md:justify-self-end lg:px-10 lg:py-3 lg:text-[15px]"
            >
              {submitting ? t("newsletterSending") : sent ? t("newsletterThanks") : t("homeSubscribeBarBtn")}
            </button>
          </form>
          {subscribeErr ? (
            <p className="px-5 pb-3 text-center text-[11px] font-medium text-amber-200 sm:px-8" role="alert">
              {subscribeErr}
            </p>
          ) : null}
          <p className="px-5 pb-3 text-center text-[10px] text-white/70 sm:px-8">{t("newsletterHint")}</p>
        </section>
      ) : null}
    </div>
  );
}
