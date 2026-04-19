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
  frequency: string;
  scope_label: string;
  scope_labels: string[];
  notes: string;
  enabled: boolean;
};

async function loadFallbackSourcePresets(): Promise<AdminSourcePresetItem[]> {
  const res = await fetch("/source-presets-fallback.json", { credentials: "same-origin" });
  if (!res.ok) return [];
  const j = (await res.json()) as { items?: AdminSourcePresetItem[] };
  return Array.isArray(j.items) ? j.items : [];
}

/** 优先请求后端；若接口 404/空列表（常见于未重启的旧进程），则使用打包的静态副本。 */
async function loadSourcePresetsWithOrigin(): Promise<{
  items: AdminSourcePresetItem[];
  origin: "api" | "fallback";
}> {
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
  const data = j.data as { items?: AdminSourcePresetItem[] } | undefined;
  const apiItems = data?.items;
  const apiOk =
    res.ok &&
    typeof j.code === "number" &&
    j.code === 0 &&
    Array.isArray(apiItems) &&
    apiItems.length > 0;

  if (apiOk) {
    return { items: apiItems, origin: "api" };
  }

  if (res.status === 401 || res.status === 403) {
    const msg = describeDetail(j.detail) || `HTTP ${res.status}`;
    throw new Error(msg);
  }

  const fb = await loadFallbackSourcePresets();
  if (fb.length > 0) {
    return { items: fb, origin: "fallback" };
  }

  if (!res.ok) {
    const msg = describeDetail(j.detail) || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  if (typeof j.code === "number" && j.code !== 0) {
    const msg = describeDetail(j.detail) || (typeof j.message === "string" ? j.message : "") || "业务错误";
    throw new Error(msg);
  }
  throw new Error("预设模板为空");
}

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
      tickets: number;
      pending_tickets: number;
      admin_users: number;
      audit_logs: number;
      trends: number;
      signals: number;
    }>("/api/admin/v1/overview"),
  sources: (keyword = "") =>
    request<{
      items: Array<{
        source: string;
        enabled: boolean;
        frequency: string;
        api_base: string;
        api_key_masked: string;
        scope_label?: string;
        scope_labels?: string[];
        notes: string;
      }>;
    }>(`/api/admin/v1/sources?keyword=${encodeURIComponent(keyword)}`),
  /** 与后端 MAINSTREAM_ADMIN_SOURCE_PRESETS 同步；旧后端无此路由时使用 public/source-presets-fallback.json */
  sourcePresets: () => loadSourcePresetsWithOrigin(),
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
  deleteSource: (source: string) =>
    request<{ deleted: string }>(`/api/admin/v1/sources/${encodeURIComponent(source)}`, {
      method: "DELETE",
    }),
  seedDemo: () => request("/api/admin/v1/bootstrap/seed-demo", { method: "POST" }),
  clearDemo: () => request("/api/admin/v1/bootstrap/clear-demo", { method: "POST" }),
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
};
