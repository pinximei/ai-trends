const KEY = "aitrends_recent_v1";

export type RecentArticle = { id: number; title: string; feed: string };

function readRecent(): RecentArticle[] {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw) as unknown;
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((x): x is RecentArticle => x && typeof x === "object" && typeof (x as RecentArticle).id === "number")
      .map((x) => ({
        id: Number((x as RecentArticle).id),
        title: String((x as RecentArticle).title || ""),
        feed: String((x as RecentArticle).feed || "news"),
      }));
  } catch {
    return [];
  }
}

/** 详情页写入，供后续若恢复「最近浏览」等功能使用 */
export function pushRecentArticle(item: RecentArticle): void {
  try {
    const prev = readRecent();
    const next = [item, ...prev.filter((x) => x.id !== item.id)].slice(0, 14);
    sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}
