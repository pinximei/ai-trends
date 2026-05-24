import type { CSSProperties, FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Brain,
  ChevronRight,
  Download,
  Flame,
  LayoutGrid,
  Mail,
  Newspaper,
  Radar,
  Wrench,
} from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { HomeArticleTile } from "@/components/home/HomeArticleTile";
import { HomeSection } from "@/components/home/HomeSection";
import { HOME_SOURCE_LABELS, mergeSourceLanes, platformAccent, type SourceLane } from "@/components/home/homeUtils";
import { useI18n } from "@/i18n";
import { TOP_NAV_ITEMS } from "@/navConfig";

const INDUSTRY = "ai";

/** 首页邮件订阅条：功能未对公众开放前保持隐藏；与后台 newsletter 就绪后可改为 true */
const HOME_NEWSLETTER_VISIBLE = false;

/** 倾斜星环平面内的圆轨道半径（rem）；越大越贴近外圈光晕、离中心 AI 越远 */
const HERO_ORBIT_REM = 9.52;
const HERO_ORBIT_SEC = 52;
/** 主光晕慢旋周期（秒），与 index.css 中 .hero-halo-spin 默认值一致 */
const HERO_HALO_ROT_SEC = 88;
const HERO_RING_TILT_DEG = 58;

/** 中心 AI 块静态外发光（无呼吸） */
const HERO_AI_CARD_SHADOW =
  "0 26px 60px -10px rgba(49,46,129,0.58), 0 0 52px rgba(34,211,238,0.34), 0 0 28px rgba(167,139,250,0.22), inset 0 1px 0 rgba(255,255,255,0.42)";

function usePrefersReducedMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(mq.matches);
    const onChange = () => setReduce(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduce;
}

/** 星环平面内：圆轨道 + 逆旋保持图标正向（CSS 动画） */
function OrbitSatellite({
  angleDeg,
  orbitRem,
  reduce,
  children,
}: {
  angleDeg: number;
  orbitRem: number;
  reduce: boolean;
  children: ReactNode;
}) {
  return (
    <div
      className="absolute left-1/2 top-1/2 z-[6] h-0 w-0"
      style={{
        transform: `translate(-50%, -50%) rotate(${angleDeg}deg) translateY(-${orbitRem}rem)`,
      }}
    >
      <div className={reduce ? "flex -translate-x-1/2 -translate-y-1/2" : "hero-sat-counter flex"}>
        <span className="pointer-events-auto relative flex h-11 w-11 items-center justify-center text-indigo-600 drop-shadow-[0_2px_12px_rgba(15,23,42,0.55)] sm:h-12 sm:w-12">
          {children}
        </span>
      </div>
    </div>
  );
}

/**
 * 天体星环：圆环放在 rotateX 倾斜的 3D 平面上，透视下呈椭圆；
 * 整层 rotateZ 公转，肉眼即「绕中心转」。
 */
