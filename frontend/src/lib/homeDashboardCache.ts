import type { ArticleFeedCard } from "@/api/public";
import type { IndustryWindData } from "@/components/home/IndustryWindPanel";
import type { SourceLane } from "@/components/home/homeUtils";
import { readSsrHomeBootstrap } from "@/lib/ssrHomeBootstrap";

const CACHE_KEY = "aitrends_home_dashboard_v12";
/** 同一会话内复用首页数据（含今日精选），减少切页回首页时的重复加载 */
const CACHE_TTL_MS = 30 * 60 * 1000;

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
  metric_basis?: string;
  metric_note?: string;
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

export function readHomeDashboardCacheAgeMs(): number | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored;
    if (!parsed || typeof parsed.fetchedAt !== "number") return null;
    return Date.now() - parsed.fetchedAt;
  } catch {
    return null;
  }
}

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

/** 每次进入首页时调用：勿在模块顶层缓存，否则 React 路由切回时读不到已写入的 session。 */
export function readHomePageBoot(): HomeDashboardCachePayload | null {
  return readSsrHomeBootstrap() ?? readHomeDashboardCache();
}

export function homePayloadHasContent(p: HomeDashboardCachePayload | null | undefined): boolean {
  if (!p) return false;
  return (
    (p.editorialApps?.length ?? 0) > 0 ||
    (p.editorialNews?.length ?? 0) > 0 ||
    (p.news?.length ?? 0) > 0 ||
    (p.apps?.length ?? 0) > 0
  );
}

export function writeHomeDashboardCache(payload: HomeDashboardCachePayload): void {
  try {
    const stored: Stored = { ...payload, fetchedAt: Date.now() };
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(stored));
  } catch {
    /* quota / private mode */
  }
}
