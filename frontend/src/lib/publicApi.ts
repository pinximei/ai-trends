/** 开发默认走 Vite 代理（同源 `/api`）；生产构建请设 `VITE_API_BASE=https://你的API域名` */
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

type Envelope<T> = { code: number; message: string; data: T };

async function parse<T>(res: Response): Promise<T> {
  const j = (await res.json()) as Envelope<T>;
  if (!res.ok || j.code !== 0) {
    throw new Error(j.message || `HTTP ${res.status}`);
  }
  return j.data;
}

export async function publicGet<T>(path: string): Promise<T> {
  const base = API_BASE.replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  const url = path.startsWith("http") ? path : `${base}${p}`;
  const res = await fetch(url);
  return parse<T>(res);
}

export const publicApi = {
  industries: () => publicGet<Array<{ id: number; slug: string; name: string }>>("/api/public/v1/meta/industries"),
  segments: (q?: { industry_slug?: string }) => {
    const sp = new URLSearchParams();
    if (q?.industry_slug) sp.set("industry_slug", q.industry_slug);
    const qs = sp.toString();
    return publicGet<Array<{ id: number; slug: string; name: string; industry_id: number; industry_slug: string }>>(
      `/api/public/v1/meta/segments${qs ? `?${qs}` : ""}`
    );
  },
  hot: (opts?: { industry_slug?: string }) => {
    const sp = new URLSearchParams();
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    const qs = sp.toString();
    return publicGet<{ generated_at: string | null; status: string; payload: Record<string, unknown> }>(
      `/api/public/v1/hot/current${qs ? `?${qs}` : ""}`
    );
  },
  metrics: (q?: { segment_id?: number; industry_slug?: string }) => {
    const sp = new URLSearchParams();
    if (q?.segment_id != null) sp.set("segment_id", String(q.segment_id));
    if (q?.industry_slug) sp.set("industry_slug", q.industry_slug);
    const qs = sp.toString();
    return publicGet<Array<{ id: number; key: string; name: string; unit: string | null; segment_id: number }>>(
      `/api/public/v1/meta/metrics${qs ? `?${qs}` : ""}`
    );
  },
  trendSummary: (opts?: { days?: number; segment_id?: number; industry_slug?: string }) => {
    const sp = new URLSearchParams();
    if (opts?.days != null) sp.set("days", String(opts.days));
    if (opts?.segment_id != null) sp.set("segment_id", String(opts.segment_id));
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    const qs = sp.toString();
    return publicGet<{
      industry: string;
      since: string;
      metrics: Array<{ key: string; name: string; avg: number | null }>;
    }>(`/api/public/v1/trends/summary${qs ? `?${qs}` : ""}`);
  },
  trendSeries: (metricKey: string, opts?: { days?: number; segment_id?: number; industry_slug?: string }) => {
    const sp = new URLSearchParams();
    sp.set("metric_key", metricKey);
    if (opts?.days != null) sp.set("days", String(opts.days));
    if (opts?.segment_id != null) sp.set("segment_id", String(opts.segment_id));
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    return publicGet<{ metric_key: string; points: Array<{ t: string; value: number }> }>(
      `/api/public/v1/trends/series?${sp.toString()}`
    );
  },
  articles: (opts?: {
    industry_slug?: string;
    sort?: "hot" | "latest";
    segment_id?: number;
    /** 逗号分隔，与 segment_id 互斥；用于「其他」板块集合 */
    segment_ids?: string;
    page?: number;
    page_size?: number;
    published_within_days?: number;
    published_on_latest_day?: boolean;
  }) => {
    const sp = new URLSearchParams();
    if (opts?.industry_slug) sp.set("industry_slug", opts.industry_slug);
    if (opts?.sort) sp.set("sort", opts.sort);
    if (opts?.segment_id != null) sp.set("segment_id", String(opts.segment_id));
    if (opts?.segment_ids) sp.set("segment_ids", opts.segment_ids);
    if (opts?.page) sp.set("page", String(opts.page));
    if (opts?.page_size) sp.set("page_size", String(opts.page_size));
    if (opts?.published_within_days != null) sp.set("published_within_days", String(opts.published_within_days));
    if (opts?.published_on_latest_day) sp.set("published_on_latest_day", "true");
    const qs = sp.toString();
    return publicGet<{ items: ArticleCard[]; total: number }>(`/api/public/v1/articles${qs ? `?${qs}` : ""}`);
  },
  article: (id: number) => publicGet<ArticleDetail>(`/api/public/v1/articles/${id}`),
  page: (slug: string) => publicGet<{ title: string; body_md: string; updated_at: string }>(`/api/public/v1/pages/${slug}`),
  /** 单板块下代表产品/内容条目的 TOP N（热度序 + 活跃指数；优先热门快照顺序） */
  segmentTopProducts: (segmentId: number, opts?: { limit?: number }) => {
    const sp = new URLSearchParams();
    sp.set("limit", String(opts?.limit ?? 10));
    return publicGet<{
      segment_id: number;
      segment_name: string;
      limit: number;
      items: Array<{
        rank: number;
        id: number;
        slug: string | null;
        title: string;
        summary: string;
        published_at: string | null;
        heat_score: number;
        activity_index: number;
        source: string | null;
      }>;
    }>(`/api/public/v1/segments/${segmentId}/top-products?${sp.toString()}`);
  },
};

export type ArticleCard = {
  id: number;
  slug: string | null;
  title: string;
  summary: string;
  segment_id: number;
  content_type: string;
  third_party_source: string | null;
  published_at: string | null;
};

export type ArticleDetail = ArticleCard & { body: string };
