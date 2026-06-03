import type { ArticleFeedCard } from "@/api/public";
import type { IndustryWindData } from "@/components/home/IndustryWindPanel";
import type { SourceLane } from "@/components/home/homeUtils";
import { readSsrHomeBootstrap } from "@/lib/ssrHomeBootstrap";

const CACHE_KEY = "aitrends_home_dashboard_v14";
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

/** 路由切走再回首页时仍保留（不随 HomePage 卸载清空） */
let memorySnapshot: Stored | null = null;

function isFresh(stored: Stored): boolean {
  return Date.now() - stored.fetchedAt <= CACHE_TTL_MS;
}

function pickNonEmpty<T>(next: T[] | undefined, prev: T[] | undefined): T[] {
  const n = next ?? [];
  if (n.length > 0) return n;
  return prev ?? [];
}

function pickTrend(
  next: HomeTrendOverview | null | undefined,
  prev: HomeTrendOverview | null | undefined,
): HomeTrendOverview | null {
  if (next?.sparkline?.length) return next;
  return prev ?? next ?? null;
}

function pickWind(
  next: IndustryWindData | null | undefined,
  prev: IndustryWindData | null | undefined,
): IndustryWindData | null {
  if ((next?.industries?.length ?? 0) > 0) return next ?? null;
  return prev ?? next ?? null;
}

/** 刷新时用新数据覆盖，但避免 API 某字段暂时为空时把已展示的卡片清空 */
export function mergeHomeDashboardPayload(
  prev: HomeDashboardCachePayload | null | undefined,
  incoming: Partial<HomeDashboardCachePayload>,
): HomeDashboardCachePayload {
  const p = prev;
  return {
    news: pickNonEmpty(incoming.news, p?.news),
    apps: pickNonEmpty(incoming.apps, p?.apps),
    editorialNews: pickNonEmpty(incoming.editorialNews, p?.editorialNews),
    editorialApps: pickNonEmpty(incoming.editorialApps, p?.editorialApps),
    highlightApps: pickNonEmpty(incoming.highlightApps, p?.highlightApps),
    highlightMonetization: pickNonEmpty(incoming.highlightMonetization, p?.highlightMonetization),
    newsLanes: pickNonEmpty(incoming.newsLanes, p?.newsLanes),
    appsLanes: pickNonEmpty(incoming.appsLanes, p?.appsLanes),
    sourceFacets: pickNonEmpty(incoming.sourceFacets, p?.sourceFacets),
    topCategories: pickNonEmpty(incoming.topCategories, p?.topCategories),
    industryWind: pickWind(incoming.industryWind, p?.industryWind),
    activeSourceCount: incoming.activeSourceCount ?? p?.activeSourceCount ?? 6,
    activeSourceKeys:
      (incoming.activeSourceKeys?.length ?? 0) > 0
        ? incoming.activeSourceKeys!
        : (p?.activeSourceKeys ?? []),
    trendOverview: pickTrend(incoming.trendOverview, p?.trendOverview),
  };
}

export function readHomeDashboardCacheAgeMs(): number | null {
  if (memorySnapshot && isFresh(memorySnapshot)) {
    return Date.now() - memorySnapshot.fetchedAt;
  }
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
  if (memorySnapshot && isFresh(memorySnapshot)) {
    const { fetchedAt: _at, ...payload } = memorySnapshot;
    return payload;
  }
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Stored;
    if (!parsed || typeof parsed.fetchedAt !== "number") return null;
    if (!isFresh(parsed)) {
      sessionStorage.removeItem(CACHE_KEY);
      memorySnapshot = null;
      return null;
    }
    memorySnapshot = parsed;
    const { fetchedAt: _at, ...payload } = parsed;
    return payload;
  } catch {
    return null;
  }
}

/** 每次进入首页时调用：优先内存快照，再 SSR / session。 */
export function readHomePageBoot(): HomeDashboardCachePayload | null {
  const mem = readHomeDashboardCache();
  if (mem) return mem;
  const ssr = readSsrHomeBootstrap();
  if (ssr) {
    writeHomeDashboardCache(ssr);
    return ssr;
  }
  return null;
}

export function homePayloadHasContent(p: HomeDashboardCachePayload | null | undefined): boolean {
  if (!p) return false;
  return (
    (p.editorialApps?.length ?? 0) > 0 ||
    (p.editorialNews?.length ?? 0) > 0 ||
    (p.news?.length ?? 0) > 0 ||
    (p.apps?.length ?? 0) > 0 ||
    (p.highlightApps?.length ?? 0) > 0 ||
    (p.highlightMonetization?.length ?? 0) > 0 ||
    (p.newsLanes?.length ?? 0) > 0 ||
    (p.appsLanes?.length ?? 0) > 0 ||
    (p.trendOverview?.sparkline?.length ?? 0) > 0 ||
    (p.industryWind?.industries?.length ?? 0) > 0
  );
}

export function writeHomeDashboardCache(payload: HomeDashboardCachePayload): void {
  const stored: Stored = { ...payload, fetchedAt: Date.now() };
  memorySnapshot = stored;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(stored));
  } catch {
    /* quota / private mode */
  }
}
