import { useMemo } from "react";
import { ScrollText, Sparkles } from "lucide-react";
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
      className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-100/90 via-white to-brand-50/50 p-3 ring-1 ring-brand-100/70"
      aria-hidden
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_20%_-10%,rgba(124,58,237,0.14),transparent_55%)]" />
      <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-brand-200/80 to-transparent" />
      <div className="relative flex h-[4.25rem] items-end gap-px px-0.5">
        {points.map((v, i) => (
          <div
            key={i}
            className="min-w-0 flex-1 rounded-t-sm bg-gradient-to-t from-brand-600/50 via-brand-400/45 to-sky-300/35 shadow-sm shadow-brand-500/10"
            style={{ height: `${Math.max(12, (v / max) * 100)}%` }}
          />
        ))}
      </div>
    </div>
  );
}

/** 左栏底部：本页速览条形示意（随本页条数与类别统计变化） */
export function FeedPageGlance({ mode, listLen, categoryOptions }: Props) {
  const { t } = useI18n();
  const ModeGlyph = mode === "apps" ? Sparkles : ScrollText;

  return (
    <section className="ui-card p-4 sm:p-5" aria-label={t("sidebarRailKicker")}>
      <div className="mb-3 flex items-center gap-2 border-b border-slate-100/90 pb-3">
        <ModeGlyph className="h-4 w-4 shrink-0 text-brand-600" strokeWidth={2} aria-hidden />
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-slate-600">{t("sidebarRailKicker")}</h2>
      </div>
      <ActivityStrip listLen={listLen} categoryOptions={categoryOptions} />
    </section>
  );
}
