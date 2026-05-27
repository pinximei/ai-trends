import type { ReplicationAnalysis } from "@/api/public/types";

/** 与后端 validate_replication_analysis_for_publish + 首页高可复刻规则对齐 */
export function hasCompleteReplicationAnalysis(
  analysis: ReplicationAnalysis | null | undefined,
  minWorth = 7,
): boolean {
  if (!analysis?.verdict?.trim()) return false;
  const worth = Number(analysis.worth_score);
  if (!Number.isFinite(worth) || worth < minWorth) return false;
  if ((analysis.value_summary || "").trim().length < 16) return false;
  if (!Array.isArray(analysis.tech_stack) || analysis.tech_stack.length === 0) return false;
  const hours = analysis.estimated_hours;
  const mvpMax = Number(hours?.mvp_max ?? 0);
  const prodMax = Number(hours?.prod_max ?? 0);
  if (mvpMax < 8 && prodMax < 40) return false;
  const plan = analysis.implementation_plan ?? [];
  const details = analysis.implementation_details ?? [];
  if (plan.length === 0 && details.length === 0) return false;
  if ((analysis.tier_rationale || "").trim().length < 20) return false;
  return true;
}

export function showReplicationTierOnCard(
  feedKind: string | null | undefined,
  analysis: ReplicationAnalysis | null | undefined,
  tier: string | null | undefined,
): boolean {
  if ((feedKind || "").trim().toLowerCase() !== "apps") return false;
  if (!hasCompleteReplicationAnalysis(analysis)) return false;
  return Boolean((tier || "").trim());
}
