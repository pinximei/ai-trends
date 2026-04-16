import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowUpRight, BookOpen, Flame, Layers, Sparkle, Zap } from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { EcosystemStrip } from "@/components/EcosystemStrip";
import { FeatureColumns } from "@/components/FeatureColumns";
import { HeroProductVisual } from "@/components/HeroProductVisual";
import { getTrendDisplay } from "@/lib/trendCopy";

const HomeTrendSparkline = lazy(() =>
  import("@/components/HomeTrendSparkline").then((m) => ({ default: m.HomeTrendSparkline }))
);

type Summary = {
  active_use_cases: number;
  new_apps: number;
  emerging_trends: number;
  updated_at: string | null;
};

type TrendRow = {
  trend_key: string;
  trend_score: number;
  confidence: number;
  sample_size: number;
};
type InspirationRow = {
  signal_id: string;
  title: string;
  source: string;
  trend_key: string;
  evidence_score: number;
};

type Timeline = { points: { period_start: string; score: number }[] };
type Period = "day" | "week" | "month" | "quarter" | "year";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06 } },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

const cardGradients = [
  "linear-gradient(90deg, rgba(34,211,238,0.35), rgba(168,85,247,0.15))",
  "linear-gradient(90deg, rgba(244,63,94,0.3), rgba(251,191,36,0.12))",
  "linear-gradient(90deg, rgba(52,211,153,0.25), rgba(34,211,238,0.12))",
  "linear-gradient(90deg, rgba(167,139,250,0.35), rgba(244,63,94,0.1))",
  "linear-gradient(90deg, rgba(251,191,36,0.3), rgba(52,211,153,0.1))",
];

