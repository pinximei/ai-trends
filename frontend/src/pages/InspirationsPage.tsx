import { motion } from "framer-motion";
import { Link, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { Zap } from "lucide-react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { PageHero } from "@/components/PageHero";
import { getTrendDisplay } from "@/lib/trendCopy";

type Item = {
  signal_id: string;
  title: string;
  source: string;
  trend_key: string;
  evidence_score: number;
};
type Period = "day" | "week" | "month" | "quarter" | "year";
const periods: Period[] = ["day", "week", "month", "quarter", "year"];

const cardAccents = [
  "border-t-fuchsia-500/60",
  "border-t-cyan-500/60",
  "border-t-amber-500/60",
  "border-t-violet-500/60",
];

export function InspirationsPage() {
  const { lang, t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<Item[]>([]);
  const periodParam = searchParams.get("period") as Period | null;
  const period: Period = periodParam && periods.includes(periodParam) ? periodParam : "day";

  const periodLabel: Record<Period, string> =
    lang === "zh"
      ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }
      : { day: "Day", week: "Week", month: "Month", quarter: "Quarter", year: "Year" };

  useEffect(() => {
    apiGet<{ items: Item[] }>(`/api/v1/inspirations?period=${period}`, lang).then((d) => setItems(d.items));
  }, [lang, period]);

  return (
    <div className="space-y-10">
      <PageHero
        title={
          <span className="flex items-center gap-3">
            <Zap className="h-9 w-9 text-amber-400" />
            {t("navInspirations")}
          </span>
        }
        subtitle={
          lang === "zh"
            ? "捕捉最新生态信号：先看来源与证据分，再决定是否进入趋势池。"
            : "Catch fresh ecosystem signals first, then decide whether to move them into tracked trends."
        }
        visual={
          <div className="rounded-xl border border-amber-500/20 bg-gradient-to-br from-amber-500/10 to-transparent px-4 py-3">
            <div className="text-[10px] font-mono uppercase tracking-widest text-amber-200/70">signals</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-bold tabular-nums text-white">{items.length}</span>
              <span className="text-xs text-slate-500">{lang === "zh" ? "条" : "items"}</span>
            </div>
          </div>
        }
      />
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400">
          {lang === "zh" ? "信号流说明" : "signal stream"}
        </div>
        <p className="mt-2 text-sm text-slate-300">
          {lang === "zh"
            ? "每小时更新：来自公开生态的新发现。看到高分信号，可直接跳转趋势或原始证据。"
            : "Updated hourly with fresh discoveries from public ecosystems. Promote high-score signals to trends or open raw evidence."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">{lang === "zh" ? "时间范围：" : "Time range:"}</span>
        {periods.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setSearchParams({ period: p })}
            className={`rounded-full px-3 py-1 text-xs transition ${
              period === p ? "bg-amber-300 text-slate-950" : "border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10"
            }`}
          >
            {periodLabel[p]}
          </button>
        ))}
      </div>
      {!items.length && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
          {lang === "zh"
            ? "当前周期暂无新信号，可切换到更长周期查看。"
            : "No fresh signals in this period yet. Try a longer period."}
        </div>
      )}
      <div className="space-y-3">
        {(items.length
          ? items
          : Array.from({ length: 4 }, () => ({
              signal_id: "",
              title: "",
              source: "",
              trend_key: "",
              evidence_score: 0,
            }))
        ).map((it, i) => (
          <motion.div
            key={it.signal_id || `placeholder-${i}`}
            initial={{ opacity: 0, rotateX: -8 }}
            animate={{ opacity: 1, rotateX: 0 }}
            transition={{ delay: i * 0.06 }}
            className={`glass glass-hover rounded-2xl border-l-4 ${cardAccents[i % cardAccents.length].replace("border-t", "border-l")} p-6`}
            style={{ transformStyle: "preserve-3d", perspective: 1000 }}
            whileHover={{ rotateY: 2, rotateX: -2 }}
          >
            {it.signal_id ? (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-lg font-medium text-white">{it.title}</div>
                  <div className="text-xs text-slate-500">{lang === "zh" ? "最新" : "latest"}</div>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-300">
                  <span className="rounded-full border border-white/10 bg-black/20 px-2 py-0.5">{it.source}</span>
                  <span className="rounded-full border border-white/10 bg-black/20 px-2 py-0.5 font-mono text-xs text-slate-300">
                    ID {it.signal_id}
                  </span>
                  <span className="font-mono text-amber-300">
                    {lang === "zh" ? "证据分" : "Score"} {it.evidence_score.toFixed(2)}
                  </span>
                  <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-cyan-200">
                    {lang === "zh" ? "新信号" : "fresh"}
                  </span>
                </div>
                <div className="mt-3 rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-xs text-slate-400">
                  <span className="text-slate-500">{t("relatedTrend")}: </span>
                  <span className="font-medium text-cyan-100/90">{getTrendDisplay(it.trend_key, lang).title}</span>
                  <span className="ml-2 font-mono text-[10px] text-slate-600">({it.trend_key})</span>
                </div>
                <div className="mt-4 flex gap-3 text-sm">
                  <Link
                    className="text-rose-300 hover:underline"
                    to={`/trends/${encodeURIComponent(it.trend_key)}?period=${period}&from=inspirations`}
                  >
                    {lang === "zh" ? "打开趋势详情" : "Open trend"}
                  </Link>
                  <Link
                    className="text-cyan-300 hover:underline"
                    to={`/evidence/${encodeURIComponent(it.signal_id)}?from=inspirations&period=${period}`}
                  >
                    {t("evidence")}
                  </Link>
                </div>
              </>
            ) : (
              <div className="space-y-4">
                <div className="h-4 w-3/4 animate-pulse rounded bg-slate-700/50" />
                <div className="h-4 w-1/2 animate-pulse rounded bg-slate-700/40" />
                <div className="text-xs text-slate-500">{t("sampling")}…</div>
              </div>
            )}
          </motion.div>
        ))}
      </div>
    </div>
  );
}
