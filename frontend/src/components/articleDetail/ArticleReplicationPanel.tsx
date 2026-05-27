import type { ReplicationAnalysis } from "@/api/public/types";
import { replicationTierLabel } from "@/components/home/homeUtils";
import { useI18n } from "@/i18n";

const VERDICT_CLASS: Record<string, string> = {
  值得复刻: "bg-emerald-100 text-emerald-800 border-emerald-200",
  观望: "bg-amber-100 text-amber-800 border-amber-200",
  不建议: "bg-slate-100 text-slate-700 border-slate-200",
};

const SATURATION_CLASS: Record<string, string> = {
  红海: "bg-rose-100 text-rose-800 border-rose-200",
  竞争适中: "bg-amber-100 text-amber-800 border-amber-200",
  细分蓝海: "bg-emerald-100 text-emerald-800 border-emerald-200",
};

type Props = {
  analysis: ReplicationAnalysis;
  replicationTier?: string | null;
};

export function ArticleReplicationPanel({ analysis, replicationTier }: Props) {
  const { t } = useI18n();
  const tierLabel = replicationTierLabel(replicationTier);
  const verdictCls = VERDICT_CLASS[analysis.verdict] ?? VERDICT_CLASS["观望"];
  const hours = analysis.estimated_hours_label;
  const mp = analysis.market_position;
  const saturationCls = SATURATION_CLASS[mp?.market_saturation ?? ""] ?? SATURATION_CLASS["竞争适中"];

  return (
    <div className="space-y-5" data-testid="replication-analysis-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-lg border px-3 py-1 text-sm font-semibold ${verdictCls}`}>
          {t("replVerdict")}: {analysis.verdict}
        </span>
        <span className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-1 text-sm font-semibold text-sky-800">
          {t("replWorthScore")}: {analysis.worth_score}/10
        </span>
        <span className="rounded-lg border border-violet-200 bg-violet-50 px-3 py-1 text-sm font-semibold text-violet-800">
          {t("replDifficulty")}: {analysis.difficulty}
        </span>
        {tierLabel ? (
          <span className="rounded-lg border border-slate-200 bg-white px-3 py-1 text-sm font-medium text-slate-700">
            {t("replTier")}: {tierLabel}
          </span>
        ) : null}
      </div>

      {hours ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-slate-200/90 bg-slate-50/80 px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replHoursMvp")}</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{hours.mvp}</p>
          </div>
          <div className="rounded-xl border border-slate-200/90 bg-slate-50/80 px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replHoursProd")}</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">{hours.production}</p>
          </div>
        </div>
      ) : null}

      {analysis.value_summary ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replValue")}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{analysis.value_summary}</p>
        </div>
      ) : null}

      {analysis.tier_rationale ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replTierWhy")}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{analysis.tier_rationale}</p>
        </div>
      ) : null}

      {mp &&
      (mp.target_user ||
        mp.vertical_niche ||
        mp.market_saturation ||
        mp.competitors?.length ||
        mp.differentiation ||
        mp.monetization_hypothesis) ? (
        <div className="rounded-xl border border-slate-200/90 bg-white px-4 py-4">
          <h3 className="text-sm font-bold text-slate-900">{t("replMarketSection")}</h3>
          <div className="mt-3 space-y-3 text-sm text-slate-600">
            {mp.target_user ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replTargetUser")}</p>
                <p className="mt-1 leading-relaxed">{mp.target_user}</p>
              </div>
            ) : null}
            {mp.vertical_niche ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replVerticalNiche")}</p>
                <p className="mt-1 leading-relaxed">{mp.vertical_niche}</p>
              </div>
            ) : null}
            {mp.market_saturation ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replMarketSaturation")}</p>
                <span
                  className={`mt-1.5 inline-block rounded-lg border px-2.5 py-0.5 text-xs font-semibold ${saturationCls}`}
                >
                  {mp.market_saturation}
                </span>
              </div>
            ) : null}
            {mp.competitors?.length ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replCompetitors")}</p>
                <ul className="mt-2 space-y-2">
                  {mp.competitors.map((c) => (
                    <li key={c.name} className="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                      <span className="font-semibold text-slate-800">{c.name}</span>
                      {c.note ? <p className="mt-0.5 text-xs text-slate-500">{c.note}</p> : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {mp.differentiation ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replDifferentiation")}</p>
                <p className="mt-1 leading-relaxed">{mp.differentiation}</p>
              </div>
            ) : null}
            {mp.monetization_hypothesis ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replMonetization")}</p>
                <p className="mt-1 leading-relaxed">{mp.monetization_hypothesis}</p>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {analysis.ai_usage_steps?.length ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replAiUsage")}</h3>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-slate-600">
            {analysis.ai_usage_steps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}

      {analysis.tech_stack?.length ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replTechStack")}</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {analysis.tech_stack.map((s) => (
              <span
                key={s}
                className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {analysis.implementation_plan?.length ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replPlan")}</h3>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-slate-600">
            {analysis.implementation_plan.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}

      {analysis.implementation_details?.length ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replDetails")}</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {analysis.implementation_details.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <h3 className="text-sm font-bold text-slate-900">{t("replOpenSource")}</h3>
        {analysis.open_source?.has_support && analysis.open_source.projects?.length ? (
          <ul className="mt-2 space-y-2">
            {analysis.open_source.projects.map((p) => (
              <li key={`${p.name}-${p.url}`} className="rounded-lg border border-slate-200/80 bg-white px-3 py-2 text-sm">
                <span className="font-semibold text-slate-800">{p.name}</span>
                {p.role ? <span className="text-slate-500"> — {p.role}</span> : null}
                {p.url ? (
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block truncate text-xs text-violet-600 hover:underline"
                  >
                    {p.url}
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1.5 text-sm text-slate-500">{t("replOpenSourceNone")}</p>
        )}
        {analysis.open_source?.gaps ? (
          <p className="mt-2 text-xs text-slate-500">
            {t("replOpenSourceGaps")}: {analysis.open_source.gaps}
          </p>
        ) : null}
      </div>

      {analysis.risks?.length ? (
        <div>
          <h3 className="text-sm font-bold text-slate-900">{t("replRisks")}</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900/90">
            {analysis.risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
