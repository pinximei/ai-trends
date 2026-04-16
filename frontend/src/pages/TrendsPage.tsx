import { motion } from "framer-motion";
import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { LayoutGrid, TrendingUp } from "lucide-react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { PageHero } from "@/components/PageHero";
import { formatConfidence, getLifecycleLabel, getTrendDisplay } from "@/lib/trendCopy";

type TrendRow = {
  trend_key: string;
  trend_score: number;
  confidence: number;
  lifecycle_stage: string;
  sample_size: number;
};
type Period = "day" | "week" | "month" | "quarter" | "year";
const periods: Period[] = ["day", "week", "month", "quarter", "year"];

const cardBands = [
  "from-fuchsia-500/50 via-rose-500/30 to-transparent",
  "from-cyan-500/50 via-sky-500/30 to-transparent",
  "from-amber-500/50 via-orange-500/30 to-transparent",
  "from-violet-500/50 via-purple-500/30 to-transparent",
];

export function TrendsPage() {
  const { lang, t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<TrendRow[]>([]);
  const periodParam = searchParams.get("period") as Period | null;
  const period: Period = periodParam && periods.includes(periodParam) ? periodParam : "week";

  const periodLabel: Record<Period, string> =
    lang === "zh"
      ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }
      : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" };

  useEffect(() => {
    apiGet<{ items: TrendRow[] }>(`/api/v1/trends?period=${period}`, lang).then((d) => setItems(d.items));
  }, [lang, period]);

  return (
    <div className="space-y-10">
      <PageHero
        title={
          <span className="flex items-center gap-3">
            <LayoutGrid className="h-9 w-9 text-fuchsia-400/90" />
            {t("navTrends")}
          </span>
        }
        subtitle={
          lang === "zh"
            ? "追踪已成型的 Agent 方向：看分数、生命周期与样本规模，判断是否值得投入。"
            : "Track validated agent directions with score, lifecycle, and sample size to decide where to invest."
        }
        visual={
          <div className="flex gap-1.5 rounded-xl border border-white/10 bg-black/30 p-3">
            {[0.4, 0.7, 0.55, 0.85, 0.6].map((h, i) => (
              <div
                key={i}
                className="w-2 rounded-sm bg-gradient-to-t from-fuchsia-500/40 to-cyan-400/80"
                style={{ height: `${h * 48 + 12}px` }}
              />
            ))}
          </div>
        }
      />
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-cyan-500/25 bg-cyan-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-200/70">{t("trendsTracked")}</div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-white">{items.length}</div>
        </div>
        <div className="rounded-2xl border border-fuchsia-500/25 bg-fuchsia-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-fuchsia-200/70">
            {lang === "zh" ? "平均分数" : "avg score"}
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-white">
            {items.length ? (items.reduce((acc, it) => acc + it.trend_score, 0) / items.length).toFixed(1) : "—"}
          </div>
        </div>
        <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-4">
          <div className="text-[10px] font-mono uppercase tracking-widest text-amber-200/70">
            {lang === "zh" ? "高置信趋势" : "high confidence"}
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-white">{items.filter((it) => it.confidence >= 0.8).length}</div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">{lang === "zh" ? "时间范围：" : "Time range:"}</span>
        {periods.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setSearchParams({ period: p })}
            className={`rounded-full px-3 py-1 text-xs transition ${
              period === p ? "bg-cyan-300 text-slate-950" : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
            }`}
          >
            {periodLabel[p]}
          </button>
        ))}
      </div>
      {!items.length && (
        <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/10 p-4 text-sm text-cyan-100">
          {lang === "zh"
            ? "当前周期暂无可展示趋势，可切换到更长周期查看。"
            : "No trends available for this period yet. Try a longer period."}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {[
          lang === "zh" ? "用于路线规划" : "For roadmap planning",
          lang === "zh" ? "按分数排序" : "Sorted by score",
          lang === "zh" ? "点击看证据链" : "Open evidence path",
        ].map((chip) => (
          <span key={chip} className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300">
            {chip}
          </span>
        ))}
      </div>
      <p className="text-xs leading-relaxed text-slate-500">{t("trendListHint")}</p>
      <div className="rounded-2xl border border-cyan-500/15 bg-gradient-to-r from-slate-900/80 to-slate-900/40 p-4 backdrop-blur-sm">
        <div className="grid grid-cols-12 gap-2 text-[11px] font-medium tracking-wide text-slate-400">
          <div className="col-span-4 sm:col-span-5">{lang === "zh" ? "趋势名称" : "Trend"}</div>
          <div className="col-span-2">{lang === "zh" ? "阶段" : "Stage"}</div>
          <div className="col-span-2">{t("score")}</div>
          <div className="col-span-2">{t("confidence")}</div>
          <div className="col-span-1 sm:col-span-1">{t("sample")}</div>
          <div className="col-span-1 text-right">{lang === "zh" ? "详情" : "Open"}</div>
        </div>
      </div>
      <div className="space-y-3">
        {(items.length
          ? items
          : Array.from({ length: 6 }, () => ({
              trend_key: "",
              trend_score: 0,
              confidence: 0,
              lifecycle_stage: "",
              sample_size: 0,
            }))
        ).map((row, i) => (
          <motion.div
            key={row.trend_key || `placeholder-${i}`}
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.04 }}
            className="break-inside-avoid"
          >
            {row.trend_key ? (
              <Link
                to={`/trends/${encodeURIComponent(row.trend_key)}?period=${period}&from=trends`}
                className="group glass glass-hover block overflow-hidden rounded-2xl p-4 ring-1 ring-white/5 transition-all hover:ring-cyan-400/20"
              >
                <div className={`mb-3 h-1.5 bg-gradient-to-r ${cardBands[i % cardBands.length]}`} />
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
                  <div className="min-w-0 flex-1">
                    <div className="text-base font-semibold leading-snug text-white group-hover:text-cyan-50">
                      {getTrendDisplay(row.trend_key, lang).title}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-slate-500">
                      {t("trendCodeLabel")}: {getTrendDisplay(row.trend_key, lang).code}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2 sm:justify-end">
                    <span className="inline-flex items-center gap-1 rounded-full border border-fuchsia-500/30 bg-fuchsia-500/10 px-2.5 py-1 text-xs text-fuchsia-100">
                      <TrendingUp className="h-3 w-3 shrink-0 text-fuchsia-300" />
                      {getLifecycleLabel(row.lifecycle_stage, lang)}
                    </span>
                    <div className="flex items-baseline gap-1 font-mono text-sm tabular-nums">
                      <span className="text-[10px] text-slate-500">{t("score")}</span>
                      <span className="text-lg text-amber-200">{row.trend_score}</span>
                    </div>
                    <div className="flex items-baseline gap-1 font-mono text-sm tabular-nums text-slate-200">
                      <span className="text-[10px] text-slate-500">{t("confidence")}</span>
                      <span>{formatConfidence(row.confidence, lang)}</span>
                    </div>
                    <div className="flex items-baseline gap-1 font-mono text-sm tabular-nums text-slate-300">
                      <span className="text-[10px] text-slate-500">{t("sample")}</span>
                      <span>{row.sample_size}</span>
                    </div>
                    <span className="text-xl text-cyan-300 transition group-hover:translate-x-0.5 sm:pl-1">→</span>
                  </div>
                </div>
              </Link>
            ) : (
              <div className="glass block overflow-hidden rounded-2xl p-4">
                <div className="space-y-4">
                  <div className="h-4 w-2/3 animate-pulse rounded bg-slate-700/50" />
                  <div className="grid grid-cols-4 gap-2">
                    <div className="h-7 animate-pulse rounded bg-slate-700/40" />
                    <div className="h-7 animate-pulse rounded bg-slate-700/40" />
                    <div className="h-7 animate-pulse rounded bg-slate-700/40" />
                    <div className="h-7 animate-pulse rounded bg-slate-700/40" />
                  </div>
                </div>
                <div className="mt-2 text-xs text-slate-500">{t("sampling")}…</div>
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
