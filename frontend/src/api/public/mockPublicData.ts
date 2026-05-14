import type { ArticleDetail, ArticleFeedCard, ArticlesFeedCursorResponse } from "./types";

const LONG_MD = (chunks: number) =>
  ["## 模拟长文（用于滚动）", ""]
    .concat(
      Array.from({ length: chunks }, (_, i) => `### 段落 ${i + 1}\n\n同一段落重复文字以便撑高页面。Lorem ipsum dolor sit amet，第 ${i + 1} 段。\n\n`),
    )
    .join("\n");

function feedCard(id: number, feed: "news" | "apps", titleSuffix: string): ArticleFeedCard {
  return {
    id,
    slug: `mock-${id}`,
    title: `模拟列表 #${id}：${titleSuffix}`,
    summary: "本地 mock 摘要。",
    segment_id: 1,
    content_type: "article",
    third_party_source: null,
    published_at: "2026-01-10T08:00:00Z",
    fingerprint: `mock-fp-${id}`,
    platform_label: feed === "apps" ? "iOS" : "Web",
    admin_source_key: "mock",
    feed_kind: feed,
    categories: ["mock"],
  };
}

/** 任意数字 id 均可打开详情（与 tryMock 一致） */
export function buildMockArticleDetail(id: number): ArticleDetail {
  const feed: "news" | "apps" = id % 2 === 0 ? "apps" : "news";
  const body = LONG_MD(48);
  return {
    id,
    slug: `mock-article-${id}`,
    title: `Mock 文章 #${id}（${feed === "apps" ? "应用" : "资讯"} · 本地数据）`,
    summary: "用于本地验证详情页布局、侧栏与滚动。无需后端。",
    segment_id: 1,
    content_type: "article",
    third_party_source: null,
    published_at: "2026-05-01T10:00:00Z",
    body,
    feed_kind: feed,
    platform_label: feed === "apps" ? "TestFlight" : "RSS",
    categories: ["本地模拟", "滚动测试"],
    tabs: [
      { label: "概览", summary: "第一段概要", body_md: `## 概览\n\n${LONG_MD(12)}` },
      { label: "附录", summary: "第二段概要", body_md: `## 附录\n\n${LONG_MD(12)}` },
    ],
  };
}

export function buildMockArticlesFeed(feed: "news" | "apps"): ArticlesFeedCursorResponse {
  const items: ArticleFeedCard[] = [];
  for (let id = 1; id <= 30; id++) {
    items.push(
      feedCard(id, feed, "较长标题用于测试侧栏换行与内部滚动 ".repeat(2).trim()),
    );
  }
  return {
    items,
    next_cursor: null,
    has_more: false,
    page_size: 24,
  };
}

/** dev + `VITE_MOCK_PUBLIC_API=true` 时由 `publicGet` 短路，不请求后端 */
export function tryMockPublicGet<T>(path: string): T | null {
  if (import.meta.env.VITE_MOCK_PUBLIC_API !== "true") return null;

  if (path.includes("/articles/feed")) {
    const sp = new URLSearchParams(path.includes("?") ? path.split("?")[1] ?? "" : "");
    const feed = sp.get("feed") === "apps" ? "apps" : "news";
    return buildMockArticlesFeed(feed) as T;
  }

  const m = path.match(/\/api\/public\/v1\/articles\/(\d+)$/);
  if (m) {
    const id = Number(m[1]);
    if (!Number.isFinite(id)) return null;
    return buildMockArticleDetail(id) as T;
  }

  return null;
}