export function Home() {
  const { lang, t } = useI18n();
  const [globalPeriod, setGlobalPeriod] = useState<Period>("week");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [trends, setTrends] = useState<TrendRow[]>([]);
  const [inspirations, setInspirations] = useState<InspirationRow[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [chartData, setChartData] = useState<{ d: string; s: number }[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const [s, tr, ins, cat] = await Promise.all([
          apiGet<Summary>("/api/v1/dashboard/summary", lang),
          apiGet<{ items: TrendRow[] }>("/api/v1/trends", lang),
          apiGet<{ items: InspirationRow[] }>("/api/v1/inspirations", lang),
          apiGet<{ items: string[] }>("/api/v1/categories", lang),
        ]);
        if (cancel) return;
        setSummary(s);
        setTrends(tr.items.slice(0, 5));
        setInspirations(ins.items.slice(0, 5));
        setCategories(cat.items);
        if (tr.items[0]) {
          const tl = await apiGet<Timeline>(`/api/v1/trends/${tr.items[0].trend_key}/timeline`, lang);
          if (!cancel) {
            setChartData(tl.points.map((p) => ({ d: p.period_start.slice(5), s: p.score })));
          }
        }
      } catch (e) {
        if (!cancel) setErr(e instanceof Error ? e.message : "error");
      }
    })();
    return () => {
      cancel = true;
    };
  }, [lang]);

  return (
    <motion.div variants={container} initial="hidden" animate="show" className="space-y-16 md:space-y-24">
      {/* Hero：左文案 + 右产品画板（参考优秀 SaaS 首屏） */}
      <motion.section variants={item} className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.4em] text-cyan-400/80">
            {lang === "zh" ? "Agent 趋势与灵感" : "Agent trends & signals"}
          </p>
          <h1 className="mt-4 text-4xl font-bold leading-[1.1] tracking-tight text-white sm:text-5xl lg:text-[3.25rem]">
            {lang === "zh" ? (
              <>
                给产品经理、开发者与投资人
                <br />
                的<span className="text-gradient">Agent 机会雷达</span>
              </>
            ) : (
              <>
                Find agent opportunities
                <br />
                <span className="text-gradient">without hunting across sources</span>
              </>
            )}
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-slate-400">
            {lang === "zh"
              ? "不用反复刷 GitHub、Product Hunt、HN。AISoul 自动汇总趋势、证据与热度变化，让你 5 分钟看清一个赛道。"
              : "Stop scanning scattered sources. AISoul aggregates trend shifts, evidence, and momentum so you can understand a track in minutes."}
          </p>
          {err && <p className="mt-4 text-sm text-rose-400">API: {err}</p>}
          <div className="mt-10 flex flex-wrap gap-4">
            <Link
              to="/trends"
              className="inline-flex items-center gap-2 rounded-full bg-cyan-400 px-8 py-3.5 text-sm font-semibold text-slate-950 shadow-[0_0_40px_rgba(34,211,238,0.35)] transition hover:scale-[1.03] hover:bg-cyan-300"
            >
              {t("ctaTrends")} <ArrowUpRight className="h-4 w-4" />
            </Link>
            <Link
              to="/inspirations"
              className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.04] px-8 py-3.5 text-sm font-medium text-slate-200 backdrop-blur transition hover:bg-white/10"
            >
              {t("ctaSignals")}
            </Link>
            <Link
              to={`/briefing?period=${globalPeriod}`}
              className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-8 py-3.5 text-sm font-medium text-cyan-100 transition hover:bg-cyan-400/20"
            >
              {t("ctaBriefing")}
            </Link>
          </div>
        </div>
        <HeroProductVisual />
      </motion.section>

      <motion.div variants={item}>
        <EcosystemStrip lang={lang} />
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
          <span className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-cyan-200/90">
            {t("trendsTracked")}: {trends.length || "—"}
          </span>
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-slate-300">
            {t("updatedAgo")}: {summary?.updated_at ? summary.updated_at.replace("T", " ").slice(0, 16) : "—"}
          </span>
        </div>
      </motion.div>

      <motion.div variants={item} className="space-y-6">
        <h2 className="text-center font-mono text-[10px] uppercase tracking-[0.35em] text-slate-500">
          {lang === "zh" ? "为何使用 AISoul" : "Why AISoul"}
        </h2>
        <FeatureColumns lang={lang} />
      </motion.div>

      <motion.section variants={item} className="space-y-4">
        <div className="flex items-end justify-between">
          <h2 className="text-xl font-semibold text-white">{lang === "zh" ? "功能入口" : "Feature gateways"}</h2>
          <span className="text-xs text-slate-500">{lang === "zh" ? "按任务进入，而非盲目浏览" : "Enter by task, not by random browsing"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-400">{lang === "zh" ? "全局周期：" : "Global period:"}</span>
          {(["day", "week", "month", "quarter", "year"] as Period[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setGlobalPeriod(p)}
              className={`rounded-full px-3 py-1 text-xs transition ${
                globalPeriod === p ? "bg-cyan-300 text-slate-950" : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
              }`}
            >
              {lang === "zh"
                ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }[p]
                : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" }[p]}
            </button>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {[
            {
              to: `/trends?period=${globalPeriod}`,
              icon: Layers,
              title: lang === "zh" ? "趋势分析" : "Trend analysis",
              desc: lang === "zh" ? "看方向是否值得投入：分数、置信度、样本量。" : "Decide investment direction with score, confidence, and sample size.",
              metricLabel: lang === "zh" ? "当前趋势" : "active trends",
              metricVal: trends.length,
              status: `${lang === "zh" ? "周期" : "Period"}: ${
                lang === "zh"
                  ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }[globalPeriod]
                  : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" }[globalPeriod]
              }`,
              tone: "from-cyan-500/20 to-transparent",
            },
            {
              to: `/inspirations?period=${globalPeriod}`,
              icon: Zap,
              title: lang === "zh" ? "灵感发现" : "Signal discovery",
              desc: lang === "zh" ? "先看新信号，再决定是否进入趋势池。" : "Scan fresh signals before promoting to tracked trends.",
              metricLabel: lang === "zh" ? "最新信号" : "fresh signals",
              metricVal: inspirations.length,
              status: `${lang === "zh" ? "周期" : "Period"}: ${
                lang === "zh"
                  ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }[globalPeriod]
                  : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" }[globalPeriod]
              }`,
              tone: "from-amber-500/20 to-transparent",
            },
            {
              to: "/categories",
              icon: Sparkle,
              title: lang === "zh" ? "分类浏览" : "Category browse",
              desc: lang === "zh" ? "按主题缩小范围，降低信息搜索成本。" : "Narrow down by topics and reduce search friction.",
              metricLabel: lang === "zh" ? "分类数量" : "categories",
              metricVal: categories.length,
              status: lang === "zh" ? "按主题聚合" : "Grouped by topics",
              tone: "from-fuchsia-500/20 to-transparent",
            },
            {
              to: "/methodology",
              icon: BookOpen,
              title: lang === "zh" ? "方法论说明" : "Methodology",
              desc: lang === "zh" ? "理解评分逻辑和边界，避免误读结论。" : "Understand scoring logic and boundaries to avoid misreads.",
              metricLabel: lang === "zh" ? "最近更新" : "last update",
              metricVal: summary?.updated_at ? summary.updated_at.slice(5, 10) : "—",
              status: lang === "zh" ? "可审计可追溯" : "Auditable & traceable",
              tone: "from-violet-500/20 to-transparent",
            },
          ].map((entry) => (
            <Link
              key={entry.to}
              to={entry.to}
              className={`glass glass-hover rounded-2xl bg-gradient-to-br ${entry.tone} p-5`}
            >
              <entry.icon className="h-5 w-5 text-cyan-200" />
              <h3 className="mt-3 text-lg font-semibold text-white">{entry.title}</h3>
              <p className="mt-2 text-sm text-slate-300">{entry.desc}</p>
              <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div className="rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-slate-300">
                  <span className="text-slate-500">{entry.metricLabel}</span>
                  <div className="mt-1 font-mono text-cyan-200">{entry.metricVal}</div>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/20 px-2 py-1 text-slate-300">
                  <span className="text-slate-500">{lang === "zh" ? "状态" : "status"}</span>
                  <div className="mt-1">{entry.status}</div>
                </div>
              </div>
              <span className="mt-3 inline-flex items-center gap-1 text-xs text-cyan-300">
                {lang === "zh" ? "进入" : "Open"} <ArrowUpRight className="h-3.5 w-3.5" />
              </span>
            </Link>
          ))}
        </div>
      </motion.section>

      {/* 数据面板：图表 + KPI */}
      <motion.div variants={item} className="grid gap-6 lg:grid-cols-12">
        <div className="neon-card lg:col-span-8">
          <div className="neon-card-inner">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-4">
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Sparkle className="h-4 w-4 shrink-0 text-amber-400" />
                  <span className="truncate">{trends[0] ? getTrendDisplay(trends[0].trend_key, lang).title : "—"}</span>
                </span>
                {trends[0] ? (
                  <span className="truncate pl-7 font-mono text-[10px] text-slate-500">{getTrendDisplay(trends[0].trend_key, lang).code}</span>
                ) : null}
              </span>
              <span className="shrink-0 rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-400">
                {lang === "zh" ? "迷你走势" : "Sparkline"}
              </span>
            </div>
            <div className="h-56 w-full sm:h-64">
              <Suspense fallback={<div className="h-full w-full animate-pulse rounded-xl bg-slate-800/40" />}>
                <HomeTrendSparkline data={chartData} />
              </Suspense>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4 lg:col-span-4">
          {[
            { icon: Layers, label: t("kpiActive"), val: summary?.active_use_cases ?? "—", hue: "from-cyan-500/30" },
            { icon: Flame, label: t("kpiEmerging"), val: summary?.emerging_trends ?? "—", hue: "from-orange-500/30" },
            { icon: ArrowUpRight, label: t("kpiApps"), val: summary?.new_apps ?? "—", hue: "from-emerald-500/30" },
          ].map((k) => (
            <div
              key={k.label}
              className={`glass glass-hover relative overflow-hidden rounded-2xl p-6 bg-gradient-to-br ${k.hue} to-transparent`}
            >
              <k.icon className="mb-3 h-6 w-6 text-slate-200" />
              <div className="text-3xl font-bold tabular-nums tracking-tight text-white">{k.val}</div>
              <div className="mt-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">{k.label}</div>
            </div>
          ))}
        </div>
      </motion.div>

      {/* 热门趋势：每卡顶部彩色条 + 留白 */}
      <motion.section variants={item}>
        <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-white">{t("topTrends")}</h2>
            <p className="mt-1 text-sm text-slate-500">
              {lang === "zh" ? "卡片顶部色带区分主题，悬停有光晕" : "Color bands distinguish topics; hover for glow"}
            </p>
          </div>
          <Link to="/trends" className="text-sm font-medium text-cyan-400 hover:underline">
            {t("explore")} →
          </Link>
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {(trends.length
            ? trends
            : Array.from({ length: 3 }, () => ({ trend_key: "", trend_score: 0, confidence: 0, sample_size: 0 }))
          ).map((row, i) => (
            <motion.div
              key={row.trend_key || `placeholder-${i}`}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              whileHover={{ y: -6 }}
            >
              {row.trend_key ? (
                <Link
                  to={`/trends/${encodeURIComponent(row.trend_key)}`}
                  className="group glass glass-hover block overflow-hidden rounded-2xl ring-1 ring-white/5"
                >
                  <div className="h-1.5 w-full" style={{ background: cardGradients[i % cardGradients.length] }} />
                  <div className="p-6">
                    <div className="text-lg font-semibold leading-snug text-cyan-50">{getTrendDisplay(row.trend_key, lang).title}</div>
                    <div className="mt-1 font-mono text-[11px] text-slate-500">{getTrendDisplay(row.trend_key, lang).code}</div>
                    <div className="mt-5 flex gap-6 border-t border-white/5 pt-4 font-mono text-xs text-slate-500">
                      <span>
                        {t("score")} <strong className="ml-1 text-lg text-white">{row.trend_score}</strong>
                      </span>
                      <span>
                        {t("sample")} <strong className="ml-1 text-lg text-white">{row.sample_size}</strong>
                      </span>
                    </div>
                  </div>
                </Link>
              ) : (
                <div className="glass block overflow-hidden rounded-2xl ring-1 ring-white/5">
                  <div className="h-1.5 w-full bg-gradient-to-r from-slate-700/40 to-transparent" />
                  <div className="space-y-4 p-6">
                    <div className="h-4 w-3/4 animate-pulse rounded bg-slate-700/50" />
                    <div className="h-4 w-1/2 animate-pulse rounded bg-slate-700/40" />
                    <p className="text-xs text-slate-500">{t("sampling")}…</p>
                  </div>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </motion.section>
    </motion.div>
  );
}
