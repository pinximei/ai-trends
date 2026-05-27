import type { ReplicationAnalysis, ReplicationPhase } from "@/api/public/types";

const POSITIVE_VERDICTS = new Set(["高价值", "值得复刻", "值得做", "高变现"]);

/** 与后端 monetization_hypothesis_is_substantive 对齐 */
const GENERIC_MONETIZATION_HYPOTHESES = new Set([
  "订阅或买断；优先验证 20 个目标用户付费意愿后再扩功能",
]);

function monetizationHypothesisIsSubstantive(hypothesis: string | undefined): boolean {
  const h = (hypothesis || "").trim();
  if (h.length < 16) return false;
  if (GENERIC_MONETIZATION_HYPOTHESES.has(h)) return false;
  if (h.startsWith("围绕「") && h.includes("垂直场景") && h.length < 48) return false;
  return true;
}

export function normalizeVerdict(verdict: string | undefined): string {
  const v = (verdict || "").trim();
  if (v === "值得复刻" || v === "值得做" || v === "高变现") return "高价值";
  return v;
}

/** 变现评估字段达标（不含工时 phases） */
export function hasValueAssessment(
  analysis: ReplicationAnalysis | null | undefined,
  minWorth = 7,
): boolean {
  if (!analysis?.verdict?.trim()) return false;
  const verdict = normalizeVerdict(analysis.verdict);
  if (verdict === "不建议") return false;
  const worth = Number(analysis.worth_score);
  if (!Number.isFinite(worth) || worth < minWorth) return false;
  if ((analysis.value_summary || "").trim().length < 16) return false;
  const mp = analysis.market_position;
  if (!monetizationHypothesisIsSubstantive(mp?.monetization_hypothesis)) return false;
  return true;
}

/** 阶段化工时拆解达标 */
export function hasEffortBreakdown(analysis: ReplicationAnalysis | null | undefined): boolean {
  const phases = analysis?.phases ?? [];
  if (phases.length < 3) return false;
  for (const p of phases) {
    if (!(p.name || "").trim()) return false;
    if (Number(p.hours_max) < 1) return false;
    if ((p.deliverable || "").trim().length < 8) return false;
  }
  const mvpMax = Number(analysis?.estimated_hours?.mvp_max ?? 0);
  return Number.isFinite(mvpMax) && mvpMax >= 8;
}

/** 完整「选项目」评估：变现 + 工时 */
export function hasCompleteReplicationAnalysis(
  analysis: ReplicationAnalysis | null | undefined,
  minWorth = 7,
): boolean {
  if (!hasValueAssessment(analysis, minWorth)) return false;
  if (!hasEffortBreakdown(analysis)) return false;
  const verdict = normalizeVerdict(analysis?.verdict);
  return POSITIVE_VERDICTS.has(verdict) || verdict === "观望";
}

/** 高价值精选：价值分≥8 且结论为高价值 */
export function isHighValuePick(analysis: ReplicationAnalysis | null | undefined): boolean {
  return hasValueAssessment(analysis, 8) && normalizeVerdict(analysis?.verdict) === "高价值";
}

export function showReplicationTierOnCard(
  feedKind: string | null | undefined,
  analysis: ReplicationAnalysis | null | undefined,
  tier: string | null | undefined,
): boolean {
  if ((feedKind || "").trim().toLowerCase() !== "apps") return false;
  if (!hasValueAssessment(analysis, 7)) return false;
  return Boolean((tier || "").trim());
}

export function formatPhaseHours(p: ReplicationPhase): string {
  const lo = Number(p.hours_min);
  const hi = Number(p.hours_max);
  if (lo > 0 && hi > 0 && hi !== lo) return `${lo}–${hi}h`;
  if (hi > 0) return `${hi}h`;
  if (lo > 0) return `${lo}h`;
  return "—";
}
