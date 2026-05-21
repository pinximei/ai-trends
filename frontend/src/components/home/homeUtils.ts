import type { ArticleFeedCard } from "@/api/public";
import { formatStarCount } from "@/articleCardVisual";

export const HOME_SOURCE_ORDER = [
  "github",
  "product_hunt",
  "huggingface_spaces",
  "hacker_news",
  "arxiv",
] as const;

export type HeatTier = "blazing" | "hot" | "fresh";

export function heatTier(heat: number | undefined): HeatTier | null {
  const h = heat ?? 0;
  if (h >= 420) return "blazing";
  if (h >= 220) return "hot";
  if (h >= 72) return "fresh";
  return null;
}

export function platformAccent(key: string): { ring: string; badge: string; dot: string } {
  const k = (key || "").toLowerCase();
  if (k === "github") return { ring: "ring-slate-700/20", badge: "bg-slate-800 text-white", dot: "bg-slate-700" };
  if (k === "product_hunt") return { ring: "ring-orange-300/50", badge: "bg-orange-500 text-white", dot: "bg-orange-500" };
  if (k === "huggingface_spaces")
    return { ring: "ring-amber-300/50", badge: "bg-amber-500 text-white", dot: "bg-amber-500" };
  if (k === "hacker_news") return { ring: "ring-orange-400/40", badge: "bg-orange-600 text-white", dot: "bg-orange-600" };
  if (k === "arxiv") return { ring: "ring-red-300/40", badge: "bg-red-600 text-white", dot: "bg-red-600" };
  return { ring: "ring-violet-300/40", badge: "bg-violet-600 text-white", dot: "bg-violet-500" };
}

export function itemBlurb(item: ArticleFeedCard, max = 140): string {
  const s = (item.card_description || item.summary || "").trim();
  if (!s) return "—";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

export function itemEngagementLine(item: ArticleFeedCard): string | null {
  const stars = item.engagement_stars_total;
  if (stars != null && stars > 0) {
    const today =
      item.engagement_stars_today != null && item.engagement_stars_today > 0
        ? ` · +${formatStarCount(item.engagement_stars_today)} 今日`
        : "";
    return `★ ${formatStarCount(stars)}${today}`;
  }
  const heat = item.heat_score;
  if (heat != null && heat > 0) return `热度 ${Math.round(heat)}`;
  return null;
}

export type SourceLane = {
  source_key: string;
  source_label: string;
  items: ArticleFeedCard[];
};

export function mergeSourceLanes(newsLanes: SourceLane[], appsLanes: SourceLane[]): SourceLane[] {
  const byKey = new Map<string, SourceLane>();
  for (const lane of newsLanes) byKey.set(lane.source_key, lane);
  for (const lane of appsLanes) {
    if (!byKey.has(lane.source_key)) byKey.set(lane.source_key, lane);
  }
  return HOME_SOURCE_ORDER.map((k) => byKey.get(k)).filter((x): x is SourceLane => Boolean(x));
}
