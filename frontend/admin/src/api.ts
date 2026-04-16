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

export const adminApi = {
  me: () =>
    request<{ username: string; role: string; expires_at: string; password_min_length: number }>("/api/admin/v1/auth/me"),
  login: (username: string, password: string) =>
    request("/api/admin/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  changePassword: (old_password: string, new_password: string) =>
    request("/api/admin/v1/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password, new_password }),
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
  pagesPlan: () => request<{ items: Array<{ key: string; title: string; description: string; status: "ready" | "planned" }> }>("/api/admin/v1/pages-plan"),
  sources: (keyword = "") =>
    request<{ items: Array<{ source: string; enabled: boolean; frequency: string; api_base: string; api_key_masked: string; notes: string }> }>(
      `/api/admin/v1/sources?keyword=${encodeURIComponent(keyword)}`
    ),
  saveSource: (payload: unknown) =>
    request("/api/admin/v1/sources", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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
  tickets: (status = "", keyword = "") =>
    request<{
      items: Array<{
        ticket_id: string;
        status: string;
        request_type: string;
        target_signal_id: string;
        reason: string;
        requester_contact: string;
        submitted_at: string;
      }>;
    }>(
      `/api/admin/v1/compliance/removal-requests?status=${encodeURIComponent(status)}&keyword=${encodeURIComponent(keyword)}`
    ),
  resolveTicket: (ticketId: string) =>
    request(`/api/admin/v1/compliance/removal-requests/${encodeURIComponent(ticketId)}/resolve`, { method: "POST" }),
  audits: () =>
    request<{ items: Array<{ actor: string; action: string; target: string; detail: string; request_id: string; created_at: string }> }>(
      "/api/admin/v1/audit-logs?limit=100"
    ),
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
  getSettings: () => request<{ password_min_length: number; lock_minutes: number; max_failed_attempts: number }>("/api/admin/v1/settings"),
  saveSettings: (payload: unknown) =>
    request("/api/admin/v1/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  health: () => request<{ status: string; db: string; time: string; metrics: Record<string, number> }>("/api/admin/v1/health"),
  queryTrends: (keyword = "", lifecycle = "") =>
    request<{
      items: Array<{
        trend_key: string;
        lifecycle_stage: string;
        trend_score: number;
        confidence: number;
        sample_size: number;
        updated_at: string;
      }>;
    }>(`/api/admin/v1/query/trends?keyword=${encodeURIComponent(keyword)}&lifecycle=${encodeURIComponent(lifecycle)}`),
  querySignals: (keyword = "", source = "", status = "") =>
    request<{
      items: Array<{
        signal_id: string;
        trend_key: string;
        source: string;
        status: string;
        evidence_score: number;
        created_at: string;
      }>;
    }>(
      `/api/admin/v1/query/signals?keyword=${encodeURIComponent(keyword)}&source=${encodeURIComponent(source)}&status=${encodeURIComponent(status)}`
    ),
  updateTrendOps: (trendKey: string, payload: { lifecycle_stage?: string; trend_score?: number }) =>
    request(`/api/admin/v1/trend-ops/${encodeURIComponent(trendKey)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateSignalOps: (signalId: string, payload: { status?: string }) =>
    request(`/api/admin/v1/signal-ops/${encodeURIComponent(signalId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
};
