import { motion } from "framer-motion";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Suspense, lazy, useEffect, useState } from "react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { ExternalLink } from "lucide-react";
import { PageHero } from "@/components/PageHero";
import { formatConfidence, getLifecycleLabel, getTrendDisplay } from "@/lib/trendCopy";

const TrendTimelineChart = lazy(() =>
  import("@/components/TrendTimelineChart").then((m) => ({ default: m.TrendTimelineChart }))
);

type Detail = {
  trend_key: string;
  trend_score: number;
  confidence: number;
  lifecycle_stage: string;
  sample_size: number;
};

type Timeline = { points: { period_start: string; score: number }[] };
type Period = "day" | "week" | "month" | "quarter" | "year";
const periods: Period[] = ["day", "week", "month", "quarter", "year"];

export function TrendDetailPage() {
  const { trendKey = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const key = decodeURIComponent(trendKey);
  const { lang, t } = useI18n();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tl, setTl] = useState<Timeline | null>(null);
  const periodParam = searchParams.get("period") as Period | null;
  const period: Period = periodParam && periods.includes(periodParam) ? periodParam : "week";
  const from = searchParams.get("from") ?? "trends";
  const backTo = from === "inspirations" ? `/inspirations?period=${period}` : `/trends?period=${period}`;

  const periodLabel: Record<Period, string> =
    lang === "zh"
      ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }
      : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" };

  useEffect(() => {
    if (!key) return;
    Promise.all([
      apiGet<Detail>(`/api/v1/trends/${encodeURIComponent(key)}`, lang),
      apiGet<Timeline>(`/api/v1/trends/${encodeURIComponent(key)}/timeline?period=${period}`, lang),
    ]).then(([d, timeline]) => {
      setDetail(d);
      setTl(timeline);
    });
  }, [key, lang, period]);

  const data = tl?.points.map((p) => ({ x: p.period_start.slice(5), y: p.score })) ?? [];

  return (
    <div className="space-y-8">
      <Link to={backTo} className="text-sm text-rose-400 hover:underline">
        ← {from === "inspirations" ? t("navInspirations") : t("navTrends")}
      </Link>
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <PageHero
          title={getTrendDisplay(key, lang).title}
          subtitle={
            detail ? (
              <div className="space-y-2">
                <p className="font-mono text-xs text-slate-500">
                  {t("trendCodeLabel")}: {getTrendDisplay(key, lang).code}
                </p>
                <p>
                  {t("score")} {detail.trend_score} · {t("confidence")} {formatConfidence(detail.confidence, lang)} ·{" "}
                  {t("lifecyclePhase")} {getLifecycleLabel(detail.lifecycle_stage, lang)} · {t("sample")} {detail.sample_size}
                </p>
              </div>
            ) : lang === "zh" ? (
              "加载趋势详情中…"
            ) : (
              "Loading trend detail…"
            )
          }
        />
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="glass rounded-3xl p-6 lg:col-span-8">
          <h2 className="mb-4 text-lg font-semibold text-white">{t("timeline")}</h2>
          <div className="mb-4 flex flex-wrap gap-2">
            {periods.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setSearchParams({ period: p, from })}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  period === p ? "bg-violet-300 text-slate-950" : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
                }`}
              >
                {periodLabel[p]}
              </button>
            ))}
          </div>
          <div className="h-64">
            <Suspense fallback={<div className="h-full w-full animate-pulse rounded-xl bg-slate-800/40" />}>
              <TrendTimelineChart data={data} />
            </Suspense>
          </div>
        </div>

        <aside className="space-y-4 lg:col-span-4">
          <div className="rounded-2xl border border-cyan-500/25 bg-cyan-500/10 p-4">
            <div className="text-[11px] font-medium text-cyan-100/80">{t("score")}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-white">{detail?.trend_score ?? "—"}</div>
          </div>
          <div className="rounded-2xl border border-fuchsia-500/25 bg-fuchsia-500/10 p-4">
            <div className="text-[11px] font-medium text-fuchsia-100/80">{t("confidence")}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-white">
              {detail ? formatConfidence(detail.confidence, lang) : "—"}
            </div>
          </div>
          <div className="rounded-2xl border border-amber-500/25 bg-amber-500/10 p-4">
            <div className="text-[11px] font-medium text-amber-100/80">{t("sample")}</div>
            <div className="mt-1 text-2xl font-bold tabular-nums text-white">{detail?.sample_size ?? "—"}</div>
          </div>
        </aside>
      </div>

      <div className="rounded-2xl border border-amber-500/20 bg-amber-950/20 p-6 text-slate-300">
        <h2 className="mb-2 font-semibold text-amber-100">{t("nextStep")}</h2>
        <p className="text-sm leading-relaxed">
          {lang === "zh"
            ? "先提出一个可验证的假设，小范围试点两周，只盯一个核心指标，记录风险后再决定是否放大。"
            : "Form one falsifiable hypothesis, run a two-week pilot, track one metric, log risks before scaling."}
        </p>
      </div>

      <Link
        to={`/evidence/sig_001?from=${from}&period=${period}`}
        className="inline-flex items-center gap-2 text-rose-400 hover:underline"
      >
        <ExternalLink className="h-4 w-4" /> {t("evidence")} (demo)
      </Link>
    </div>
  );
}
