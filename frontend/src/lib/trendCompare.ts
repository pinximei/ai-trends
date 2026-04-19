/** 将各板块序列按区间内极值归一化到 0–100，便于横向对比「相对热度」走势（原始单位可能不同）。 */

export function normalizeMinMax(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (Math.abs(max - min) < 1e-9) return values.map(() => 50);
  return values.map((v) => ((v - min) / (max - min)) * 100);
}

export function dateKey(iso: string): string {
  return iso.slice(0, 10);
}

export type SegmentSeries = {
  segmentId: number;
  segmentName: string;
  metricKey: string;
  metricName: string;
  points: { t: string; value: number }[];
};

export type CompareRow = { x: string; values: Record<string, number> };

/** 按日期对齐各板块归一化后的值，用于多折线图。lineKey 形如 seg_12 */
export function buildNormalizedCompareRows(series: SegmentSeries[]): CompareRow[] {
  const lineKeys = series.map((s) => lineKey(s.segmentId));
  const byDate = new Map<string, Record<string, number>>();

  series.forEach((s, idx) => {
    const key = lineKeys[idx];
    const vals = s.points.map((p) => p.value);
    const norm = normalizeMinMax(vals);
    s.points.forEach((p, i) => {
      const dk = dateKey(p.t);
      let row = byDate.get(dk);
      if (!row) {
        row = {};
        byDate.set(dk, row);
      }
      row[key] = norm[i]!;
    });
  });

  const dates = [...byDate.keys()].sort();
  return dates.map((x) => ({
    x,
    values: byDate.get(x) ?? {},
  }));
}

export function lineKey(segmentId: number): string {
  return `seg_${segmentId}`;
}

/** 各板块归一化序列的区间均值，用于排序「谁相对更热」 */
export function rankByMeanNormalized(series: SegmentSeries[]): { segmentId: number; segmentName: string; meanNorm: number }[] {
  return series
    .map((s) => {
      const vals = s.points.map((p) => p.value);
      const norm = normalizeMinMax(vals);
      const meanNorm = norm.length ? norm.reduce((a, b) => a + b, 0) / norm.length : 0;
      return { segmentId: s.segmentId, segmentName: s.segmentName, meanNorm };
    })
    .sort((a, b) => b.meanNorm - a.meanNorm);
}
