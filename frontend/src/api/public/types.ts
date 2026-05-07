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

export type ArticleFeedCard = ArticleCard & {
  fingerprint: string;
  platform_label: string;
  admin_source_key: string;
  feed_kind: "news" | "apps";
  categories?: string[];
};

export type ArticleDetail = ArticleCard & {
  body: string;
  categories?: string[];
  feed_kind?: "news" | "apps";
  admin_source_key?: string;
};
