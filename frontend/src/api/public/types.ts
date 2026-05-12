export type ArticleCard = {
  id: number;
  slug: string | null;
  title: string;
  summary: string;
  segment_id: number;
  content_type: string;
  third_party_source: string | null;
  /** 连接器原始条目 URL（若有） */
  source_original_url?: string | null;
  published_at: string | null;
  categories?: string[];
};

export type ArticleTabSummary = { label: string; summary: string };

export type ArticleFeedCard = ArticleCard & {
  fingerprint: string;
  platform_label: string;
  admin_source_key: string;
  feed_kind: "news" | "apps";
  categories?: string[];
  /** 列表卡片：各 tab 概要（与详情 tabs 对应） */
  tab_summaries?: ArticleTabSummary[];
};

export type ArticleTab = { label: string; summary: string; body_md: string };

export type ArticleDetail = ArticleCard & {
  body: string;
  categories?: string[];
  feed_kind?: "news" | "apps";
  admin_source_key?: string;
  /** 分 tab：label + 概要 + Markdown 详情 */
  tabs?: ArticleTab[];
};

/** 公开资讯/应用列表：按条数游标（默认） */
export type ArticlesFeedCursorResponse = {
  items: ArticleFeedCard[];
  next_cursor: string | null;
  has_more: boolean;
  page_size: number;
};

/** 公开资讯/应用列表：按 UTC 自然日整页 */
export type ArticlesFeedDayResponse = {
  items: ArticleFeedCard[];
  paginate_by: "day";
  page: number;
  total_pages: number;
  day_utc: string | null;
  has_prev: boolean;
  has_next: boolean;
  days_scan_truncated: boolean;
};

export type ArticlesFeedResponse = ArticlesFeedCursorResponse | ArticlesFeedDayResponse;