function HeroGraphic() {
  const { t } = useI18n();
  const reduce = usePrefersReducedMotion();
  const orbitRem = HERO_ORBIT_REM;
  const tilt = reduce ? 0 : HERO_RING_TILT_DEG;
  const orbitStepDeg = 360 / TOP_NAV_ITEMS.length;

  const heroMotionStyle = {
    ["--hero-orbit-sec" as string]: `${HERO_ORBIT_SEC}s`,
    ["--hero-halo-sec" as string]: `${HERO_HALO_ROT_SEC}s`,
  } as CSSProperties;

  return (
    <div
      data-testid="hero-graphic"
      className="relative mx-auto w-full max-w-[min(100%,392px)] shrink-0 overflow-visible px-0 py-0 sm:max-w-[416px] sm:px-0.5"
      style={heroMotionStyle}
    >
      <div
        data-orbit-square
        className="relative isolate mx-auto aspect-square w-full max-w-[352px] overflow-visible [perspective:1000px] [perspective-origin:50%_50%] sm:max-w-[380px]"
      >
        {/* 背面大环境光（不倾斜） */}
        <div
          className="pointer-events-none absolute -inset-[18%] -z-[1] rounded-full bg-[radial-gradient(circle_at_50%_40%,rgba(165,180,252,0.2)_0%,rgba(147,163,253,0.14)_28%,rgba(125,211,252,0.1)_48%,rgba(99,102,241,0.05)_72%,transparent_92%)] blur-[58px]"
          aria-hidden
        />

        <div className="relative h-full w-full [transform-style:preserve-3d]">
          {/* 星环平面：圆 → 屏上椭圆 */}
          <div
            className="absolute inset-0 flex items-center justify-center [transform-style:preserve-3d]"
            style={tilt ? { transform: `rotateX(${tilt}deg)` } : undefined}
          >
            {/* 慢旋柔光（与环同平面） */}
            <div
              data-testid="hero-halo-primary"
              className={`pointer-events-none absolute aspect-square w-[90%] max-w-[min(100%,310px)] rounded-full sm:max-w-[334px] ${reduce ? "" : "hero-halo-spin"}`}
              aria-hidden
              style={{
                background:
                  "radial-gradient(ellipse 108% 102% at 48% 36%, rgba(199,210,254,0.26) 0%, rgba(176,190,254,0.2) 18%, rgba(165,180,252,0.17) 34%, rgba(139,154,255,0.13) 50%, rgba(125,211,252,0.11) 66%, rgba(99,102,241,0.07) 82%, transparent 96%)",
                boxShadow:
                  "0 0 96px 44px rgba(125,211,252,0.18), 0 0 160px 72px rgba(167,139,250,0.12), 0 0 220px 96px rgba(99,102,241,0.05), inset 0 0 72px rgba(165,180,252,0.09), inset 0 0 120px rgba(79,70,229,0.035)",
              }}
            />

            {/* 公转：同平面整层旋转 */}
            <div
              className={`pointer-events-none absolute inset-0 flex items-center justify-center [transform-style:preserve-3d] ${reduce ? "" : "hero-orbit-spin"}`}
            >
              <div className="relative aspect-square w-[90%] max-w-[min(100%,310px)] sm:max-w-[334px]">
                {TOP_NAV_ITEMS.map((item, i) => {
                  const Icon = item.icon;
                  return (
                    <OrbitSatellite key={item.to} angleDeg={orbitStepDeg * i} orbitRem={orbitRem} reduce={reduce}>
                      <Link
                        to={item.to}
                        className="flex h-full w-full items-center justify-center rounded-full text-indigo-600 outline-none ring-violet-400/40 transition hover:bg-white/35 hover:text-violet-700 focus-visible:ring-2"
                        aria-label={t(item.key)}
                      >
                        <Icon className="h-[1.2rem] w-[1.2rem] sm:h-7 sm:w-7" strokeWidth={2.2} />
                      </Link>
                    </OrbitSatellite>
                  );
                })}
              </div>
            </div>
          </div>

          {/* 中心 AI：反向倾斜正对镜头 */}
          <div
            className="absolute left-1/2 top-1/2 z-20 [transform-style:preserve-3d]"
            style={
              tilt
                ? { transform: `translate(-50%, -50%) translateZ(4.35rem) rotateX(-${tilt}deg)` }
                : { transform: "translate(-50%, -50%)" }
            }
          >
            <div
              className="relative h-[5.75rem] w-[5.75rem] overflow-hidden rounded-2xl ring-1 ring-white/30 sm:h-[6.5rem] sm:w-[6.5rem]"
              style={{ boxShadow: HERO_AI_CARD_SHADOW }}
            >
              <div
                className={`absolute inset-0 bg-[length:200%_200%] bg-[linear-gradient(125deg,#5b21b6_0%,#6366f1_22%,#0ea5e9_48%,#a855f7_72%,#5b21b6_100%)] ${reduce ? "" : "hero-ai-gradient-shift"}`}
              />
              <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_32%_18%,rgba(255,255,255,0.55)_0%,transparent_58%)]" />
              <div className="absolute inset-0 bg-[linear-gradient(195deg,rgba(244,114,182,0.28)_0%,transparent_42%,rgba(56,189,248,0.22)_100%)]" />
              <div className="absolute inset-0 bg-gradient-to-t from-indigo-950/4 via-transparent to-transparent" />
              <div className="absolute inset-0 rounded-2xl border border-white/35" />
              <div className="absolute inset-x-0 top-0 h-[46%] rounded-t-2xl bg-gradient-to-b from-white/36 to-transparent" />
              <div className="relative flex h-full w-full items-center justify-center">
                <Brain
                  className="absolute -right-0.5 -top-0.5 z-10 h-7 w-7 text-cyan-100 drop-shadow sm:h-8 sm:w-8"
                  strokeWidth={1.75}
                />
                <span className="relative z-10 text-[1.7rem] font-black tracking-tight text-white drop-shadow-[0_2px_12px_rgba(15,23,42,0.55)] sm:text-4xl">
                  AI
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type SparkPoint = { day: string; count: number };

