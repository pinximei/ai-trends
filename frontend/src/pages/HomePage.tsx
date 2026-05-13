import type { CSSProperties, FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Link } from "react-router-dom";
import {
  BarChart3,
  Bot,
  Brain,
  ChevronRight,
  Download,
  FileText,
  Mail,
  MessageCircle,
  Wrench,
} from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { useI18n } from "@/i18n";

const INDUSTRY = "ai";

/** 倾斜星环平面内的圆轨道半径（rem），与环尺寸一起调 */
const HERO_ORBIT_REM = 8.55;
const HERO_ORBIT_SEC = 52;
const HERO_RING_TILT_DEG = 58;

/** 中心 AI 块呼吸灯：与 framer-motion 关键帧同步 */
const HERO_AI_BREATH_SHADOW_IDLE =
  "0 26px 60px -10px rgba(49,46,129,0.58), 0 0 52px rgba(34,211,238,0.34), 0 0 28px rgba(167,139,250,0.22), inset 0 1px 0 rgba(255,255,255,0.42)";
const HERO_AI_BREATH_SHADOW_PEAK =
  "0 38px 88px -4px rgba(49,46,129,0.72), 0 0 80px rgba(34,211,238,0.58), 0 0 52px rgba(167,139,250,0.42), inset 0 1px 0 rgba(255,255,255,0.5)";

