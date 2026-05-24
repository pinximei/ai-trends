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
  /** 连接器解析的主链接（GitHub 仓库页、HN 讨论帖等） */
  source_original_url?: string | null;
  published_at: string | null;
  /** 可更新热度；应用泳道按日列表内优先于发布时间排序 */
  heat_score?: number;
  updated_at?: string | null;
  /** GitHub 等：总 star（重复同步时刷新） */
  engagement_stars_total?: number | null;
  /** GitHub Trending：今日 star 增速 */
  engagement_stars_today?: number | null;
  /** Product Hunt / HF Spaces 等封面图 */
  cover_image_url?: string | null;
  categories?: string[];
  /** LLM 可复刻性档位 S/A/B/C（S=高可复刻） */
  replication_tier?: string | null;
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
  /** 列表卡片主文案：对应 tab「描述」或 summary */
  card_description?: string;
  /** 列表卡片：对应 tab「功能亮点」或资讯「要点」 */
  card_highlights?: string;
};

export type ArticleTab = { label: string; summary: string; body_md: string };

export type ArticleDetailProfile =
  | "product_launch"
  | "ai_space"
  | "open_source"
  | "news_wire"
  | "platform_api"
  | "news_article"
  | "app_product";

export type ArticleDetail = ArticleCard & {
  body: string;
  categories?: string[];
  feed_kind?: "news" | "apps";
  admin_source_key?: string;
  /** 部分列表字段在详情接口一并返回 */
  platform_label?: string;
  /** 按数据源推断的详情版式 id */
  detail_profile?: ArticleDetailProfile;
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
  /** 本页所含日历日数（默认 3） */
  days_per_page: number;
  /** 本页最新一日（UTC） */
  day_utc: string | null;
  /** 本页最旧一日（UTC）；与 day_utc 相同时为单日页 */
  day_utc_end?: string | null;
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