const SPARK_W = 340;
const SPARK_H = 118;
const SPARK_ML = 32;
const SPARK_MR = 16;
const SPARK_MT = 12;
const SPARK_MB = 8;

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

function TrendSparkline({ points, tall = false }: { points: SparkPoint[]; tall?: boolean }) {
  const { t } = useI18n();
  const [hover, setHover] = useState<number | null>(null);

  const emptyH = tall ? "h-44 sm:h-52" : "h-40 sm:h-44";
  const chartMaxW = tall ? "max-w-[min(100%,22rem)] sm:max-w-[24rem]" : "max-w-[min(100%,20rem)]";

  if (!points.length) {
    return (
      <div className={`flex items-center justify-center text-sm text-slate-400 ${emptyH}`}>
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
  const chartPct = (x: number) => `${(x / SPARK_W) * 100}%`;

  return (
    <div className={`flex w-full flex-col items-center ${tall ? "py-1" : ""}`}>
      <div className={`relative w-full ${chartMaxW}`}>
        <svg
          viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
          className="mx-auto block h-auto w-full text-violet-600"
          role="img"
          aria-label={`${t("homeTrendChartTitle")}，${t("homeTrendFootSum")} ${formatCount(sum)}`}
        >
          <defs>
            <linearGradient id="home-trend-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(129 140 248)" stopOpacity="0.38" />
              <stop offset="55%" stopColor="rgb(167 139 250)" stopOpacity="0.14" />
              <stop offset="100%" stopColor="rgb(167 139 250)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="home-trend-stroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="rgb(99 102 241)" />
              <stop offset="100%" stopColor="rgb(139 92 246)" />
            </linearGradient>
            <filter id="home-trend-glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="1.8" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {yTicks.map((tick) => {
            const y = SPARK_MT + innerH - (tick / yMax) * innerH;
            return (
              <g key={tick}>
                <line
                  x1={SPARK_ML}
                  y1={y}
                  x2={SPARK_W - SPARK_MR}
                  y2={y}
                  stroke={tick === 0 ? "rgb(203 213 225)" : "rgb(226 232 240)"}
                  strokeWidth={tick === 0 ? 1.25 : 1}
                  strokeDasharray={tick === 0 ? undefined : "5 4"}
                />
                <text
                  x={SPARK_ML - 8}
                  y={y + 4}
                  textAnchor="end"
                  className="fill-slate-500 text-[10px] font-medium tabular-nums"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          <path d={area} fill="url(#home-trend-fill)" />
          <path
            d={line}
            fill="none"
            stroke="url(#home-trend-stroke)"
            strokeWidth="2.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#home-trend-glow)"
          />

          {active ? (
            <line
              x1={active.x}
              y1={SPARK_MT}
              x2={active.x}
              y2={baselineY}
              stroke="rgb(167 139 250)"
              strokeWidth="1.25"
              strokeDasharray="4 4"
              opacity={0.85}
            />
          ) : null}

          {coords.map((p) => {
            const on = hover === p.index;
            return (
              <g key={p.day}>
                {on ? (
                  <circle cx={p.x} cy={p.y} r={9} fill="rgb(167 139 250)" opacity={0.22} />
                ) : null}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={on ? 6 : 4.5}
                  fill={on ? "rgb(79 70 229)" : "rgb(124 58 237)"}
                  stroke="white"
                  strokeWidth={2.5}
                  className="transition-all duration-150"
                />
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={16}
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
            className="pointer-events-none absolute z-10 -translate-x-1/2 rounded-xl border border-violet-200/90 bg-white/95 px-3 py-2 text-center shadow-lg shadow-violet-200/50 backdrop-blur-sm"
            style={{
              left: chartPct(active.x),
              top: `${Math.max(4, (active.y / SPARK_H) * 100 - 22)}%`,
            }}
          >
            <p className="text-xs font-semibold text-slate-600">{formatSparkDayLabel(active.day)}</p>
            <p className="text-base font-bold tabular-nums text-violet-700">
              {formatCount(active.count)}
              <span className="ml-0.5 text-xs font-medium text-violet-500">{t("homeTrendUnitShort")}</span>
            </p>
          </div>
        ) : null}
      </div>

      <div className={`relative mt-2 h-5 w-full tabular-nums text-slate-500 ${chartMaxW}`}>
        {xLabelIdx.map((idx) => {
          const c = coords[idx];
          if (!c) return null;
          const edge = idx === 0 ? "-translate-x-0" : idx === points.length - 1 ? "-translate-x-full" : "-translate-x-1/2";
          return (
            <span
              key={points[idx]?.day ?? idx}
              className={`absolute top-0 text-xs font-medium sm:text-sm ${edge}`}
              style={{ left: chartPct(c.x) }}
            >
              {formatSparkDayShort(points[idx]?.day ?? "")}
            </span>
          );
        })}
      </div>
      <p className={`mt-1 text-center text-xs text-slate-400 ${chartMaxW}`}>{t("homeTrendYUnit")}</p>

      <div className={`mt-4 w-full space-y-3 text-center ${chartMaxW}`}>
        <p className="text-xs leading-relaxed text-slate-600 sm:text-sm">{t("homeTrendLegend")}</p>
        <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-2.5">
          <span className="rounded-full bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200/90 shadow-sm sm:px-3.5 sm:text-sm">
            {t("homeTrendFootSum")}{" "}
            <strong className="tabular-nums text-violet-700">{formatCount(sum)}</strong>
          </span>
          <span className="rounded-full bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200/90 shadow-sm sm:px-3.5 sm:text-sm">
            {t("homeTrendFootAvg")} <strong className="tabular-nums text-violet-700">{avg}</strong>
          </span>
          <span className="rounded-full bg-white/90 px-3 py-1.5 text-xs font-medium text-slate-600 ring-1 ring-slate-200/90 shadow-sm sm:px-3.5 sm:text-sm">
            {t("homeTrendFootPeak")}{" "}
            <strong className="tabular-nums text-violet-700">{formatCount(peak)}</strong>
          </span>
        </div>
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

export function HomePage() {
  const { t } = useI18n();
  const [news, setNews] = useState<ArticleFeedCard[]>([]);
  const [apps, setApps] = useState<ArticleFeedCard[]>([]);
  const [newsLanes, setNewsLanes] = useState<SourceLane[]>([]);
  const [appsLanes, setAppsLanes] = useState<SourceLane[]>([]);
  const [sourceFacets, setSourceFacets] = useState<
    Array<{ key: string; label: string; news_count: number; apps_count: number }>
  >([]);
  const [topCategories, setTopCategories] = useState<Array<{ label: string; count: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [subscribeErr, setSubscribeErr] = useState("");
  const [trendOverview, setTrendOverview] = useState<{
    sparkline: Array<{ day: string; count: number }>;
    apps_count: number;
    news_count: number;
    apps_growth_pct: number | null;
    news_growth_pct: number | null;
  } | null>(null);

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

  const mergedLanes = useMemo(() => mergeSourceLanes(newsLanes, appsLanes), [newsLanes, appsLanes]);

  const quickNav = useMemo(
    () => [
      { to: "/news", label: t("homeGoNewsRadar"), Icon: Newspaper, grad: "from-violet-600 to-indigo-600" },
      { to: "/apps", label: t("homeGoAppsRadar"), Icon: LayoutGrid, grad: "from-sky-500 to-blue-600" },
      { to: "/downloads", label: t("homePopularCat5Title"), Icon: Download, grad: "from-emerald-500 to-teal-600" },
    ],
    [t],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    const loadFeedFallback = async (feed: "news" | "apps", limit: number) => {
      const res = await publicApi.articlesFeed({
        feed,
        industry_slug: INDUSTRY,
        paginate_by: "heat",
        heat_page_size: limit,
        heat_max_ranked: limit * 3,
        published_within_days: 30,
      });
      return "items" in res && Array.isArray(res.items) ? res.items : [];
    };

    publicApi
      .homeDashboard({
        industry_slug: INDUSTRY,
        news_limit: 8,
        apps_limit: 10,
        published_within_days: 30,
      })
      .then(async (data) => {
        if (cancelled) return;
        let nextNews = data.news ?? [];
        let nextApps = data.apps ?? [];
        if (nextNews.length === 0) {
          try {
            nextNews = await loadFeedFallback("news", 8);
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
        setNews(nextNews);
        setApps(nextApps);
        setNewsLanes(data.news_source_lanes ?? []);
        setAppsLanes(data.apps_source_lanes ?? []);
        setSourceFacets(data.source_facets ?? []);
        setTopCategories(data.top_categories ?? []);
        setTrendOverview(data.trend ?? null);
      })
      .catch(async () => {
        if (cancelled) return;
        try {
          const [nextNews, nextApps] = await Promise.all([
            loadFeedFallback("news", 8),
            loadFeedFallback("apps", 10),
          ]);
          if (cancelled) return;
          setNews(nextNews);
          setApps(nextApps);
        } catch {
          if (!cancelled) {
            setNews([]);
            setApps([]);
          }
        }
        if (!cancelled) {
          setNewsLanes([]);
          setAppsLanes([]);
          setSourceFacets([]);
          setTopCategories([]);
          setTrendOverview(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const featured = news[0];
  const newsWall = news.slice(1, 5);
  const appLeaderboard = apps.slice(0, 6);
  const totalInWindow = (trendOverview?.news_count ?? 0) + (trendOverview?.apps_count ?? 0);

  const onSubscribe = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setSubscribeErr("");
    try {
      await publicApi.newsletterSubscribe(trimmed);
      setSent(true);
      setEmail("");
      window.setTimeout(() => {
        setSent(false);
      }, 4000);
    } catch (err) {
      const text = err instanceof Error && err.message ? err.message : t("newsletterErrorNetwork");
      setSubscribeErr(text);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="w-full space-y-5 lg:space-y-6">
      <section className="grid items-center gap-6 overflow-visible lg:grid-cols-[minmax(0,26rem)_1fr] lg:gap-6 lg:py-2 xl:grid-cols-[minmax(0,28rem)_1fr]">
        <div className="relative z-10 min-w-0 text-center lg:max-w-none lg:text-left">
          <h1 className="text-3xl font-bold leading-tight tracking-tight text-slate-900 sm:text-4xl lg:text-[2.1rem] lg:leading-snug xl:text-4xl">
            {t("homeMainHeroTitle")}
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-[15px] lg:mx-0 lg:text-base">
            {t("homeMainHeroDesc")}
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3 lg:justify-start">
            <Link
              to="/news"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-7 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-500/25 transition hover:brightness-105 active:scale-[0.99] sm:text-[15px]"
            >
              {t("homeMainHeroCta1")}
              <ChevronRight className="h-4 w-4 opacity-90" strokeWidth={2} />
            </Link>
            <Link
              to="/apps"
              className="inline-flex items-center gap-2 rounded-full border border-slate-300/90 bg-white px-7 py-3 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-violet-300 hover:text-violet-700 sm:text-[15px]"
            >
              {t("homeMainHeroCta2")}
            </Link>
          </div>
        </div>
        <div className="flex min-w-0 items-center justify-center px-2 py-2 sm:px-4 lg:px-6">
          <div className="w-full max-w-[min(100%,380px)] shrink-0 sm:max-w-[400px]">
            <HeroGraphic />
          </div>
        </div>
      </section>

      <section className="ui-card overflow-hidden p-4 sm:p-5">
        <div className="grid gap-5 lg:grid-cols-2 lg:items-stretch lg:gap-6">
          {!loading && trendOverview ? (
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-wider text-slate-400">{t("homeLiveStats")}</p>
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
                    <span className="text-sm font-semibold text-slate-400">/5</span>
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
                      const label =
                        f.label ||
                        HOME_SOURCE_LABELS[f.key as keyof typeof HOME_SOURCE_LABELS] ||
                        f.key;
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

              {topCategories.length > 0 ? (
                <>
                  <p className="mt-4 text-[10px] font-bold uppercase tracking-wider text-slate-400">{t("homeTopicsLabel")}</p>
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {topCategories.slice(0, 6).map((c) => (
                      <div
                        key={c.label}
                        className="rounded-lg border border-violet-100 bg-violet-50/90 px-2.5 py-2 ring-1 ring-violet-100/80"
                      >
                        <p className="line-clamp-2 text-[11px] font-semibold leading-snug text-violet-900">{c.label}</p>
                        <p className="mt-1 text-sm font-bold tabular-nums text-violet-700">{c.count}</p>
                      </div>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          ) : loading ? (
            <div className="flex min-h-[8rem] items-center justify-center text-sm text-slate-500">{t("homeLoading")}</div>
          ) : null}

          <div
            className={`flex min-w-0 flex-col ${!loading && trendOverview ? "border-t border-slate-100 pt-5 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0" : ""}`}
          >
            <p className="text-center text-sm font-bold text-slate-900 lg:text-left">{t("homeAiTrend")}</p>
            <div className="mt-3 flex flex-1 flex-col items-center rounded-2xl bg-gradient-to-b from-violet-50/90 via-white to-slate-50/80 px-3 py-4 ring-1 ring-violet-100/70 sm:px-4 sm:py-5">
              {loading ? (
                <div className="flex min-h-[10rem] flex-1 items-center justify-center text-sm text-slate-400 lg:min-h-[13rem]">
                  {t("homeLoading")}
                </div>
              ) : (
                <TrendSparkline points={trendOverview?.sparkline ?? []} tall />
              )}
            </div>
            <p className="mt-3 text-center text-xs leading-relaxed text-slate-500 sm:text-sm lg:text-left">
              {t("homeTrendChartTitle")} · {t("homeTrendDataNote")}
            </p>
          </div>
        </div>
      </section>

      <HomeSection
        title={t("homeSourceRadar")}
        subtitle={t("homeSourceRadarSub")}
        icon={<Radar className="h-5 w-5" strokeWidth={2} />}
      >
        {loading ? (
          <p className="text-sm text-slate-500">{t("homeLoading")}</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
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

      <div className="grid gap-6 lg:grid-cols-12 lg:gap-8">
        <div className="space-y-6 lg:col-span-8 lg:space-y-8">
          <HomeSection
            title={t("homeTodayFocus")}
            subtitle={t("homeNewsWallSub")}
            icon={<Flame className="h-5 w-5 text-orange-500" strokeWidth={2} />}
            action={featured ? { label: t("homeFeaturedCta"), to: `/resources/${featured.id}` } : undefined}
          >
            {loading ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : !featured ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <HomeArticleTile item={featured} variant="spotlight" />
            )}
          </HomeSection>

          <HomeSection title={t("homeNewsWall")} action={{ label: t("homeGoNewsRadar"), to: "/news" }}>
            {loading ? (
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

        <aside className="space-y-6 lg:col-span-4 lg:space-y-8">
          <HomeSection
            title={t("homePopularTools")}
            subtitle={t("homeAppsLeaderboardSub")}
            icon={<Wrench className="h-5 w-5 text-sky-600" strokeWidth={2} />}
            action={{ label: t("homeGoAppsRadar"), to: "/apps" }}
          >
            {loading ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : appLeaderboard.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <div className="ui-card divide-y divide-slate-100 overflow-hidden">
                {appLeaderboard.map((item, idx) => (
                  <HomeArticleTile key={item.id} item={item} variant="rank" rank={idx + 1} />
                ))}
              </div>
            )}
          </HomeSection>
        </aside>
      </div>

      <HomeSection title={t("homeQuickNav")}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {quickNav.map(({ to, label, Icon, grad }) => (
            <Link
              key={to}
              to={to}
              className="ui-card group flex items-center gap-3 rounded-xl p-4 transition hover:border-violet-300 hover:shadow-md"
            >
              <span
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${grad} text-white shadow-sm`}
              >
                <Icon className="h-5 w-5" strokeWidth={1.75} />
              </span>
              <span className="text-sm font-bold text-slate-900 group-hover:text-violet-700">{label}</span>
            </Link>
          ))}
        </div>
      </HomeSection>

      {HOME_NEWSLETTER_VISIBLE ? (
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
                if (subscribeErr) setSubscribeErr("");
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
