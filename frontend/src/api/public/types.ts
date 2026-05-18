export type ArticleCard = {
  id: number;
  slug: string | null;
  title: string;
  summary: string;
  segment_id: number;
  content_type: string;
  third_party_source: string | null;
  /** 连接器单次 HTTP 同步日志 id（与后台 product_connector_logs 对应） */
  connector_sync_log_id?: number | null;
  /** 上游 API 条目的稳定 id（如 HN objectID、GitHub node_id） */
  source_external_id?: string | null;
  published_at: string | null;
  /** 可更新热度；应用泳道按日列表内优先于发布时间排序 */
  heat_score?: number;
  updated_at?: string | null;
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
  /** 部分列表字段在详情接口一并返回 */
  platform_label?: string;
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

/** 公开资讯/应用列表：当前时间窗内按热度分页（触底懒加载，与按日/游标互斥） */
export type ArticlesFeedHeatResponse = {
  items: ArticleFeedCard[];
  paginate_by: "heat";
  /** 本页起始偏移（热度池内，与 heat_max 上限一致） */
  offset: number;
  page_size: number;
  /** 参与排序的热度条数上限（默认 100） */
  heat_max: number;
  total: number;
  has_more: boolean;
};

export type ArticlesFeedResponse = ArticlesFeedCursorResponse | ArticlesFeedDayResponse | ArticlesFeedHeatResponse;
