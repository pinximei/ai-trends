import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { IndustryWindLineChart } from "@/components/home/IndustryWindLineChart";
import { useI18n } from "@/i18n";

export type WindDayPoint = { day: string; count: number };

export type IndustryWindRow = {
  label: string;
  headline?: string;
  summary?: string;
  rank: number;
  momentum_pct: number;
  raw_momentum: number;
  article_count: number;
  prior_count: number;
  growth_pct: number | null;
  signal: "升温" | "稳定" | "降温" | "偏冷" | string;
  heat_avg: number;
  top_pick: { id: number; title: string; feed_kind: "news" | "apps" } | null;
  series_this_week?: WindDayPoint[];
  series_last_week?: WindDayPoint[];
};

export type IndustryWindData = {
  recent_days: number;
  compare_mode?: string;
  period_label?: string;
  this_week_start?: string;
  last_week_start?: string;
  industries: IndustryWindRow[];
  note?: string;
  source?: string;
};

export type IndustryWindViewMode = "rank" | "chart";

const VIEW_STORAGE_KEY = "aitrends_industry_wind_view_v1";

const SIGNAL_STYLE: Record<string, { bar: string; badge: string; text: string }> = {
  升温: {
    bar: "from-orange-500 to-rose-500",
    badge: "bg-orange-100 text-orange-800 ring-orange-200/80",
    text: "text-orange-700",
  },
  稳定: {
    bar: "from-violet-500 to-indigo-500",
    badge: "bg-violet-100 text-violet-800 ring-violet-200/80",
    text: "text-violet-700",
  },
  降温: {
    bar: "from-slate-400 to-slate-500",
    badge: "bg-slate-100 text-slate-600 ring-slate-200/80",
    text: "text-slate-600",
  },
  偏冷: {
    bar: "from-slate-200 to-slate-300",
    badge: "bg-slate-50 text-slate-400 ring-slate-200/80",
    text: "text-slate-400",
  },
};

