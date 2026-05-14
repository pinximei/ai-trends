type Envelope<T> = { code: number; message: string; data: T };

/** FastAPI：detail 可能是字符串或校验错误数组，直接塞进 Error 会显示 [object Object] */
function describeDetail(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const o = item as { msg?: string; loc?: unknown[] };
          const path = Array.isArray(o.loc) ? o.loc.filter((x) => x !== "body").join(".") : "";
          return [path, o.msg].filter(Boolean).join(" ");
        }
        try {
          return JSON.stringify(item);
        } catch {
          return String(item);
        }
      })
      .filter(Boolean)
      .join("；");
  }
  if (typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return "请求参数有误";
    }
  }
  return String(detail);
}

async function parse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let j: Record<string, unknown> = {};
  if (text) {
    try {
      j = JSON.parse(text) as Record<string, unknown>;
    } catch {
      throw new Error(text.slice(0, 240) || `HTTP ${res.status}`);
    }
  }

  if (!res.ok) {
    const msg = describeDetail(j.detail) || (typeof j.message === "string" ? j.message : "") || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  const code = j.code;
  if (typeof code === "number" && code !== 0) {
    const msg = describeDetail(j.detail) || (typeof j.message === "string" ? j.message : "") || "业务错误";
    throw new Error(msg);
  }

  return j.data as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: "include", ...init });
  return parse<T>(res);
}

export type AdminSourcePresetItem = {
  source: string;
  label: string;
  api_base: string;
  scope_label: string;
  scope_labels: string[];
  notes: string;
  enabled: boolean;
  /** false：免 Key 公开模板，卡片不展示密钥输入 */
  show_api_key_field?: boolean;
  /** true：另展示 OAuth Client Secret（当前仅 product_hunt） */
  show_app_secret_field?: boolean;
};

