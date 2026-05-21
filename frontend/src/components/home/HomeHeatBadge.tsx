import { useI18n } from "@/i18n";
import { heatTier, type HeatTier } from "./homeUtils";

const STYLES: Record<HeatTier, string> = {
  blazing: "bg-gradient-to-r from-rose-500 to-orange-500 text-white shadow-sm",
  hot: "bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-sm",
  fresh: "bg-emerald-500/90 text-white shadow-sm",
};

export function HomeHeatBadge({ heat }: { heat?: number }) {
  const { t } = useI18n();
  const tier = heatTier(heat);
  if (!tier) return null;
  const label =
    tier === "blazing" ? t("homeHeatBlazing") : tier === "hot" ? t("homeHeatHot") : t("homeHeatFresh");
  return (
    <span className={`inline-flex rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${STYLES[tier]}`}>
      {label}
    </span>
  );
}
