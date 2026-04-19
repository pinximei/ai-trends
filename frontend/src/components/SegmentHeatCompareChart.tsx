import { useEffect, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useI18n } from "@/i18n";
import { lineKey, type CompareRow } from "@/lib/trendCompare";

const PALETTE = ["#60a5fa", "#34d399", "#fbbf24", "#a78bfa", "#f472b6"];

type Props = {
  rows: CompareRow[];
  segmentNames: Record<number, string>;
  segmentIds: number[];
};

export function SegmentHeatCompareChart({ rows, segmentNames, segmentIds }: Props) {
  const { t } = useI18n();
  const [hiddenSeg, setHiddenSeg] = useState<Set<number>>(() => new Set());

  useEffect(() => {
    setHiddenSeg(new Set());
  }, [segmentIds.join(",")]);

  const chartData = rows.map((r) => {
    const o: Record<string, string | number> = { x: r.x };
    for (const id of segmentIds) {
      const k = lineKey(id);
      const v = r.values[k];
      if (v !== undefined) o[k] = Math.round(v * 100) / 100;
    }
    return o;
  });

  function toggleSeg(id: number) {
    setHiddenSeg((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="flex h-full min-h-[200px] flex-col gap-2">
      <div className="min-h-0 flex-1 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="x" stroke="#64748b" fontSize={11} tickLine={false} />
            <YAxis
              stroke="#64748b"
              fontSize={11}
              width={36}
              domain={[0, 100]}
              tickLine={false}
              label={{ value: "0–100", angle: -90, position: "insideLeft", fill: "#64748b", fontSize: 10 }}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(15,23,42,0.95)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: "12px",
              }}
              formatter={(value: number, name: string) => {
                const id = Number(name.replace("seg_", ""));
                const label = segmentNames[id] ?? name;
                return [`${value}`, label];
              }}
            />
            {segmentIds.map((id, i) => (
              <Line
                key={id}
                type="monotone"
                dataKey={lineKey(id)}
                name={lineKey(id)}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={2}
                dot={false}
                connectNulls
                hide={hiddenSeg.has(id)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="flex shrink-0 flex-wrap items-center justify-center gap-2 px-1">
        {segmentIds.map((id, i) => {
          const color = PALETTE[i % PALETTE.length];
          const hidden = hiddenSeg.has(id);
          const label = segmentNames[id] ?? `seg_${id}`;
          return (
            <button
              key={id}
              type="button"
              onClick={() => toggleSeg(id)}
              title={hidden ? t("trendLegendToggleShow") : t("trendLegendToggleHide")}
              aria-pressed={!hidden}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                hidden
                  ? "border-white/10 bg-slate-950/60 text-slate-500 line-through decoration-slate-500"
                  : "border-white/15 bg-white/[0.06] text-slate-100 hover:bg-white/[0.1]"
              }`}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full ring-1 ring-white/20"
                style={{ backgroundColor: hidden ? "transparent" : color, boxShadow: hidden ? undefined : `0 0 8px ${color}66` }}
              />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
