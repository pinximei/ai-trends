import { publicGet, publicPost } from "./client";
import type { ArticleDetail, ArticlesFeedResponse } from "./types";

export { publicGet, publicPost } from "./client";
export type { ArticleCard, ArticleDetail, ArticleFeedCard, ArticleTab, ArticleTabSummary, ArticlesFeedResponse, ArticlesFeedDayResponse, ArticlesFeedCursorResponse, ArticlesFeedHeatResponse } from "./types";

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
    paginate_by?: "cursor" | "day" | "heat";
    page?: number;
    days_per_page?: number;
    heat_offset?: number;
    heat_page_size?: number;
    heat_max_ranked?: number;
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
    if (opts.paginate_by) sp.set("paginate_by", opts.paginate_by);
    if (opts.page != null) sp.set("page", String(opts.page));
    if (opts.days_per_page != null) sp.set("days_per_page", String(opts.days_per_page));
    if (opts.heat_offset != null) sp.set("heat_offset", String(opts.heat_offset));
    if (opts.heat_page_size != null) sp.set("heat_page_size", String(opts.heat_page_size));
    if (opts.heat_max_ranked != null) sp.set("heat_max_ranked", String(opts.heat_max_ranked));
    if (opts.page_size != null) sp.set("page_size", String(opts.page_size));
    if (opts.cursor) sp.set("cursor", opts.cursor);
    if (opts.exclude_fp) sp.set("exclude_fp", opts.exclude_fp);
    if (opts.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts.published_on_latest_day) sp.set("published_on_latest_day", "true");
    if (opts.category) sp.set("category", opts.category);
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    return publicGet<ArticlesFeedResponse>(`/api/public/v1/articles/feed?${sp.toString()}`);
  },
  article: (id: number) => publicGet<ArticleDetail>(`/api/public/v1/articles/${id}`),
  page: (slug: string) => {
    return publicGet<{ title: string; body_md: string; updated_at: string }>(
      `/api/public/v1/pages/${encodeURIComponent(slug)}`,
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
  newsletterSubscribe: (email: string) =>
    publicPost<{ subscribed: boolean }>("/api/public/v1/newsletter/subscribe", { email }),
};
