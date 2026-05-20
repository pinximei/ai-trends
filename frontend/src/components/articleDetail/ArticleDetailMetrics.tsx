import type { ArticleDetail } from "@/api/public";
import { formatStarCount } from "@/articleCardVisual";
import type { DetailLayoutConfig } from "@/lib/articleDetailLayout";

type Props = {
  article: ArticleDetail;
  layout: DetailLayoutConfig;
  starsLabel: string;
  heatLabel: string;
  starsTodayTemplate: (n: string) => string;
};

export function ArticleDetailMetrics({ article, layout, starsLabel, heatLabel, starsTodayTemplate }: Props) {
  if (!layout.showMetrics) return null;

  const starsTotal = article.engagement_stars_total;
  const starsToday = article.engagement_stars_today;
  const heat = article.heat_score;

  if (layout.metricsMode === "stars" && starsTotal == null) return null;
  if (layout.metricsMode === "heat" && (heat == null || heat <= 0) && starsTotal == null) return null;

  return (
    <div
      className="ui-card grid gap-3 p-4 sm:grid-cols-2 sm:p-5"
      data-testid="resource-detail-metrics"
    >
      {layout.metricsMode === "stars" && starsTotal != null ? (
        <div className="rounded-lg border border-amber-100 bg-amber-50/60 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-900/80">{starsLabel}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-amber-950">
            ★ {formatStarCount(starsTotal)}
            {starsToday != null ? (
              <span className="ml-2 text-sm font-medium text-amber-800/90">
                {starsTodayTemplate(formatStarCount(starsToday))}
              </span>
            ) : null}
          </p>
        </div>
      ) : null}
      {layout.metricsMode === "heat" && heat != null && heat > 0 ? (
        <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{heatLabel}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{Math.round(heat)}</p>
        </div>
      ) : null}
      {layout.metricsMode === "heat" && starsTotal != null ? (
        <div className="rounded-lg border border-amber-100 bg-amber-50/50 px-4 py-3 sm:col-span-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-900/80">{starsLabel}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-amber-950">★ {formatStarCount(starsTotal)}</p>
        </div>
      ) : null}
    </div>
  );
}
