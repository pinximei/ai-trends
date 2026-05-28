import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/i18n";
import { formatWindGrowth, type IndustryWindRow } from "@/components/home/IndustryWindPanel";

/** 宽 viewBox，配合 w-full 横向铺满 */
const CHART_W = 1000;
const CHART_H = 280;
const ML = 48;
const MR = 20;
const MT = 20;
const MB = 52;

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

function seriesKey(row: IndustryWindRow): string {
  return `${row.rank}-${rowHeadline(row)}`;
}

function mergeDayAxis(rows: IndustryWindRow[]): string[] {
  const keys = new Set<string>();
  for (const row of rows) {
    for (const p of row.series_this_week ?? []) keys.add(p.day);
    for (const p of row.series_last_week ?? []) keys.add(p.day);
  }
  return Array.from(keys).sort();
}

type Props = {
  rows: IndustryWindRow[];
};

export function IndustryWindLineChart({ rows }: Props) {
  const { t } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(() => new Set());

  const rowSignature = rows.map((r) => seriesKey(r)).join("|");
  useEffect(() => {
    setHiddenKeys(new Set());
    setHover(null);
  }, [rowSignature]);

  const allSeries = useMemo(() => {
    const days = mergeDayAxis(rows);
    return rows.map((row, i) => {
      const thisWeek = row.series_this_week ?? [];
      const lastWeek = row.series_last_week ?? [];
      const countFor = (list: typeof thisWeek, d: string) => list.find((p) => p.day === d)?.count ?? 0;
      return {
        key: seriesKey(row),
        row,
        color: LINE_COLORS[i % LINE_COLORS.length],
        days,
        thisCounts: days.map((d) => countFor(thisWeek, d)),
        lastCounts: days.map((d) => countFor(lastWeek, d)),
      };
    });
  }, [rows]);

  const visibleSeries = useMemo(
    () => allSeries.filter((s) => !hiddenKeys.has(s.key)),
    [allSeries, hiddenKeys],
  );

  const maxY = useMemo(() => {
    let m = 1;
    for (const s of visibleSeries) {
      for (const c of [...s.thisCounts, ...s.lastCounts]) {
        m = Math.max(m, c);
      }
    }
    return m;
  }, [visibleSeries]);

  const toggleSeries = (key: string) => {
    setHiddenKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
        return next;
      }
      next.add(key);
      return next;
    });
  };

  if (!allSeries.length || !allSeries[0]?.days.length) {
    return <p className="text-sm text-slate-500">{t("homeIndustryWindChartEmpty")}</p>;
  }

  const innerW = CHART_W - ML - MR;
  const innerH = CHART_H - MT - MB;
  const dayCount = allSeries[0].days.length;
  const xAt = (i: number) =>
    dayCount === 1 ? ML + innerW / 2 : ML + (i / (dayCount - 1)) * innerW;
  const yAt = (v: number) => MT + innerH - (v / maxY) * innerH;

  const yTicks = maxY <= 4 ? Array.from({ length: maxY + 1 }, (_, i) => i) : [0, Math.round(maxY / 2), maxY];

  const paths = visibleSeries.map((s) => {
    const thisPts = s.thisCounts.map((c, i) => ({ x: xAt(i), y: yAt(c), c }));
    const lastPts = s.lastCounts.map((c, i) => ({ x: xAt(i), y: yAt(c), c }));
    const toLine = (pts: typeof thisPts) =>
      pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
    return { ...s, thisLine: toLine(thisPts), lastLine: toLine(lastPts), thisPts, lastPts };
  });

  const hoverIdx = hover;
  const plotPct = (x: number) => `${((x - ML) / innerW) * 100}%`;

  return (
    <div className="w-full min-w-0">
      <p className="text-center text-xs text-slate-500">{t("homeIndustryWindChartHint")}</p>
      <div className="relative mt-3 w-full min-w-0">
        <svg
          viewBox={`0 0 ${CHART_W} ${CHART_H}`}
          className="block h-auto w-full min-w-0"
          style={{ minHeight: "13rem", maxHeight: "18rem" }}
          role="img"
          aria-label={t("homeIndustryWindChartAria")}
        >
          <line x1={ML} y1={MT} x2={ML} y2={MT + innerH} stroke="rgb(148 163 184)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          <line
            x1={ML}
            y1={MT + innerH}
            x2={CHART_W - MR}
            y2={MT + innerH}
            stroke="rgb(148 163 184)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />

          {yTicks.map((tick) => {
            const y = yAt(tick);
            return (
              <g key={tick}>
                <line
                  x1={ML}
                  y1={y}
                  x2={CHART_W - MR}
                  y2={y}
                  stroke="rgb(241 245 249)"
                  strokeWidth="1"
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  x={ML - 10}
                  y={y + 4}
                  textAnchor="end"
                  className="fill-slate-500 text-[11px] tabular-nums"
                  style={{ fontSize: 11 }}
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {paths.map((p) => (
            <g key={p.key}>
              <path
                d={p.lastLine}
                fill="none"
                stroke={p.color.stroke}
                strokeWidth="1.5"
                strokeDasharray="5 4"
                opacity="0.5"
                vectorEffect="non-scaling-stroke"
              />
              <path
                d={p.thisLine}
                fill="none"
                stroke={p.color.stroke}
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
              {hoverIdx != null
                ? p.thisPts.map((pt, i) => (
                    <circle
                      key={i}
                      cx={pt.x}
                      cy={pt.y}
                      r={hoverIdx === i ? 5 : 3.5}
                      fill={p.color.fill}
                      stroke="white"
                      strokeWidth="1.5"
                      opacity={hoverIdx === i ? 1 : 0}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))
                : null}
            </g>
          ))}

          {allSeries[0].days.map((d, i) => (
            <text
              key={d}
              x={xAt(i)}
              y={CHART_H - 14}
              textAnchor="middle"
              className="fill-slate-500 tabular-nums"
              style={{ fontSize: dayCount > 10 ? 9 : 10 }}
            >
              {formatDayShort(d)}
            </text>
          ))}

          {allSeries[0].days.map((_, i) => (
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

        {hoverIdx != null && visibleSeries.length > 0 ? (
          <div
            className="pointer-events-none absolute z-10 max-w-[min(100%,18rem)] rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px] shadow-lg"
            style={{
              left: plotPct(xAt(hoverIdx)),
              top: "6%",
              transform: "translateX(-50%)",
            }}
          >
            <p className="font-semibold text-slate-700">{formatDayShort(allSeries[0].days[hoverIdx] ?? "")}</p>
            <ul className="mt-1 max-h-40 space-y-0.5 overflow-y-auto">
              {paths.map((p) => (
                <li key={p.key} className="flex items-center gap-1.5 text-slate-600">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: p.color.stroke }} />
                  <span className="line-clamp-1 font-medium">{rowHeadline(p.row)}</span>
                  <span className="ml-auto tabular-nums text-slate-800">{p.thisPts[hoverIdx]?.c ?? 0}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[10px] text-slate-400 sm:text-[11px]">
        <span className="flex items-center gap-1.5">
          <span className="h-0 w-5 border-t-2 border-dashed border-slate-400" />
          {t("homeIndustryWindLastWeek")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-5 bg-slate-600" />
          {t("homeIndustryWindThisWeek")}
        </span>
      </div>

      <p className="mt-3 text-center text-[11px] text-slate-500">{t("homeIndustryWindChartToggleHint")}</p>
      <ul className="mt-2 flex flex-wrap justify-center gap-2">
        {allSeries.map((p) => {
          const on = !hiddenKeys.has(p.key);
          return (
            <li key={p.key}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => toggleSeries(p.key)}
                className={`flex max-w-[min(100%,14rem)] items-center gap-2 rounded-full border px-3 py-1.5 text-left text-[11px] transition sm:text-xs ${
                  on
                    ? "border-slate-300 bg-white text-slate-800 shadow-sm ring-1 ring-slate-200/80"
                    : "border-slate-200 bg-slate-100/80 text-slate-400 line-through"
                }`}
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-white"
                  style={{ background: on ? p.color.stroke : "rgb(203 213 225)" }}
                />
                <span className="line-clamp-1 font-medium">{rowHeadline(p.row)}</span>
                <span className="shrink-0 tabular-nums text-slate-500">{formatWindGrowth(p.row, t)}</span>
              </button>
            </li>
          );
        })}
      </ul>
      {visibleSeries.length === 0 ? (
        <p className="mt-3 text-center text-sm text-slate-500">{t("homeIndustryWindChartAllHidden")}</p>
      ) : null}
    </div>
  );
}
