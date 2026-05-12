import { useMemo } from "react";
import { BarChart3, Layers, Sparkles } from "lucide-react";
import { useI18n } from "@/i18n";

type Cat = { label: string; count: number };

type Props = {
  mode: "news" | "apps";
  listLen: number;
  categoryOptions: Cat[];
};

function ActivityStrip({ listLen, categoryOptions }: { listLen: number; categoryOptions: Cat[] }) {
  const points = useMemo(() => {
    const seed = listLen + categoryOptions.reduce((s, c) => s + c.count, 0);
    return Array.from({ length: 14 }, (_, i) =>
      Math.max(0.08, seed * 0.035 + Math.sin(i * 0.5) * (seed * 0.018) + i * 0.05),
    );
  }, [listLen, categoryOptions]);
  const max = Math.max(...points, 1);
  return (
    <div
      className="relative mt-3 overflow-hidden rounded-2xl bg-gradient-to-br from-slate-100/90 via-white to-violet-50/50 p-3 ring-1 ring-violet-100/70"
      aria-hidden
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_20%_-10%,rgba(124,58,237,0.14),transparent_55%)]" />
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-violet-200/80 to-transparent" />
      <div className="relative flex h-[4.25rem] items-end gap-px px-0.5">
        {points.map((v, i) => (
          <div
            key={i}
            className="min-w-0 flex-1 rounded-t-sm bg-gradient-to-t from-violet-600/50 via-violet-400/45 to-sky-300/35 shadow-sm shadow-violet-500/10"
            style={{ height: `${Math.max(12, (v / max) * 100)}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function FeedSidebar({ mode, listLen, categoryOptions }: Props) {
  const { t } = useI18n();

  const sorted = useMemo(
    () => [...categoryOptions].sort((a, b) => b.count - a.count).slice(0, 5),
    [categoryOptions],
  );
  const maxC = sorted[0]?.count || 1;
  const totalListed = categoryOptions.reduce((s, c) => s + c.count, 0);

  const railTitle = mode === "apps" ? t("sidebarChartApps") : t("sidebarChartNews");

  return (
    <div className="relative flex flex-col overflow-hidden rounded-3xl border border-slate-200/70 bg-gradient-to-b from-white via-white to-slate-50/40 shadow-card ring-1 ring-white/60 transition-shadow duration-300 hover:shadow-ui">
      <div className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-violet-400/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-24 -left-12 h-40 w-40 rounded-full bg-sky-400/12 blur-3xl" />

      <header className="relative border-b border-slate-100/90 px-5 pb-4 pt-5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-violet-600/90">{t("sidebarRailKicker")}</p>
        <h2 className="mt-2 text-[15px] font-bold leading-snug tracking-tight text-slate-900">{railTitle}</h2>
        <div className="mt-3 flex items-center gap-2">
          <span className="h-0.5 w-10 rounded-full bg-gradient-to-r from-violet-500 to-sky-400" />
          <span className="h-0.5 flex-1 rounded-full bg-slate-100" />
        </div>
      </header>

      <div className="relative space-y-0 px-5 pb-5 pt-4">
        <ActivityStrip listLen={listLen} categoryOptions={categoryOptions} />

        <section className="mt-5 overflow-hidden rounded-2xl border border-slate-100/90 bg-white/70 shadow-inner">
          <div className="grid grid-cols-3 divide-x divide-slate-100/90">
            <div className="flex flex-col items-center gap-1 px-2 py-3.5 text-center">
              <Sparkles className="h-4 w-4 text-emerald-600" strokeWidth={2} aria-hidden />
              <span className="text-lg font-bold tabular-nums leading-none text-slate-900">{listLen}</span>
              <span className="max-w-[5.5rem] text-[10px] font-medium uppercase leading-tight tracking-wide text-slate-500">
                {t("sidebarStatNew")}
              </span>
            </div>
            <div className="flex flex-col items-center gap-1 px-2 py-3.5 text-center">
              <Layers className="h-4 w-4 text-violet-600" strokeWidth={2} aria-hidden />
              <span className="text-lg font-bold tabular-nums leading-none text-slate-900">{categoryOptions.length}</span>
              <span className="max-w-[5.5rem] text-[10px] font-medium uppercase leading-tight tracking-wide text-slate-500">
                {t("sidebarStatCategories")}
              </span>
            </div>
            <div className="flex flex-col items-center gap-1 px-2 py-3.5 text-center">
              <BarChart3 className="h-4 w-4 text-sky-600" strokeWidth={2} aria-hidden />
              <span className="text-lg font-bold tabular-nums leading-none text-slate-900">{totalListed}</span>
              <span className="max-w-[5.5rem] text-[10px] font-medium uppercase leading-tight tracking-wide text-slate-500">
                {t("sidebarStatVolume")}
              </span>
            </div>
          </div>
        </section>

        <section className="mt-5">
          <h3 className="flex items-center gap-2.5 text-[11px] font-bold uppercase tracking-wider text-slate-600">
            <span className="h-2 w-2 shrink-0 rounded-full bg-gradient-to-br from-violet-500 to-sky-400 shadow-sm shadow-violet-400/35" aria-hidden />
            {t("sidebarTrendingTitle")}
          </h3>
          <ol className="mt-3 space-y-1.5">
            {sorted.length === 0 ? (
              <li className="rounded-xl border border-dashed border-slate-200/90 bg-slate-50/50 px-3 py-4 text-center text-xs text-slate-500">
                {t("sidebarTrendingEmpty")}
              </li>
            ) : (
              sorted.map((row, idx) => (
                <li key={row.label}>
                  <div className="group flex gap-3 rounded-xl border border-transparent px-2 py-2 transition hover:border-violet-100 hover:bg-violet-50/40">
                    <span className="mt-0.5 w-6 shrink-0 text-right font-mono text-[11px] font-semibold tabular-nums text-slate-400 group-hover:text-violet-600">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-[13px] font-semibold leading-snug text-slate-800">{row.label}</span>
                        <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] font-medium tabular-nums text-slate-600 ring-1 ring-slate-200/80">
                          {row.count}
                        </span>
                      </div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-violet-500 via-fuchsia-500 to-sky-400 transition-[width] duration-500"
                          style={{ width: `${Math.max(8, (row.count / maxC) * 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </li>
              ))
            )}
          </ol>
        </section>
      </div>
    </div>
  );
}
