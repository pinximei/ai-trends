import type { IndustryWindRow, WindDayPoint } from "@/components/home/IndustryWindPanel";

/** 与后端 ``_day_keys_utc`` 对齐：最近 N 个 UTC 自然日（不含 endOffset 当日），从旧到新。 */
export function lastUtcDayKeys(endOffsetDays: number, count: number): string[] {
  const out: string[] = [];
  const todayUtc = Date.UTC(
    new Date().getUTCFullYear(),
    new Date().getUTCMonth(),
    new Date().getUTCDate(),
  );
  const endMs = todayUtc - endOffsetDays * 86400000;
  for (let i = count; i >= 1; i--) {
    out.push(new Date(endMs - i * 86400000).toISOString().slice(0, 10));
  }
  return out;
}

function spreadCountAcrossDays(total: number, days: string[]): WindDayPoint[] {
  const n = days.length;
  if (n === 0) return [];
  const safe = Math.max(0, Math.floor(total));
  if (safe === 0) return days.map((day) => ({ day, count: 0 }));
  const base = Math.floor(safe / n);
  let rem = safe - base * n;
  return days.map((day) => {
    const extra = rem > 0 ? 1 : 0;
    if (rem > 0) rem -= 1;
    return { day, count: base + extra };
  });
}

/** API/缓存缺 series 时，用本周/上周篇数生成 7 日折线（便于切换视图，非精确按日统计）。 */
export function ensureWindChartSeries(row: IndustryWindRow): IndustryWindRow {
  if ((row.series_this_week?.length ?? 0) > 0) return row;
  const thisDays = lastUtcDayKeys(0, 7);
  const lastDays = lastUtcDayKeys(7, 7);
  return {
    ...row,
    series_this_week: spreadCountAcrossDays(row.article_count ?? 0, thisDays),
    series_last_week: spreadCountAcrossDays(row.prior_count ?? 0, lastDays),
  };
}

export function industriesWithChartSeries(rows: IndustryWindRow[]): IndustryWindRow[] {
  return rows.map(ensureWindChartSeries);
}