/** 仅从 GET /api/admin/v1/sources/presets（数据库）加载，不使用前端静态 JSON。 */
async function loadSourcePresetsFromApi(): Promise<{ items: AdminSourcePresetItem[] }> {
  const res = await fetch("/api/admin/v1/sources/presets", { credentials: "include" });
  const text = await res.text();
  let j: Record<string, unknown> = {};
  if (text) {
    try {
      j = JSON.parse(text) as Record<string, unknown>;
    } catch {
      j = {};
    }
  }
  if (res.status === 401 || res.status === 403) {
    const msg = describeDetail(j.detail) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (!res.ok) {
    const msg = describeDetail(j.detail) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (typeof j.code === "number" && j.code !== 0) {
    const msg = describeDetail(j.detail) || (typeof j.message === "string" ? j.message : "") || "业务错误";
    throw new Error(msg);
  }
  const data = j.data as { items?: AdminSourcePresetItem[] } | undefined;
  const items = Array.isArray(data?.items) ? data!.items! : [];
  return { items };
}

export type ThemeFetchConnectorDetail = {
  connector_id: number;
  name: string;
  http_status?: number;
  articles_created?: number;
  rows_ingested?: number;
  error?: string | null;
};

export type ThemeFetchResult = {
  taxonomy_synced: boolean;
  theme_applied_to_url: boolean;
  connectors_total: number;
  ok: number;
  fail: number;
  details: ThemeFetchConnectorDetail[];
};

export const adminApi = {
  me: () =>
    request<{ username: string; role: string; expires_at: string; password_min_length: number }>("/api/admin/v1/auth/me"),
  login: (username: string, password: string) =>
    request("/api/admin/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request("/api/admin/v1/auth/logout", { method: "POST" }),
  overview: () =>
    request<{
      sources: number;
      admin_users: number;
      trends: number;
      signals: number;
    }>("/api/admin/v1/overview"),
  sources: (keyword = "") =>
    request<{
      items: Array<{
        source: string;
        enabled: boolean;
        api_base: string;
        api_key_masked: string;
        app_secret_masked?: string;
        scope_label?: string;
        scope_labels?: string[];
        notes: string;
      }>;
    }>(`/api/admin/v1/sources?keyword=${encodeURIComponent(keyword)}`),
  /** 数据源模板列表：与 admin_source_configs 一致，仅后端数据库。 */
  sourcePresets: () => loadSourcePresetsFromApi(),
  saveSource: (payload: unknown) =>
    request("/api/admin/v1/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  /** 对已保存 source 或未入库的 api_base 发起 GET，可选 Bearer api_key（不落库） */
  testSource: (payload: {
    source?: string;
    api_base?: string;
    api_key?: string;
    /** GitLab 个人访问令牌用 private_token */
    auth_mode?: "bearer" | "private_token";
  }) =>
    request<{ http_status: number; snippet: string; ok: boolean; url_tested: string }>("/api/admin/v1/sources/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  seedDemo: () => request("/api/admin/v1/bootstrap/seed-demo", { method: "POST" }),
  clearDemo: () => request("/api/admin/v1/bootstrap/clear-demo", { method: "POST" }),
  /** 仅管理员：清空连接器入库数据（文章/指标点/同步日志/热门快照/LLM 用量），重置连接器上次同步时间 */
  clearProductIngestData: () =>
    request<Record<string, number>>("/api/admin/v1/product/ingest-data/clear", { method: "POST" }),
  /** 仅管理员：先按数据源领域同步 taxonomy，再对所有已启用连接器立即拉取；可选 theme 在无 q 等参数时写入 URL 的 q */
  themeFetchProductData: (opts?: { theme?: string }) =>
    request<ThemeFetchResult>("/api/admin/v1/product/ingest/theme-fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts?.theme?.trim() ? { theme: opts.theme.trim() } : {}),
    }),
  dbInfo: () =>
    request<{
      mode: string;
      database_url: string;
      test_url: string;
      prod_url: string;
    }>("/api/admin/v1/system/db-info"),
  users: (role = "", keyword = "") =>
    request<{
      items: Array<{
        username: string;
        role: string;
        enabled: boolean;
        failed_attempts: number;
        locked_until: string | null;
        updated_at: string;
      }>;
    }>(`/api/admin/v1/users?role=${encodeURIComponent(role)}&keyword=${encodeURIComponent(keyword)}`),
  createUser: (payload: unknown) =>
    request("/api/admin/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateUser: (username: string, payload: unknown) =>
    request(`/api/admin/v1/users/${encodeURIComponent(username)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteUser: (username: string) =>
    request<{ deleted: string }>(`/api/admin/v1/users/${encodeURIComponent(username)}`, {
      method: "DELETE",
    }),
  getSettings: () => request<{ password_min_length: number; lock_minutes: number; max_failed_attempts: number }>("/api/admin/v1/settings"),
  saveSettings: (payload: unknown) =>
    request("/api/admin/v1/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  health: () => request<{ status: string; db: string; time: string; metrics: Record<string, number> }>("/api/admin/v1/health"),
  dataTables: () =>
    request<
      Array<{
        key: string;
        label: string;
        has_time: boolean;
        time_hint: string | null;
        dimensions: Array<{ name: string; label: string }>;
      }>
    >("/api/admin/v1/data/tables"),
  dataRows: (opts: {
    table: string;
    since?: string;
    until?: string;
    segment_id?: number;
    metric_id?: number;
    status?: string;
    limit?: number;
    offset?: number;
  }) => {
    const sp = new URLSearchParams();
    sp.set("table", opts.table);
    if (opts.since) sp.set("since", opts.since);
    if (opts.until) sp.set("until", opts.until);
    if (opts.segment_id != null) sp.set("segment_id", String(opts.segment_id));
    if (opts.metric_id != null) sp.set("metric_id", String(opts.metric_id));
    if (opts.status) sp.set("status", opts.status);
    if (opts.limit != null) sp.set("limit", String(opts.limit));
    if (opts.offset != null) sp.set("offset", String(opts.offset));
    return request<{
      table: string;
      columns: string[];
      rows: Record<string, unknown>[];
      limit: number;
      offset: number;
      count: number;
    }>(`/api/admin/v1/data/rows?${sp.toString()}`);
  },
  dataRowsCount: (opts: {
    table: string;
    since?: string;
    until?: string;
    segment_id?: number;
    metric_id?: number;
    status?: string;
  }) => {
    const sp = new URLSearchParams();
    sp.set("table", opts.table);
    if (opts.since) sp.set("since", opts.since);
    if (opts.until) sp.set("until", opts.until);
    if (opts.segment_id != null) sp.set("segment_id", String(opts.segment_id));
    if (opts.metric_id != null) sp.set("metric_id", String(opts.metric_id));
    if (opts.status) sp.set("status", opts.status);
    return request<{ table: string; total: number }>(`/api/admin/v1/data/rows/count?${sp.toString()}`);
  },
  /** 数据查询筛选：板块 / 指标维度 */
  productSegments: (industrySlug = "ai") =>
    request<Array<Record<string, unknown>>>(`/api/admin/v1/product/segments?industry_slug=${encodeURIComponent(industrySlug)}`),
  productMetrics: () => request<Array<Record<string, unknown>>>("/api/admin/v1/product/metrics"),
  getLlmSettings: () =>
    request<{
      provider: string;
      base_url: string;
      model: string;
      api_key_masked: string;
      has_api_key: boolean;
      pipeline: Array<{ id: string; label: string }>;
    }>("/api/admin/v1/product/settings/llm"),
  saveLlmSettings: (payload: { provider?: string; base_url?: string; model?: string; api_key?: string }) =>
    request<{
      provider: string;
      base_url: string;
      model: string;
      api_key_masked: string;
      has_api_key: boolean;
      pipeline: Array<{ id: string; label: string }>;
    }>("/api/admin/v1/product/settings/llm", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getSchedulerSettings: () =>
    request<{
      connector_scheduler_enabled: boolean;
      connector_sync_interval_hours: number;
      last_connector_batch_at: string | null;
      gate_interval_minutes: number;
    }>("/api/admin/v1/product/settings/scheduler"),
  getRuntimeSettings: () =>
    request<{
      cors_origins_csv: string;
      jwt_ttl_seconds: number;
      allowed_skew_seconds: number;
      require_https: boolean;
      allow_insecure_localhost: boolean;
      admin_cookie_secure: boolean;
      app_env: string;
      demo_seed_enabled: boolean | null;
      demo_seed_effective: boolean;
      legacy_admin_enabled: boolean;
      app_release_label: string;
      hot_llm_model: string;
      secrets_note: string;
    }>("/api/admin/v1/product/settings/runtime"),
  saveRuntimeSettings: (payload: Record<string, unknown>) =>
    request<{
      cors_origins_csv: string;
      jwt_ttl_seconds: number;
      allowed_skew_seconds: number;
      require_https: boolean;
      allow_insecure_localhost: boolean;
      admin_cookie_secure: boolean;
      app_env: string;
      demo_seed_enabled: boolean | null;
      demo_seed_effective: boolean;
      legacy_admin_enabled: boolean;
      app_release_label: string;
      hot_llm_model: string;
      secrets_note: string;
    }>("/api/admin/v1/product/settings/runtime", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  saveSchedulerSettings: (payload: { connector_scheduler_enabled?: boolean; connector_sync_interval_hours?: number }) =>
    request<{
      connector_scheduler_enabled: boolean;
      connector_sync_interval_hours: number;
      last_connector_batch_at: string | null;
      gate_interval_minutes: number;
    }>("/api/admin/v1/product/settings/scheduler", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getNewsletterSettings: () =>
    request<{
      cron_enabled: boolean;
      generate_enabled: boolean;
      send_enabled: boolean;
      daily_digest_job_enabled: boolean;
      subscribe_verify_mx: boolean;
      article_limit: number;
      daily_hour: number;
      daily_minute: number;
      public_site_base_url: string;
      smtp_host: string;
      smtp_port: number;
      smtp_user: string;
      smtp_password_masked: string;
      has_smtp_password: boolean;
      mail_from: string;
      smtp_use_tls: boolean;
      bcc_batch: number;
      footer_note: string;
    }>("/api/admin/v1/product/settings/newsletter"),
  saveNewsletterSettings: (payload: Record<string, unknown>) =>
    request<{
      cron_enabled: boolean;
      generate_enabled: boolean;
      send_enabled: boolean;
      daily_digest_job_enabled: boolean;
      subscribe_verify_mx: boolean;
      article_limit: number;
      daily_hour: number;
      daily_minute: number;
      public_site_base_url: string;
      smtp_host: string;
      smtp_port: number;
      smtp_user: string;
      smtp_password_masked: string;
      has_smtp_password: boolean;
      mail_from: string;
      smtp_use_tls: boolean;
      bcc_batch: number;
      footer_note: string;
    }>("/api/admin/v1/product/settings/newsletter", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  softwarePackages: (limit = 80) =>
    request<
      Array<{
        id: number;
        title: string;
        platform: string;
        category_slug: string;
        category_label: string;
        status: string;
        sort_order: number;
        has_artifact: boolean;
        store_url: string;
        created_at: string;
      }>
    >(`/api/admin/v1/product/software/packages?limit=${encodeURIComponent(String(limit))}`),
  uploadSoftwarePackage: (form: FormData) =>
    request<{ id: number; title: string; platform: string; download_path: string }>("/api/admin/v1/product/software/packages", {
      method: "POST",
      body: form,
    }),
  deleteSoftwarePackage: (packageId: number) =>
    request<{ deleted: number }>(`/api/admin/v1/product/software/packages/${packageId}`, {
      method: "DELETE",
    }),
};
