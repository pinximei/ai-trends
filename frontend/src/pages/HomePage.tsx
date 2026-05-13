import type { CSSProperties, FormEvent } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  BarChart3,
  Brain,
  Building2,
  ChevronRight,
  FileText,
  Github,
  Download,
  Mail,
  MessageCircle,
  Sparkles,
  Wrench,
} from "lucide-react";
import { publicApi, type ArticleFeedCard } from "@/api/public";
import { useI18n } from "@/i18n";

const INDUSTRY = "ai";

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

/** 设计稿右侧主视觉：中心发光立方体 + 四角浮动图标 */
function HeroGraphic() {
  const float = "absolute flex h-11 w-11 items-center justify-center rounded-xl bg-white/12 shadow-lg ring-1 ring-white/25 backdrop-blur-sm text-white/90";
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[420px]">
      <div className="absolute inset-[6%] rounded-full border border-dashed border-violet-300/25 bg-gradient-to-br from-violet-500/15 to-indigo-600/10 shadow-[0_0_60px_rgba(99,102,241,0.25)]" />
      <div className={`${float} left-[8%] top-[20%] animate-float`} style={{ animationDuration: "20s" }}>
        <Sparkles className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div className={`${float} right-[10%] top-[16%] animate-float2`} style={{ animationDuration: "24s" }}>
        <MessageCircle className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div className={`${float} left-[12%] bottom-[18%] animate-float2`} style={{ animationDuration: "22s" }}>
        <FileText className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div className={`${float} right-[8%] bottom-[22%] animate-float`} style={{ animationDuration: "19s" }}>
        <BarChart3 className="h-5 w-5" strokeWidth={1.75} />
      </div>
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <div className="relative flex h-36 w-36 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-500 via-indigo-600 to-sky-500 shadow-2xl ring-4 ring-white/25 sm:h-40 sm:w-40">
          <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-white/25 to-transparent" />
          <Brain className="absolute -right-2 -top-2 h-9 w-9 text-cyan-200/90 drop-shadow-md" strokeWidth={1.5} />
          <span className="relative text-3xl font-black tracking-tight text-white drop-shadow-md sm:text-4xl">AI</span>
        </div>
      </div>
    </div>
  );
}

