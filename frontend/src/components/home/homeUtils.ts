import type { ArticleFeedCard } from "@/api/public";
import { formatStarCount } from "@/articleCardVisual";

/** 与后端 ACTIVE_ADMIN_SOURCE_KEYS 默认顺序一致；无 API 列表时的兜底 */
export const HOME_SOURCE_ORDER_DEFAULT = [
  "github",
  "product_hunt",
  "hacker_news",
  "newsapi",
  "thenewsapi",
  "acquire",
] as const;

const HOME_SOURCE_LABELS: Record<string, string> = {
  github: "GitHub（客户端）",
  product_hunt: "Product Hunt",
  hacker_news: "Hacker News",
  newsapi: "NewsAPI",
  thenewsapi: "TheNewsAPI",
  acquire: "Acquire（AI 资产）",
};

/** 首页雷达网格：列数随已配置源数量自适应（避免写死 7 列留白） */
export function radarGridClass(sourceCount: number): string {
  const n = Math.max(1, Math.min(sourceCount, 8));
  const map: Record<number, string> = {
    1: "grid gap-3 grid-cols-1",
    2: "grid gap-3 grid-cols-1 sm:grid-cols-2",
    3: "grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3",
    4: "grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
    5: "grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5",
    6: "grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6",
    7: "grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7",
    8: "grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-4 xl:grid-cols-8",
  };
  return map[n] ?? map[6];
}

export type HeatTier = "blazing" | "hot" | "fresh";

const REPLICATION_TIER_LABEL: Record<string, string> = {
  S: "高变现价值",
  A: "较高变现价值",
  B: "变现价值中",
  C: "低变现价值",
};

/** 列表卡片变现价值档位徽章；无档位时返回 null。 */
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
  if (k === "acquire")
    return { ring: "ring-emerald-300/50", badge: "bg-emerald-700 text-white", dot: "bg-emerald-700", border: "border-l-emerald-700" };
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

export function mergeSourceLanes(
  newsLanes: SourceLane[],
  appsLanes: SourceLane[],
  sourceOrder?: string[],
): SourceLane[] {
  const byKey = new Map<string, SourceLane>();
  for (const lane of newsLanes) {
    const prev = byKey.get(lane.source_key);
    if (!prev || (!prev.items.length && lane.items.length)) byKey.set(lane.source_key, lane);
  }
  for (const lane of appsLanes) {
    const prev = byKey.get(lane.source_key);
    if (!prev || (!prev.items.length && lane.items.length)) byKey.set(lane.source_key, lane);
  }
  const order =
    sourceOrder?.length ? sourceOrder : byKey.size ? [...byKey.keys()] : [...HOME_SOURCE_ORDER_DEFAULT];
  return order.map((k) => {
    const hit = byKey.get(k);
    if (hit) return hit;
    return {
      source_key: k,
      source_label: HOME_SOURCE_LABELS[k] ?? k.replace(/_/g, " "),
      items: [],
    };
  });
}
