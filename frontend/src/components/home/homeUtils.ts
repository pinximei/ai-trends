import type { ArticleFeedCard } from "@/api/public";
import { formatStarCount } from "@/articleCardVisual";

export const HOME_SOURCE_ORDER = [
  "github",
  "product_hunt",
  "hacker_news",
  "newsapi",
  "thenewsapi",
] as const;

export const HOME_SOURCE_LABELS: Record<(typeof HOME_SOURCE_ORDER)[number], string> = {
  github: "GitHub（客户端）",
  product_hunt: "Product Hunt",
  hacker_news: "Hacker News",
  newsapi: "NewsAPI",
  thenewsapi: "TheNewsAPI",
};

export type HeatTier = "blazing" | "hot" | "fresh";

const REPLICATION_TIER_LABEL: Record<string, string> = {
  S: "高可复刻",
  A: "较高可复刻",
  B: "可复刻性中",
  C: "低可复刻",
};

/** 列表卡片可复刻性档位徽章；无档位时返回 null。 */
export function replicationTierLabel(tier: string | null | undefined): string | null {
  const k = (tier || "").trim().toUpperCase();
  return REPLICATION_TIER_LABEL[k] ?? null;
}

export function heatTier(heat: number | undefined): HeatTier | null {
  const h = heat ?? 0;
  if (h >= 420) return "blazing";
  if (h >= 220) return "hot";
  if (h >= 72) return "fresh";
  return null;
}

export function platformAccent(key: string): { ring: string; badge: string; dot: string; border: string } {
  const k = (key || "").toLowerCase();
  if (k === "github")
    return { ring: "ring-slate-700/20", badge: "bg-slate-800 text-white", dot: "bg-slate-700", border: "border-l-slate-700" };
  if (k === "product_hunt")
    return { ring: "ring-orange-300/50", badge: "bg-orange-500 text-white", dot: "bg-orange-500", border: "border-l-orange-500" };
  if (k === "hacker_news")
    return { ring: "ring-orange-400/40", badge: "bg-orange-600 text-white", dot: "bg-orange-600", border: "border-l-orange-600" };
  if (k === "newsapi")
    return { ring: "ring-sky-300/50", badge: "bg-sky-600 text-white", dot: "bg-sky-600", border: "border-l-sky-600" };
  if (k === "thenewsapi")
    return { ring: "ring-blue-300/50", badge: "bg-blue-700 text-white", dot: "bg-blue-700", border: "border-l-blue-700" };
  if (k === "arxiv" || k === "huggingface_spaces")
    return { ring: "ring-red-300/40", badge: "bg-red-600 text-white", dot: "bg-red-600", border: "border-l-red-600" };
  return { ring: "ring-violet-300/40", badge: "bg-violet-600 text-white", dot: "bg-violet-500", border: "border-l-violet-500" };
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
  return HOME_SOURCE_ORDER.map((k) => {
    const hit = byKey.get(k);
    if (hit) return hit;
    return {
      source_key: k,
      source_label: HOME_SOURCE_LABELS[k],
      items: [],
    };
  });
}