function TrendSparkline() {
  return (
    <svg viewBox="0 0 280 100" className="h-24 w-full text-violet-500" aria-hidden>
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
      { to: "/news", titleKey: "homePopularCat3Title", subKey: "homePopularCat3Sub", Icon: Building2, grad: "from-rose-500 to-orange-500" },
      { to: "/news", titleKey: "homePopularCat4Title", subKey: "homePopularCat4Sub", Icon: Github, grad: "from-slate-600 to-slate-800" },
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
    <div className="min-w-0 space-y-10">
      {/* Hero：左文右图（设计稿 1.png） */}
      <section className="grid items-center gap-10 lg:grid-cols-2 lg:gap-12">
        <div>
          <h1 className="text-gradient text-3xl font-bold leading-tight tracking-tight sm:text-4xl lg:text-[2.35rem] lg:leading-[1.2]">
            {t("homeMainHeroTitle")}
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-relaxed text-slate-600 sm:text-[15px]">{t("homeMainHeroDesc")}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/news"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-500/25 transition hover:brightness-105 active:scale-[0.99]"
            >
              {t("homeMainHeroCta1")}
              <ChevronRight className="h-4 w-4 opacity-90" strokeWidth={2} />
            </Link>
            <Link
              to="/apps"
              className="inline-flex items-center gap-2 rounded-full border border-slate-300/90 bg-white px-6 py-2.5 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-violet-300 hover:text-violet-700"
            >
              {t("homeMainHeroCta2")}
            </Link>
          </div>
        </div>
        <HeroGraphic />
      </section>

      <div className="grid gap-8 lg:grid-cols-[1fr_300px] lg:items-start">
        <div className="min-w-0 space-y-10">
          {/* 今日焦点 */}
          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-slate-900">{t("homeTodayFocus")}</h2>
            </div>
            {loading ? (
              <p className="text-sm text-slate-500">{t("homeLoading")}</p>
            ) : news.length === 0 ? (
              <p className="text-sm text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <div className="grid gap-4 lg:grid-cols-5">
                {featured ? (
                  <Link
                    to={`/resources/${featured.id}`}
                    className="ui-card group overflow-hidden transition hover:shadow-lg lg:col-span-3"
                  >
                    <div className="grid gap-0 md:grid-cols-2">
                      <div className="relative aspect-[5/4] min-h-[200px] md:aspect-auto md:min-h-[240px]" style={thumbSurface(`${featured.id}-feat`)}>
                        <span className="absolute left-4 top-4 rounded-lg bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-violet-700 shadow-sm ring-1 ring-white/60">
                          {t("homeImportantTag")}
                        </span>
                        <span className="absolute inset-0 flex items-center justify-center text-5xl font-black text-white/30">
                          {(featured.title || "?").slice(0, 1)}
                        </span>
                      </div>
                      <div className="flex flex-col justify-center p-5 sm:p-6">
                        <p className="line-clamp-2 text-lg font-bold leading-snug text-slate-900 group-hover:text-violet-700">{featured.title}</p>
                        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-slate-600">{summarize(featured.summary, 160)}</p>
                        <div className="mt-4 flex flex-wrap gap-3 text-xs text-slate-500">
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                            {featured.categories?.[0] ?? featured.platform_label ?? t("source")}
                          </span>
                          <span className="tabular-nums">{timeAgo(featured.published_at)}</span>
                        </div>
                      </div>
                    </div>
                  </Link>
                ) : null}
                <div className="flex min-h-0 flex-col gap-3 lg:col-span-2">
                  {sideNews.map((item) => (
                    <Link
                      key={item.id}
                      to={`/resources/${item.id}`}
                      className="ui-card flex gap-3 p-3 transition hover:border-violet-200 hover:shadow-md sm:p-3.5"
                    >
                      <div
                        className="relative h-20 w-24 shrink-0 overflow-hidden rounded-lg ring-1 ring-black/5"
                        style={thumbSurface(`${item.id}-side`)}
                      >
                        <span className="absolute inset-0 flex items-center justify-center text-xl font-bold text-white/90">
                          {(item.title || "?").slice(0, 1)}
                        </span>
                      </div>
                      <div className="min-w-0 flex-1 py-0.5">
                        <p className="line-clamp-2 text-sm font-semibold leading-snug text-slate-900">{item.title}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
                          <span className="text-violet-600">{item.platform_label || t("source")}</span>
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

          {/* 热门分类 */}
          <section>
            <h2 className="mb-4 text-lg font-bold text-slate-900">{t("homePopularCategories")}</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
              {popularCats.map(({ to, titleKey, subKey, Icon, grad }) => (
                <Link
                  key={titleKey}
                  to={to}
                  className="ui-card flex flex-col items-center gap-2 rounded-xl p-4 text-center transition hover:border-violet-200 hover:shadow-md"
                >
                  <span
                    className={`flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br ${grad} text-white shadow-md`}
                  >
                    <Icon className="h-6 w-6" strokeWidth={1.75} />
                  </span>
                  <p className="text-sm font-semibold text-slate-900">{t(titleKey)}</p>
                  <p className="text-[11px] text-slate-500">{t(subKey)}</p>
                </Link>
              ))}
            </div>
          </section>
        </div>

        {/* 右侧栏 */}
        <aside className="min-w-0 space-y-6 lg:sticky lg:top-24">
          <div className="ui-card overflow-hidden p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold text-slate-900">{t("homePopularTools")}</h3>
              <Link to="/apps" className="text-xs font-medium text-violet-600 hover:underline">
                {t("homeViewAll")}
              </Link>
            </div>
            {!loading && toolList.length === 0 ? (
              <p className="text-xs text-slate-500">{t("homeEmpty")}</p>
            ) : (
              <ol className="space-y-3">
                {toolList.map((item, idx) => (
                  <li key={item.id}>
                    <Link to={`/resources/${item.id}`} className="flex gap-3 rounded-lg p-1.5 transition hover:bg-slate-50">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-slate-100 text-xs font-bold text-violet-600">
                        {idx + 1}
                      </span>
                      <div
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white shadow-inner"
                        style={thumbSurface(`tool-${item.id}`)}
                      >
                        {(item.title || "?").slice(0, 1)}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
                        <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">{summarize(item.summary, 48)}</p>
                        <p className="mt-1 text-xs font-semibold text-amber-600">{toolRating(item.title)}</p>
                      </div>
                    </Link>
                  </li>
                ))}
              </ol>
            )}
          </div>

          <div className="ui-card overflow-hidden p-4 shadow-sm">
            <h3 className="text-sm font-bold text-slate-900">{t("homeAiTrend")}</h3>
            <p className="mt-1 text-xs text-slate-500">{t("homeTrendChartTitle")}</p>
            <div className="mt-3 rounded-xl bg-slate-50/90 px-2 py-2 ring-1 ring-slate-100">
              <TrendSparkline />
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4 text-center">
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{t("homeStatActiveTools")}</p>
                <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">2,847</p>
                <p className="text-xs font-medium text-emerald-600">+12.5% {t("homeStatGrowth")}</p>
              </div>
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{t("homeStatNewArticles")}</p>
                <p className="mt-1 text-lg font-bold tabular-nums text-slate-900">18,920</p>
                <p className="text-xs font-medium text-emerald-600">+8.2% {t("homeStatGrowth")}</p>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* 通栏订阅（设计稿底部渐变条；首页不显示右下角浮动条） */}
      <section className="overflow-hidden rounded-2xl bg-gradient-to-r from-violet-600 via-indigo-600 to-sky-600 p-[1px] shadow-lg">
        <form
          onSubmit={onSubscribe}
          className="grid gap-4 rounded-2xl bg-gradient-to-r from-violet-600/95 via-indigo-600/95 to-sky-600/95 px-5 py-6 sm:px-8 sm:py-7 md:grid-cols-[minmax(0,1fr)_minmax(0,18rem)_auto] md:items-center md:gap-6"
        >
          <div className="flex min-w-0 items-start gap-3 text-white md:items-center">
            <span className="mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/25 md:mt-0">
              <Mail className="h-5 w-5" strokeWidth={2} />
            </span>
            <p className="min-w-0 text-sm font-medium leading-relaxed md:text-[15px]">{t("homeSubscribeBarTitle")}</p>
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
            className="rounded-full bg-indigo-950/90 px-8 py-2.5 text-sm font-semibold text-white shadow-md transition hover:bg-indigo-950 md:justify-self-end"
          >
            {sent ? t("newsletterThanks") : t("homeSubscribeBarBtn")}
          </button>
        </form>
        <p className="px-5 pb-3 text-center text-[10px] text-white/70 sm:px-8">{t("newsletterHint")}</p>
      </section>
    </div>
  );
}
