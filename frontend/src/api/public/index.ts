import { publicGet, publicPost } from "./client";
import type { ArticleDetail, ArticleFeedCard, ArticlesFeedResponse } from "./types";

export { publicGet, publicPost } from "./client";
export type { ArticleCard, ArticleDetail, ArticleFeedCard, ArticleTab, ArticleTabSummary, ArticlesFeedResponse, ArticlesFeedDayResponse, ArticlesFeedCursorResponse, ArticlesFeedHeatResponse } from "./types";

export const publicApi = {
  articleCategories: (opts: {
    feed: "news" | "apps";
    industry_slug?: string;
    published_within_days?: number;
    published_on_latest_day?: boolean;
    source?: string | null;
    q?: string | null;
    replication_tiers?: string | null;
  }) => {
    const sp = new URLSearchParams();
    sp.set("feed", opts.feed);
    if (opts.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts.published_on_latest_day) sp.set("published_on_latest_day", "true");
    if (opts.source) sp.set("source", opts.source);
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    if (opts.replication_tiers) sp.set("replication_tiers", opts.replication_tiers);
    return publicGet<Array<{ label: string; count: number }>>(`/api/public/v1/articles/categories?${sp.toString()}`);
  },
  articleSources: (opts: {
    feed: "news" | "apps";
    industry_slug?: string;
    published_within_days?: number;
    published_on_latest_day?: boolean;
    category?: string | null;
    q?: string | null;
    replication_tiers?: string | null;
  }) => {
    const sp = new URLSearchParams();
    sp.set("feed", opts.feed);
    if (opts.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts.published_on_latest_day) sp.set("published_on_latest_day", "true");
    if (opts.category) sp.set("category", opts.category);
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    if (opts.replication_tiers) sp.set("replication_tiers", opts.replication_tiers);
    return publicGet<Array<{ key: string; label: string; count: number }>>(
      `/api/public/v1/articles/sources?${sp.toString()}`,
    );
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
    source?: string | null;
    q?: string | null;
    replication_tiers?: string | null;
    sort_replicable?: boolean;
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
    if (opts.source) sp.set("source", opts.source);
    if (opts.q && opts.q.trim()) sp.set("q", opts.q.trim());
    if (opts.replication_tiers) sp.set("replication_tiers", opts.replication_tiers);
    if (opts.sort_replicable) sp.set("sort_replicable", "true");
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
  homeDashboard: (opts?: {
    industry_slug?: string;
    news_limit?: number;
    apps_limit?: number;
    replicable_apps_limit?: number;
    published_within_days?: number;
  }) => {
    const sp = new URLSearchParams();
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts?.news_limit != null) sp.set("news_limit", String(opts.news_limit));
    if (opts?.apps_limit != null) sp.set("apps_limit", String(opts.apps_limit));
    if (opts?.replicable_apps_limit != null) sp.set("replicable_apps_limit", String(opts.replicable_apps_limit));
    if (opts?.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    const qs = sp.toString();
    return publicGet<{
      news: ArticleFeedCard[];
      apps: ArticleFeedCard[];
      highlight_replicable_apps: ArticleFeedCard[];
      featured_news_id: number | null;
      pick_window_days: number;
      scoring_note: string;
      trend: {
        sparkline: Array<{ day: string; count: number }>;
        apps_count: number;
        news_count: number;
        apps_growth_pct: number | null;
        news_growth_pct: number | null;
      };
      news_source_lanes: Array<{ source_key: string; source_label: string; items: ArticleFeedCard[] }>;
      apps_source_lanes: Array<{ source_key: string; source_label: string; items: ArticleFeedCard[] }>;
      source_facets: Array<{ key: string; label: string; news_count: number; apps_count: number }>;
      top_categories: Array<{ label: string; count: number }>;
      active_source_count: number;
    }>(`/api/public/v1/home/dashboard${qs ? `?${qs}` : ""}`);
  },
  homeEditorialPicks: (opts?: {
    industry_slug?: string;
    news_limit?: number;
    apps_limit?: number;
    published_within_days?: number;
  }) => {
    const sp = new URLSearchParams();
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts?.news_limit != null) sp.set("news_limit", String(opts.news_limit));
    if (opts?.apps_limit != null) sp.set("apps_limit", String(opts.apps_limit));
    if (opts?.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    const qs = sp.toString();
    return publicGet<{
      news: ArticleFeedCard[];
      apps: ArticleFeedCard[];
      featured_news_id: number | null;
      pick_window_days: number;
      scoring_note: string;
    }>(`/api/public/v1/home/editorial-picks${qs ? `?${qs}` : ""}`);
  },
  homeTrendOverview: (opts?: { industry_slug?: string; sparkline_days?: number; period_days?: number }) => {
    const sp = new URLSearchParams();
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts?.sparkline_days != null) sp.set("sparkline_days", String(opts.sparkline_days));
    if (opts?.period_days != null) sp.set("period_days", String(opts.period_days));
    const qs = sp.toString();
    return publicGet<{
      sparkline: Array<{ day: string; count: number }>;
      apps_count: number;
      news_count: number;
      apps_growth_pct: number | null;
      news_growth_pct: number | null;
    }>(`/api/public/v1/home/trend-overview${qs ? `?${qs}` : ""}`);
  },
};
