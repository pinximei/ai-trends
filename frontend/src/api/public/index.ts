import { publicGet } from "./client";
import type { ArticleDetail, ArticleFeedCard } from "./types";
import type { Lang } from "@/i18n";

export { publicGet } from "./client";
export type { ArticleCard, ArticleDetail, ArticleFeedCard, ArticleTab, ArticleTabSummary } from "./types";

export const publicApi = {
  articleCategories: (opts: {
    feed: "news" | "apps";
    industry_slug?: string;
    published_within_days?: number;
    published_on_latest_day?: boolean;
    q?: string | null;
  }) => {
    const sp = new URLSearchParams();
    sp.set("feed", opts.feed);
    if (opts.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts.published_on_latest_day) sp.set("published_on_latest_day", "true");
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    return publicGet<Array<{ label: string; count: number }>>(`/api/public/v1/articles/categories?${sp.toString()}`);
  },
  articlesFeed: (opts: {
    feed: "news" | "apps";
    industry_slug?: string;
    page_size?: number;
    cursor?: string | null;
    exclude_fp?: string;
    published_within_days?: number;
    published_on_latest_day?: boolean;
    category?: string | null;
    q?: string | null;
  }) => {
    const sp = new URLSearchParams();
    sp.set("feed", opts.feed);
    if (opts.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts.page_size != null) sp.set("page_size", String(opts.page_size));
    if (opts.cursor) sp.set("cursor", opts.cursor);
    if (opts.exclude_fp) sp.set("exclude_fp", opts.exclude_fp);
    if (opts.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts.published_on_latest_day) sp.set("published_on_latest_day", "true");
    if (opts.category) sp.set("category", opts.category);
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    return publicGet<{ items: ArticleFeedCard[]; next_cursor: string | null; has_more: boolean; page_size: number }>(
      `/api/public/v1/articles/feed?${sp.toString()}`
    );
  },
  article: (id: number) => publicGet<ArticleDetail>(`/api/public/v1/articles/${id}`),
  page: (slug: string, opts?: { lang?: Lang }) => {
    const sp = new URLSearchParams();
    if (opts?.lang === "en") sp.set("lang", "en");
    const qs = sp.toString();
    return publicGet<{ title: string; body_md: string; updated_at: string }>(
      `/api/public/v1/pages/${encodeURIComponent(slug)}${qs ? `?${qs}` : ""}`,
    );
  },
  softwareCategories: () =>
    publicGet<Array<{ slug: string; label: string; count: number }>>("/api/public/v1/software/categories"),
  softwareDownloads: (opts?: { platform?: "all" | "ios" | "android"; category_slug?: string; limit?: number }) => {
    const sp = new URLSearchParams();
    if (opts?.platform && opts.platform !== "all") sp.set("platform", opts.platform);
    if (opts?.category_slug) sp.set("category_slug", opts.category_slug);
    if (opts?.limit != null) sp.set("limit", String(opts.limit));
    const qs = sp.toString();
    return publicGet<
      Array<{
        id: number;
        title: string;
        summary: string;
        platform: string;
        category_slug: string;
        category_label: string;
        store_url: string;
        download_url: string;
        download_mode: "direct" | "external" | "none";
        icon_url: string | null;
        sort_order: number;
      }>
    >(`/api/public/v1/software/downloads${qs ? `?${qs}` : ""}`);
  },
};
