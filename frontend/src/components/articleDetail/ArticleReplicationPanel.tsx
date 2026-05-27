import type { ReplicationAnalysis } from "@/api/public/types";
import { replicationTierLabel } from "@/components/home/homeUtils";
import { formatPhaseHours, normalizeVerdict } from "@/lib/replication";
import { useI18n } from "@/i18n";

const VERDICT_CLASS: Record<string, string> = {
  高价值: "bg-emerald-100 text-emerald-800 border-emerald-200",
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
  const verdict = normalizeVerdict(analysis.verdict);
  const verdictCls = VERDICT_CLASS[verdict] ?? VERDICT_CLASS["观望"];
  const hours = analysis.estimated_hours_label;
  const mp = analysis.market_position;
  const saturationCls = SATURATION_CLASS[mp?.market_saturation ?? ""] ?? SATURATION_CLASS["竞争适中"];
  const phases = analysis.phases ?? [];

  return (
    <div className="space-y-6" data-testid="replication-analysis-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-lg border px-3 py-1 text-sm font-semibold ${verdictCls}`}>
          {t("replVerdict")}: {verdict}
        </span>
        <span className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-1 text-sm font-semibold text-sky-800">
          {t("replWorthScore")}: {analysis.worth_score}/10
        </span>
        {hours?.mvp && hours.mvp !== "未估算" ? (
          <span className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-800">
            {t("replHoursMvp")}: {hours.mvp}
          </span>
        ) : null}
        {analysis.mvp_weeks_label ? (
          <span className="rounded-lg border border-emerald-100 bg-white px-3 py-1 text-xs font-medium text-emerald-800">
            {analysis.mvp_weeks_label}
          </span>
        ) : null}
        {tierLabel ? (
          <span className="rounded-lg border border-slate-200 bg-white px-3 py-1 text-sm font-medium text-slate-600">
            {t("replTier")}: {tierLabel}
          </span>
        ) : null}
      </div>

      {analysis.value_summary ? (
        <div className="rounded-xl border border-sky-100 bg-sky-50/60 px-4 py-3">
          <h3 className="text-sm font-bold text-slate-900">{t("replValue")}</h3>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-700">{analysis.value_summary}</p>
        </div>
      ) : null}

      {phases.length > 0 ? (
        <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/40 px-4 py-4">
          <h3 className="text-sm font-bold text-slate-900">{t("replEffortSection")}</h3>
          {analysis.team_shape || analysis.assumptions ? (
            <p className="mt-1 text-xs text-slate-600">
              {[analysis.team_shape, analysis.assumptions].filter(Boolean).join(" · ")}
            </p>
          ) : null}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[28rem] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-emerald-200/80 text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="py-2 pr-3">{t("replPhaseName")}</th>
                  <th className="py-2 pr-3">{t("replPhaseHours")}</th>
                  <th className="py-2">{t("replPhaseDeliverable")}</th>
                </tr>
              </thead>
              <tbody>
                {phases.map((p, i) => (
                  <tr key={`${p.name}-${i}`} className="border-b border-emerald-100/80 align-top">
                    <td className="py-2.5 pr-3 font-medium text-slate-800">{p.name}</td>
                    <td className="py-2.5 pr-3 tabular-nums text-emerald-800">{formatPhaseHours(p)}</td>
                    <td className="py-2.5 text-slate-600">{p.deliverable}</td>
                  </tr>
                ))}
                {hours?.mvp && hours.mvp !== "未估算" ? (
                  <tr className="font-semibold text-slate-900">
                    <td className="py-2.5 pr-3">{t("replPhaseTotal")}</td>
                    <td className="py-2.5 pr-3 tabular-nums text-emerald-800">{hours.mvp}</td>
                    <td className="py-2.5 text-slate-600">{hours.production !== "未估算" ? hours.production : "—"}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {analysis.effort_summary ? (
            <p className="mt-2 text-xs text-slate-500">{analysis.effort_summary}</p>
          ) : null}
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
            {mp.monetization_hypothesis ? (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">{t("replMonetization")}</p>
                <p className="mt-1 leading-relaxed font-medium text-slate-800">{mp.monetization_hypothesis}</p>
              </div>
            ) : null}
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
          </div>
        </div>
      ) : null}

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

      {analysis.difficulty ? (
        <p className="text-xs text-slate-500">
          {t("replDifficulty")}: {analysis.difficulty}
          {analysis.platform_fit && analysis.platform_fit !== "unknown"
            ? ` · ${t("replPlatform")}: ${analysis.platform_fit}`
            : ""}
        </p>
      ) : null}

      {analysis.implementation_plan?.length ? (
        <details className="rounded-lg border border-slate-200/80 bg-slate-50/50 px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">{t("replPlan")}</summary>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-slate-600">
            {analysis.implementation_plan.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ol>
        </details>
      ) : null}

      {analysis.tech_stack?.length ? (
        <details className="rounded-lg border border-slate-200/80 bg-slate-50/50 px-3 py-2">
          <summary className="cursor-pointer text-sm font-semibold text-slate-700">{t("replTechStack")}</summary>
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
        </details>
      ) : null}

      {analysis.tier_rationale ? (
        <p className="text-xs text-slate-500">
          {t("replTierWhy")}: {analysis.tier_rationale}
        </p>
      ) : null}
    </div>
  );
}
