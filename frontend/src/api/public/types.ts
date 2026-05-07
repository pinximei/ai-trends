export type ArticleCard = {
  id: number;
  slug: string | null;
  title: string;
  summary: string;
  segment_id: number;
  content_type: string;
  third_party_source: string | null;
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