function formatGrowth(pct: number | null): string {
  if (pct == null) return "—";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct}%`;
}

function rowHeadline(row: IndustryWindRow): string {
  return (row.headline || row.label || "").trim();
}

function readStoredView(): IndustryWindViewMode {
  try {
    const v = sessionStorage.getItem(VIEW_STORAGE_KEY);
    if (v === "chart" || v === "rank") return v;
  } catch {
    /* private mode */
  }
  return "rank";
}

type Props = {
  data: IndustryWindData | null;
  loading?: boolean;
};

export function IndustryWindPanel({ data, loading }: Props) {
  const { t } = useI18n();
  const [view, setView] = useState<IndustryWindViewMode>(() => readStoredView());

  useEffect(() => {
    try {
      sessionStorage.setItem(VIEW_STORAGE_KEY, view);
    } catch {
      /* ignore */
    }
  }, [view]);

  const hasChartSeries = Boolean(
    data?.industries?.some((r) => (r.series_this_week?.length ?? 0) > 0 || (r.series_last_week?.length ?? 0) > 0),
  );

  useEffect(() => {
    if (view === "chart" && !loading && data && !hasChartSeries) {
      setView("rank");
    }
  }, [view, loading, data, hasChartSeries]);

  return (
    <section id="industry-wind" className="ui-card scroll-mt-24 overflow-hidden p-5 sm:p-6">
      <div className="flex flex-wrap items-start gap-3 border-b border-slate-100 pb-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500 to-rose-600 text-white shadow-md">
          <TrendingUp className="h-5 w-5" strokeWidth={2.5} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-bold text-slate-900 sm:text-xl">{t("homeIndustryWindTitle")}</h2>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">
            {view === "chart" ? t("homeIndustryWindSubChart") : t("homeIndustryWindSub")}
          </p>
        </div>
        {!loading && data?.industries?.length ? (
          <div
            className="flex shrink-0 rounded-full border border-slate-200 bg-slate-50 p-0.5"
            role="tablist"
            aria-label={t("homeIndustryWindViewToggle")}
          >
            {(
              [
                { key: "rank" as const, label: t("homeIndustryWindViewRank") },
                { key: "chart" as const, label: t("homeIndustryWindViewChart") },
              ] as const
            ).map((opt) => (
              <button
                key={opt.key}
                type="button"
                role="tab"
                aria-selected={view === opt.key}
                disabled={opt.key === "chart" && !hasChartSeries}
                onClick={() => setView(opt.key)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition sm:text-sm ${
                  view === opt.key
                    ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/80"
                    : "text-slate-500 hover:text-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-slate-500">{t("homeLoading")}</p>
      ) : !data?.industries?.length ? (
        <p className="mt-4 text-sm text-slate-500">{t("homeIndustryWindEmpty")}</p>
      ) : view === "chart" ? (
        <div className="mt-5">
          <IndustryWindLineChart rows={data.industries} />
          {data.note ? <p className="mt-4 text-[11px] leading-relaxed text-slate-400">{data.note}</p> : null}
          <p className="mt-2 text-center text-[11px] text-slate-400">
            {data.period_label || `${t("homeIndustryWindPeriod")} ${data.recent_days} ${t("trendsPeriodDaysUnit")}`}
          </p>
        </div>
      ) : (
        <div className="mt-5 space-y-4">
          {data.industries.map((row) => {
            const style = SIGNAL_STYLE[row.signal] ?? SIGNAL_STYLE["稳定"];
            const barPct = Math.max(row.momentum_pct, row.article_count > 0 ? 8 : 0);
            const headline = rowHeadline(row);
            const key = `${row.rank}-${headline}`;
            return (
              <div
                key={key}
                className="rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 py-3 sm:px-4"
              >
                <div className="flex flex-wrap items-start gap-2 gap-y-1">
                  <span className="mt-0.5 w-6 shrink-0 text-center text-xs font-bold tabular-nums text-slate-400">
                    {row.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold leading-snug text-slate-900 sm:text-[15px]">{headline}</p>
                    {row.summary ? (
                      <p className="mt-1 text-xs leading-relaxed text-slate-600 sm:text-sm">{row.summary}</p>
                    ) : null}
                  </div>
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-[10px] font-bold ring-1 ${style.badge}`}>
                    {row.signal}
                  </span>
                  <span className={`w-full text-right text-xs font-semibold tabular-nums sm:ml-auto sm:w-auto ${style.text}`}>
                    {formatGrowth(row.growth_pct)}
                    <span className="mx-1 font-normal text-slate-300">·</span>
                    <span className="font-normal text-slate-500">
                      {t("homeIndustryWindThisWeek")} {row.article_count}
                      <span className="mx-1 text-slate-300">/</span>
                      {t("homeIndustryWindLastWeek")} {row.prior_count}
                    </span>
                  </span>
                </div>
                <div className="mt-2.5 flex items-center gap-3 pl-8">
                  <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-200/80">
                    <div
                      className={`h-full rounded-full bg-gradient-to-r ${style.bar} transition-all duration-500`}
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                  <span className="shrink-0 text-[11px] tabular-nums text-slate-500">
                    {row.heat_avg > 0 ? `${t("homeIndustryWindHeat")} ${row.heat_avg}` : "—"}
                  </span>
                </div>
                {row.top_pick ? (
                  <p className="mt-2 pl-8 text-xs text-slate-500">
                    <span className="text-slate-400">{t("homeIndustryWindExample")} </span>
                    <Link
                      to={`/resources/${row.top_pick.id}`}
                      className="font-medium text-violet-600 hover:underline"
                    >
                      {row.top_pick.title}
                    </Link>
                    <span className="mx-1 text-slate-300">·</span>
                    <Link
                      to={row.top_pick.feed_kind === "apps" ? "/apps" : "/news"}
                      className="text-violet-600 hover:underline"
                    >
                      {t("homeIndustryWindMore")}
                    </Link>
                  </p>
                ) : null}
              </div>
            );
          })}
          {data.note ? <p className="text-[11px] leading-relaxed text-slate-400">{data.note}</p> : null}
          <p className="text-center text-[11px] text-slate-400">
            {data.period_label || `${t("homeIndustryWindPeriod")} ${data.recent_days} ${t("trendsPeriodDaysUnit")}`}
          </p>
        </div>
      )}
    </section>
  );
}
