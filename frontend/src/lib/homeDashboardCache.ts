import type { ArticleFeedCard } from "@/api/public";
import type { IndustryWindData } from "@/components/home/IndustryWindPanel";
import type { SourceLane } from "@/components/home/homeUtils";

const CACHE_KEY = "aitrends_home_dashboard_v4";
/** 同一会话内复用首页数据，减少往返与「加载中」闪烁 */
const CACHE_TTL_MS = 5 * 60 * 1000;

export type HomeTrendOverview = {
  sparkline: Array<{ day: string; count: number }>;
  apps_count: number;
  news_count: number;
  apps_growth_pct: number | null;
  news_growth_pct: number | null;
  this_week_total?: number;
  last_week_total?: number;
  week_total_growth_pct?: number | null;
  compare_mode?: string;
};

export type HomeDashboardCachePayload = {
  news: ArticleFeedCard[];
  apps: ArticleFeedCard[];
  editorialNews: ArticleFeedCard[];
  editorialApps: ArticleFeedCard[];
  highlightApps: ArticleFeedCard[];
  highlightMonetization: ArticleFeedCard[];
  newsLanes: SourceLane[];
  appsLanes: SourceLane[];
  sourceFacets: Array<{ key: string; label: string; news_count: number; apps_count: number }>;
  topCategories: Array<{ label: string; count: number }>;
  industryWind: IndustryWindData | null;
  activeSourceCount: number;
  activeSourceKeys: string[];
  trendOverview: HomeTrendOverview | null;
};

type Stored = HomeDashboardCachePayload & { fetchedAt: number };

export function readHomeDashboardCache(): HomeDashboardCachePayload | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored;
    if (!parsed || typeof parsed.fetchedAt !== "number") return null;
    if (Date.now() - parsed.fetchedAt > CACHE_TTL_MS) {
      sessionStorage.removeItem(CACHE_KEY);
      return null;
    }
    const { fetchedAt: _at, ...payload } = parsed;
    return payload;
  } catch {
    return null;
  }
}

export function writeHomeDashboardCache(payload: HomeDashboardCachePayload): void {
  try {
    const stored: Stored = { ...payload, fetchedAt: Date.now() };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(stored));
  } catch {
    /* quota / private mode */
  }
}
