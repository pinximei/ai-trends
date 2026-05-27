import { useMemo, useState } from "react";
import { useI18n } from "@/i18n";
import type { IndustryWindRow } from "@/components/home/IndustryWindPanel";

const CHART_W = 520;
const CHART_H = 240;
const ML = 44;
const MR = 16;
const MT = 18;
const MB = 36;

const LINE_COLORS = [
  { stroke: "rgb(234 88 12)", fill: "rgb(234 88 12)" },
  { stroke: "rgb(124 58 237)", fill: "rgb(124 58 237)" },
  { stroke: "rgb(14 165 233)", fill: "rgb(14 165 233)" },
  { stroke: "rgb(16 185 129)", fill: "rgb(16 185 129)" },
  { stroke: "rgb(244 63 94)", fill: "rgb(244 63 94)" },
  { stroke: "rgb(99 102 241)", fill: "rgb(99 102 241)" },
] as const;

function formatDayShort(day: string): string {
  const parts = day.split("-");
  if (parts.length >= 3) return `${parts[1]}/${parts[2]}`;
  return day;
}

function rowHeadline(row: IndustryWindRow): string {
  return (row.headline || row.label || "").trim();
}

function formatGrowth(pct: number | null): string {
  if (pct == null) return "—";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct}%`;
}

type Props = {
  rows: IndustryWindRow[];
};

export function IndustryWindLineChart({ rows }: Props) {
  const { t } = useI18n();
  const [hover, setHover] = useState<number | null>(null);

  const series = useMemo(() => {
    return rows.slice(0, 6).map((row, i) => {
      const thisWeek = row.series_this_week ?? [];
      const lastWeek = row.series_last_week ?? [];
      const days =
        thisWeek.length >= lastWeek.length
          ? thisWeek.map((p) => p.day)
          : lastWeek.map((p) => p.day);
      return {
        row,
        color: LINE_COLORS[i % LINE_COLORS.length],
        days,
        thisCounts: days.map((d) => thisWeek.find((p) => p.day === d)?.count ?? 0),
        lastCounts: days.map((d) => lastWeek.find((p) => p.day === d)?.count ?? 0),
      };
    });
  }, [rows]);

  const maxY = useMemo(() => {
    let m = 1;
    for (const s of series) {
      for (const c of [...s.thisCounts, ...s.lastCounts]) {
        m = Math.max(m, c);
      }
    }
    return m;
  }, [series]);

  if (!series.length || !series[0]?.days.length) {
    return <p className="text-sm text-slate-500">{t("homeIndustryWindChartEmpty")}</p>;
  }

  const innerW = CHART_W - ML - MR;
  const innerH = CHART_H - MT - MB;
  const dayCount = series[0].days.length;
  const xAt = (i: number) =>
    dayCount === 1 ? ML + innerW / 2 : ML + (i / (dayCount - 1)) * innerW;
  const yAt = (v: number) => MT + innerH - (v / maxY) * innerH;

  const yTicks = maxY <= 4 ? Array.from({ length: maxY + 1 }, (_, i) => i) : [0, Math.round(maxY / 2), maxY];

  const paths = series.map((s) => {
    const thisPts = s.thisCounts.map((c, i) => ({ x: xAt(i), y: yAt(c), c }));
    const lastPts = s.lastCounts.map((c, i) => ({ x: xAt(i), y: yAt(c), c }));
    const toLine = (pts: typeof thisPts) =>
      pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
    return { ...s, thisLine: toLine(thisPts), lastLine: toLine(lastPts), thisPts, lastPts };
  });

  const hoverIdx = hover;
  const plotPct = (x: number) => `${((x - ML) / innerW) * 100}%`;

  return (
    <div className="w-full">
      <p className="text-center text-xs text-slate-500">{t("homeIndustryWindChartHint")}</p>
      <div className="relative mt-3 w-full">
        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          className="block h-[14rem] w-full sm:h-[16rem]"
          role="img"
          aria-label={t("homeIndustryWindChartAria")}
        >
          <line x1={ML} y1={MT} x2={ML} y2={MT + innerH} stroke="rgb(148 163 184)" strokeWidth="1.5" />
          <line x1={ML} y1={MT + innerH} x2={CHART_W - MR} y2={MT + innerH} stroke="rgb(148 163 184)" strokeWidth="1.5" />

          {yTicks.map((tick) => {
            const y = yAt(tick);
            return (
              <g key={tick}>
                <line x1={ML} y1={y} x2={CHART_W - MR} y2={y} stroke="rgb(241 245 249)" strokeWidth="1" />
                <text x={ML - 8} y={y + 4} textAnchor="end" className="fill-slate-500 text-[10px] tabular-nums">
                  {tick}
                </text>
              </g>
            );
          })}

          {paths.map((p) => (
            <g key={rowHeadline(p.row)}>
              <path d={p.lastLine} fill="none" stroke={p.color.stroke} strokeWidth="1.5" strokeDasharray="4 3" opacity="0.45" />
              <path d={p.thisLine} fill="none" stroke={p.color.stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              {hoverIdx != null
                ? p.thisPts.map((pt, i) => (
                    <circle
                      key={i}
                      cx={pt.x}
                      cy={pt.y}
                      r={hoverIdx === i ? 4.5 : 3}
                      fill={p.color.fill}
                      stroke="white"
                      strokeWidth="1.5"
                      opacity={hoverIdx === i ? 1 : 0}
                    />
                  ))
                : null}
            </g>
          ))}

          {series[0].days.map((_, i) => (
            <rect
              key={i}
              x={i === 0 ? ML : (xAt(i - 1) + xAt(i)) / 2}
              y={MT}
              width={
                i === 0
                  ? (xAt(1) - ML) / 2
                  : i === dayCount - 1
                    ? CHART_W - MR - (xAt(i - 1) + xAt(i)) / 2
                    : (xAt(i + 1) - xAt(i - 1)) / 2
              }
              height={innerH}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>

        {hoverIdx != null ? (
          <div
            className="pointer-events-none absolute z-10 max-w-[min(100%,16rem)] rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px] shadow-lg"
            style={{
              left: plotPct(xAt(hoverIdx)),
              top: "8%",
              transform: "translateX(-50%)",
            }}
          >
            <p className="font-semibold text-slate-700">{formatDayShort(series[0].days[hoverIdx] ?? "")}</p>
            <ul className="mt-1 space-y-0.5">
              {paths.map((p) => (
                <li key={rowHeadline(p.row)} className="flex items-center gap-1.5 text-slate-600">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: p.color.stroke }} />
                  <span className="line-clamp-1 font-medium">{rowHeadline(p.row)}</span>
                  <span className="ml-auto tabular-nums text-slate-800">{p.thisPts[hoverIdx]?.c ?? 0}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="relative mt-1 h-6 text-[11px] text-slate-500" style={{ marginLeft: `${(ML / CHART_W) * 100}%`, width: `${(innerW / CHART_W) * 100}%` }}>
          {series[0].days.map((d, i) => {
            const edge = i === 0 ? "" : i === dayCount - 1 ? "-translate-x-full" : "-translate-x-1/2";
            return (
              <span key={d} className={`absolute top-0 ${edge}`} style={{ left: plotPct(xAt(i)) }}>
                {formatDayShort(d)}
              </span>
            );
          })}
        </div>
      </div>

      <ul className="mt-4 flex flex-wrap justify-center gap-x-4 gap-y-2 text-[11px] text-slate-600">
        {paths.map((p) => (
          <li key={rowHeadline(p.row)} className="flex max-w-full items-center gap-1.5">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: p.color.stroke }} />
            <span className="line-clamp-1 font-medium text-slate-800">{rowHeadline(p.row)}</span>
            <span className="shrink-0 tabular-nums text-slate-500">
              {formatGrowth(p.row.growth_pct)}
            </span>
          </li>
        ))}
        <li className="flex items-center gap-1.5 text-slate-400">
          <span className="h-0 w-4 border-t border-dashed border-slate-400" />
          {t("homeIndustryWindLastWeek")}
        </li>
        <li className="flex items-center gap-1.5 text-slate-400">
          <span className="h-0.5 w-4 bg-slate-500" />
          {t("homeIndustryWindThisWeek")}
        </li>
      </ul>
    </div>
  );
}
