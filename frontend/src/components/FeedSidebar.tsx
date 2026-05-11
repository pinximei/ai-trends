import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip } from "recharts";
import { BarChart3, Layers, Sparkles } from "lucide-react";
import { useI18n } from "@/i18n";

type Cat = { label: string; count: number };

type Props = {
  mode: "news" | "apps";
  listLen: number;
  categoryOptions: Cat[];
};

export function FeedSidebar({ mode, listLen, categoryOptions }: Props) {
  const { t } = useI18n();

  const chartData = useMemo(() => {
    const seed = listLen + categoryOptions.reduce((s, c) => s + c.count, 0);
    return Array.from({ length: 14 }, (_, i) => ({
      i: String(i),
      v: Math.max(1, seed * 0.06 + Math.sin(i * 0.5) * (seed * 0.03) + i * 1.1),
    }));
  }, [listLen, categoryOptions]);

  const sorted = useMemo(
    () => [...categoryOptions].sort((a, b) => b.count - a.count).slice(0, 5),
    [categoryOptions],
  );
  const maxC = sorted[0]?.count || 1;
  const totalListed = categoryOptions.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-5">
      <div className="glass-light glass-hover-light p-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {mode === "apps" ? t("sidebarChartApps") : t("sidebarChartNews")}
        </p>
        <div className="mt-2 h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 6, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="sidebarFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0.08} />
                </linearGradient>
              </defs>
              <Tooltip
                formatter={(v: number) => [Math.round(v), t("sidebarTooltip")]}
                labelFormatter={() => ""}
                contentStyle={{
                  borderRadius: 12,
                  border: "1px solid #e2e8f0",
                  fontSize: 12,
                  boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
                }}
              />
              <Area
                type="monotone"
                dataKey="v"
                stroke="#7c3aed"
                strokeWidth={2.5}
                fill="url(#sidebarFill)"
                dot={false}
                activeDot={{ r: 4, fill: "#0ea5e9", stroke: "#fff", strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="glass-light rounded-2xl p-3 text-center">
          <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-600">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="text-lg font-bold tabular-nums text-slate-900">{listLen}</div>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{t("sidebarStatNew")}</div>
        </div>
        <div className="glass-light rounded-2xl p-3 text-center">
          <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100 text-violet-600">
            <Layers className="h-4 w-4" />
          </div>
          <div className="text-lg font-bold tabular-nums text-slate-900">{categoryOptions.length}</div>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{t("sidebarStatCategories")}</div>
        </div>
        <div className="glass-light rounded-2xl p-3 text-center">
          <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-sky-100 text-sky-600">
            <BarChart3 className="h-4 w-4" />
          </div>
          <div className="text-lg font-bold tabular-nums text-slate-900">{totalListed}</div>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{t("sidebarStatVolume")}</div>
        </div>
      </div>

      <div className="glass-light p-5">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{t("sidebarTrendingTitle")}</p>
        <ul className="mt-3 space-y-3">
          {sorted.length === 0 ? (
            <li className="text-sm text-slate-500">{t("sidebarTrendingEmpty")}</li>
          ) : (
            sorted.map((row) => (
              <li key={row.label}>
                <div className="flex items-center justify-between gap-2 text-xs font-medium text-slate-700">
                  <span className="truncate">{row.label}</span>
                  <span className="shrink-0 tabular-nums text-slate-500">{row.count}</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-violet-500 to-sky-400"
                    style={{ width: `${Math.max(8, (row.count / maxC) * 100)}%` }}
                  />
                </div>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