function summarize(text: string, max: number) {
  const s = (text || "").trim();
  if (!s) return "—";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function thumbSurface(seed: string): CSSProperties {
  let n = 0;
  for (let i = 0; i < seed.length; i++) n += seed.charCodeAt(i);
  const hue = (n * 47) % 360;
  const hue2 = (hue + 38) % 360;
  return {
    background: `linear-gradient(135deg, hsl(${hue} 72% 52%) 0%, hsl(${hue2} 65% 42%) 100%)`,
  };
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  const days = Math.floor(h / 24);
  return `${days} 天前`;
}

function toolRating(seed: string): string {
  let n = 0;
  for (let i = 0; i < seed.length; i++) n += seed.charCodeAt(i);
  return (9 + (n % 8) / 10).toFixed(1);
}

/** 星环平面内：圆轨道 + 逆旋保持图标正向 */
function OrbitSatellite({
  angleDeg,
  orbitRem,
  orbitSec,
  reduce,
  children,
}: {
  angleDeg: number;
  orbitRem: number;
  orbitSec: number;
  reduce: boolean | null;
  children: ReactNode;
}) {
  return (
    <div
      className="absolute left-1/2 top-1/2 z-[6] h-0 w-0"
      style={{
        transform: `translate(-50%, -50%) rotate(${angleDeg}deg) translateY(-${orbitRem}rem)`,
      }}
    >
      <motion.div
        className="flex -translate-x-1/2 -translate-y-1/2"
        animate={reduce ? undefined : { rotate: -360 }}
        transition={{ duration: orbitSec, repeat: Infinity, ease: "linear" }}
      >
        <span className="pointer-events-auto relative flex h-11 w-11 items-center justify-center text-indigo-600 drop-shadow-[0_2px_12px_rgba(15,23,42,0.55)] sm:h-12 sm:w-12">
          {children}
        </span>
      </motion.div>
    </div>
  );
}

/**
 * 天体星环：圆环放在 rotateX 倾斜的 3D 平面上，透视下呈椭圆；
 * 整层 rotateZ 公转，肉眼即「绕中心转」。
 */
function HeroGraphic() {
  const reduce = useReducedMotion();
  const orbitSec = HERO_ORBIT_SEC;
  const orbitRem = HERO_ORBIT_REM;
  const tilt = reduce ? 0 : HERO_RING_TILT_DEG;

  return (
    <div
      data-testid="hero-graphic"
      className="relative mx-auto w-full max-w-[min(100%,392px)] shrink-0 overflow-visible px-0 py-0 sm:max-w-[416px] sm:px-0.5"
    >
      <div
        data-orbit-square
        className="relative isolate mx-auto aspect-square w-full max-w-[352px] overflow-visible [perspective:1000px] [perspective-origin:50%_38%] sm:max-w-[380px]"
      >
        {/* 背面大环境光（不倾斜） */}
        <div
          className="pointer-events-none absolute -inset-[18%] -z-[1] rounded-full bg-[radial-gradient(circle_at_50%_36%,rgba(167,139,250,0.42),rgba(125,211,252,0.16)_42%,rgba(99,102,241,0.08)_58%,transparent_72%)] blur-[52px]"
          aria-hidden
        />

        <div className="relative h-full w-full [transform-style:preserve-3d]">
          {/* 星环平面：圆 → 屏上椭圆 */}
          <div
            className="absolute inset-0 flex items-center justify-center [transform-style:preserve-3d]"
            style={tilt ? { transform: `rotateX(${tilt}deg)` } : undefined}
          >
            {/* 慢旋柔光（与环同平面） */}
            <motion.div
              data-testid="hero-halo-primary"
              className="pointer-events-none absolute aspect-square w-[90%] max-w-[min(100%,310px)] rounded-full sm:max-w-[334px]"
              aria-hidden
              style={{
                background:
                  "radial-gradient(circle at 32% 20%, rgba(255,255,255,0.58) 0%, rgba(186,230,253,0.28) 30%, rgba(99,102,241,0.16) 52%, transparent 76%)",
                boxShadow:
                  "0 0 72px 28px rgba(125,211,252,0.38), 0 0 120px 48px rgba(167,139,250,0.26), 0 0 160px 64px rgba(99,102,241,0.12), inset 0 0 56px rgba(255,255,255,0.32)",
              }}
              animate={reduce ? undefined : { rotate: 360 }}
              transition={{ duration: 88, repeat: Infinity, ease: "linear" }}
            />

            {/* 公转：同平面整层旋转，卫星在圆上 */}
            <motion.div
              className="pointer-events-none absolute inset-0 flex items-center justify-center [transform-style:preserve-3d]"
              animate={reduce ? undefined : { rotate: 360 }}
              transition={{ duration: orbitSec, repeat: Infinity, ease: "linear" }}
            >
              <div className="relative aspect-square w-[90%] max-w-[min(100%,310px)] sm:max-w-[334px]">
                <OrbitSatellite angleDeg={0} orbitRem={orbitRem} orbitSec={orbitSec} reduce={reduce}>
                  <Bot className="h-[1.2rem] w-[1.2rem] sm:h-7 sm:w-7" strokeWidth={2.2} />
                </OrbitSatellite>
                <OrbitSatellite angleDeg={90} orbitRem={orbitRem} orbitSec={orbitSec} reduce={reduce}>
                  <MessageCircle className="h-[1.2rem] w-[1.2rem] sm:h-7 sm:w-7" strokeWidth={2.2} />
                </OrbitSatellite>
                <OrbitSatellite angleDeg={180} orbitRem={orbitRem} orbitSec={orbitSec} reduce={reduce}>
                  <FileText className="h-[1.2rem] w-[1.2rem] sm:h-7 sm:w-7" strokeWidth={2.2} />
                </OrbitSatellite>
                <OrbitSatellite angleDeg={270} orbitRem={orbitRem} orbitSec={orbitSec} reduce={reduce}>
                  <BarChart3 className="h-[1.2rem] w-[1.2rem] sm:h-7 sm:w-7" strokeWidth={2.2} />
                </OrbitSatellite>
              </div>
            </motion.div>
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
            <motion.div
              className="relative h-[5.75rem] w-[5.75rem] overflow-hidden rounded-2xl ring-1 ring-white/30 sm:h-[6.5rem] sm:w-[6.5rem]"
              initial={{ scale: 1, boxShadow: HERO_AI_BREATH_SHADOW_IDLE }}
              animate={
                reduce
                  ? { scale: 1, boxShadow: HERO_AI_BREATH_SHADOW_IDLE }
                  : {
                      scale: [1, 1.1, 1],
                      boxShadow: [
                        HERO_AI_BREATH_SHADOW_IDLE,
                        HERO_AI_BREATH_SHADOW_PEAK,
                        HERO_AI_BREATH_SHADOW_IDLE,
                      ],
                    }
              }
              transition={
                reduce
                  ? { duration: 0 }
                  : { duration: 2.6, repeat: Infinity, ease: "easeInOut" }
              }
            >
              <motion.div
                className="absolute inset-0 bg-[length:200%_200%] bg-[linear-gradient(125deg,#5b21b6_0%,#6366f1_22%,#0ea5e9_48%,#a855f7_72%,#5b21b6_100%)]"
                animate={reduce ? undefined : { backgroundPosition: ["0% 0%", "100% 100%", "0% 0%"] }}
                transition={{ duration: 16, repeat: Infinity, ease: "linear" }}
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
            </motion.div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TrendSparkline() {
  return (
    <svg viewBox="0 0 280 100" className="h-36 w-full text-violet-500 sm:h-40" aria-hidden>
      <defs>
        <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgb(139 92 246)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="rgb(139 92 246)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0 78 C40 72 60 40 100 52 C140 64 160 28 200 38 C240 48 260 18 280 22 L280 100 L0 100 Z"
        fill="url(#trend-fill)"
      />
      <path
        d="M0 78 C40 72 60 40 100 52 C140 64 160 28 200 38 C240 48 260 18 280 22"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function HomePage() {
  const { t } = useI18n();
  const [news, setNews] = useState<ArticleFeedCard[]>([]);
  const [apps, setApps] = useState<ArticleFeedCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const popularCats = useMemo(
    () => [
      { to: "/news", titleKey: "homePopularCat1Title", subKey: "homePopularCat1Sub", Icon: Brain, grad: "from-violet-500 to-indigo-600" },
      { to: "/apps", titleKey: "homePopularCat2Title", subKey: "homePopularCat2Sub", Icon: Wrench, grad: "from-sky-500 to-blue-600" },
      { to: "/downloads", titleKey: "homePopularCat5Title", subKey: "homePopularCat5Sub", Icon: Download, grad: "from-emerald-500 to-teal-600" },
    ],
    [],
  );

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
        page_size: 10,
        published_within_days: 30,
      }),
    ])
      .then(([n, a]) => {
        if (cancelled) return;
        setNews(n.items ?? []);
        setApps(a.items ?? []);
      })
      .catch(() => {
        if (!cancelled) {
          setNews([]);
          setApps([]);
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
  const sideNews = news.slice(1, 4);
  const toolList = apps.slice(0, 5);

  const onSubscribe = (e: FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setSent(true);
    setEmail("");
    window.setTimeout(() => setSent(false), 3200);
  };

  return (
    <div className="w-full space-y-6 lg:space-y-8">
      {/* lg+：左主列 | 右栏（热门工具 + AI 趋势），大屏铺满 */}
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(260px,20rem)] lg:items-start lg:gap-x-12 xl:grid-cols-[minmax(0,1fr)_minmax(280px,22rem)] xl:gap-x-16 2xl:grid-cols-[minmax(0,1fr)_minmax(300px,24rem)] 2xl:gap-x-20">
        <div className="min-w-0 space-y-6 pr-0 lg:space-y-8 lg:pr-2">
          <section className="flex flex-col items-center gap-3 overflow-visible text-center sm:gap-4 lg:flex-row lg:items-center lg:gap-5 lg:text-left xl:gap-6">
            <div className="min-w-0 w-full shrink-0 lg:w-auto lg:max-w-lg lg:flex-none xl:max-w-xl">
              <h1 className="text-3xl font-bold leading-tight tracking-tight text-slate-900 sm:text-4xl lg:text-[2.1rem] lg:leading-snug xl:text-4xl">
                {t("homeMainHeroTitle")}
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-[15px] lg:text-base">
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
            <div className="flex min-h-0 w-full min-w-0 flex-1 items-center justify-center overflow-visible py-0 lg:min-h-0 lg:min-w-[340px] lg:flex-1 lg:justify-center">
              <div className="flex w-full min-w-0 max-w-full shrink-0 justify-center overflow-visible lg:w-full">
                <HeroGraphic />
              </div>
            </div>
          </section>

          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold tracking-tight text-slate-900 lg:text-xl">{t("homeTodayFocus")}</h2>
            </div>
            {loading ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : news.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <div className="grid gap-4 lg:grid-cols-12 lg:gap-5">
                {featured ? (
                  <Link
                    to={`/resources/${featured.id}`}
                    className="ui-card group overflow-hidden transition hover:shadow-lg lg:col-span-7"
                  >
                    <div className="grid gap-0 lg:grid-cols-2">
                      <div
                        className="relative h-36 w-full sm:h-40 lg:h-44"
                        style={thumbSurface(`${featured.id}-feat`)}
                      >
                        <span className="absolute left-3 top-3 rounded-lg bg-white/90 px-2 py-1 text-[11px] font-semibold text-violet-700 shadow-sm ring-1 ring-white/60">
                          {t("homeImportantTag")}
                        </span>
                        <span className="absolute inset-0 flex items-center justify-center text-4xl font-black text-white/30 sm:text-5xl">
                          {(featured.title || "?").slice(0, 1)}
                        </span>
                      </div>
                      <div className="flex flex-col justify-center p-4 sm:p-5">
                        <p className="line-clamp-2 text-lg font-bold leading-snug text-slate-900 group-hover:text-violet-700 sm:text-xl">
                          {featured.title}
                        </p>
                        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-slate-600">
                          {summarize(featured.summary, 160)}
                        </p>
                        <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-500">
                          <span className="rounded-lg bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
                            {featured.categories?.[0] ?? featured.platform_label ?? t("source")}
                          </span>
                          <span className="tabular-nums">{timeAgo(featured.published_at)}</span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ) : null}
                <div className="flex min-h-0 flex-col gap-3 lg:col-span-5">
                  {sideNews.map((item) => (
                    <Link
                      key={item.id}
                      to={`/resources/${item.id}`}
                      className="ui-card flex gap-3 p-3 transition hover:border-violet-200 hover:shadow-md sm:p-3.5"
                    >
                      <div
                        className="relative h-16 w-20 shrink-0 overflow-hidden rounded-lg ring-1 ring-black/5 sm:h-[4.5rem] sm:w-24"
                        style={thumbSurface(`${item.id}-side`)}
                      >
                        <span className="absolute inset-0 flex items-center justify-center text-lg font-bold text-white/90 sm:text-xl">
                          {(item.title || "?").slice(0, 1)}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1 py-0.5">
                        <p className="line-clamp-2 text-sm font-semibold leading-snug text-slate-900 sm:text-[15px]">{item.title}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                          <span className="font-medium text-violet-600">{item.platform_label || t("source")}</span>
                          <span>·</span>
                          <span className="tabular-nums">{timeAgo(item.published_at)}</span>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-4 text-lg font-bold tracking-tight text-slate-900 lg:text-xl">{t("homePopularCategories")}</h2>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-3 sm:gap-6 lg:gap-8">
              {popularCats.map(({ to, titleKey, subKey, Icon, grad }) => (
                <Link
                  key={titleKey}
                  to={to}
                  className="ui-card group flex min-h-[160px] flex-col items-center justify-center gap-4 rounded-2xl p-8 text-center shadow-sm transition hover:border-violet-300/80 hover:shadow-lg sm:min-h-[180px] sm:p-10"
                >
                  <span
                    className={`flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br ${grad} text-white shadow-lg ring-2 ring-white/30 transition group-hover:scale-[1.04] sm:h-20 sm:w-20`}
                  >
                    <Icon className="h-9 w-9 sm:h-10 sm:w-10" strokeWidth={1.75} />
                  </span>
                  <p className="text-lg font-bold text-slate-900 sm:text-xl">{t(titleKey)}</p>
                  <p className="max-w-xs text-sm leading-relaxed text-slate-500">{t(subKey)}</p>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <aside className="min-w-0 space-y-6 lg:sticky lg:top-24 2xl:top-28">
          <div className="ui-card overflow-hidden rounded-2xl p-5 shadow-md sm:p-6">
            <div className="mb-4 flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
              <h3 className="text-base font-bold text-slate-900">{t("homePopularTools")}</h3>
              <Link to="/apps" className="text-xs font-semibold text-violet-600 hover:underline sm:text-sm">
                {t("homeViewAll")}
              </Link>
            </div>
            {!loading && toolList.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <ol className="space-y-1">
                {toolList.map((item, idx) => (
                  <li key={item.id}>
                    <Link
                      to={`/resources/${item.id}`}
                      className="flex gap-4 rounded-xl p-2 transition hover:bg-slate-50 sm:p-3"
                    >
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-sm font-bold text-violet-700 ring-1 ring-violet-100">
                        {idx + 1}
                      </span>
                      <div
                        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-base font-bold text-white shadow-md ring-1 ring-white/20"
                        style={thumbSurface(`tool-${item.id}`)}
                      >
                        {(item.title || "?").slice(0, 1)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-slate-900 sm:text-[15px]">{item.title}</p>
                        <p className="mt-1 line-clamp-2 text-xs leading-snug text-slate-500 sm:text-[13px]">
                          {summarize(item.summary, 64)}
                        </p>
                        <p className="mt-2 text-sm font-bold tabular-nums text-amber-600">{toolRating(item.title)}</p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="ui-card overflow-hidden rounded-2xl p-5 shadow-md sm:p-6">
            <h3 className="text-base font-bold text-slate-900">{t("homeAiTrend")}</h3>
            <p className="mt-1 text-xs text-slate-500 sm:text-sm">{t("homeTrendChartTitle")}</p>
            <div className="mt-4 rounded-xl bg-slate-50/90 px-2 py-3 ring-1 ring-slate-100">
              <TrendSparkline />
            </div>
            <div className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-5 text-center">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{t("homeStatActiveTools")}</p>
                <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 sm:text-2xl">2,847</p>
                <p className="text-xs font-semibold text-emerald-600 sm:text-sm">+12.5% {t("homeStatGrowth")}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">{t("homeStatNewArticles")}</p>
                <p className="mt-1 text-xl font-bold tabular-nums text-slate-900 sm:text-2xl">18,920</p>
                <p className="text-xs font-semibold text-emerald-600 sm:text-sm">+8.2% {t("homeStatGrowth")}</p>
              </div>
            </div>
          </div>
        </aside>
      </div>

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
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("newsletterPlaceholder")}
            className="w-full min-w-0 rounded-full border border-white/30 bg-white py-2.5 pl-4 pr-4 text-sm text-slate-900 shadow-inner outline-none placeholder:text-slate-400 focus:ring-2 focus:ring-white/50"
            autoComplete="email"
          />
          <button
            type="submit"
            className="rounded-full bg-indigo-950/90 px-8 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-indigo-950 md:justify-self-end lg:px-10 lg:py-3 lg:text-[15px]"
          >
            {sent ? t("newsletterThanks") : t("homeSubscribeBarBtn")}
          </button>
        </form>
        <p className="px-5 pb-3 text-center text-[10px] text-white/70 sm:px-8">{t("newsletterHint")}</p>
      </section>
    </div>
  );
}
