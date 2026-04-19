import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { adminApi } from "./api";
import { DataQueryPanel } from "./DataQueryPanel";
import { PRESET_TEMPLATE_SOURCE_SLUGS } from "./presetTemplateSlugs";

function zhRole(role: string | undefined) {
  if (!role) return "—";
  if (role === "admin") return "管理员";
  if (role === "operator") return "运营";
  if (role === "viewer") return "仅浏览";
  return role;
}

function formatSourceFrequency(f: string | undefined): string {
  const v = (f || "").trim();
  if (v === "daily_07:00") return "每日 07:00";
  if (v === "hourly") return "每小时";
  if (v === "daily") return "每天";
  if (v === "weekly") return "每周";
  return v || "—";
}

function friendlyErr(msg: string): string {
  const m = msg.trim();
  if (/^not\s*found$/i.test(m) || m === "Not Found") {
    return "接口返回 404：请确认后端已启动、路径正确，并已登录后台。";
  }
  if (m === "forbidden" || m === "Forbidden") {
    return "没有权限执行该操作，请确认当前账号角色是否满足要求。";
  }
  if (m.includes("unauthenticated") || m.includes("session expired")) {
    return "登录已失效，请重新登录。";
  }
  if (/password too short/i.test(m)) {
    const n = m.match(/min=(\d+)/)?.[1];
    return n ? `密码长度不足：至少需要 ${n} 位（与下方安全策略一致）。` : "密码长度不符合策略。";
  }
  if (m.includes("username exists")) return "该用户名已被占用，请换一个。";
  if (m.includes("cannot downgrade yourself")) return "不能降低自己的管理员权限。";
  if (m.includes("cannot disable yourself")) return "不能禁用自己的账号。";
  if (m.includes("cannot delete your own account")) return "不能删除当前登录账号。";
  if (/invalid credentials|incorrect password|401/i.test(m)) return "用户名或密码错误。";
  return msg;
}

type Me = { username: string; role: string; expires_at: string; password_min_length: number };
type Source = {
  source: string;
  enabled: boolean;
  frequency: string;
  api_base: string;
  api_key_masked: string;
  scope_label?: string;
  scope_labels?: string[];
  notes: string;
};
type AdminUser = {
  username: string;
  role: string;
  enabled: boolean;
  failed_attempts: number;
  locked_until: string | null;
  created_at?: string;
  updated_at: string;
};
type Health = { status: string; db: string; time: string; metrics: Record<string, number> };
type Settings = { password_min_length: number };
type DbInfo = { mode: string; database_url: string; test_url: string; prod_url: string };
type TabKey = "overview" | "queries" | "sources" | "settings";

type SourcePresetRow = {
  source: string;
  label: string;
  api_base: string;
  frequency: string;
  scope_label: string;
  scope_labels: string[];
  notes: string;
  enabled: boolean;
};

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState("");
  const [loginSubmitting, setLoginSubmitting] = useState(false);
  const [tab, setTabState] = useState<TabKey>("overview");
  const [refreshSeq, setRefreshSeq] = useState(0);

  const [sources, setSources] = useState<Source[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [overview, setOverview] = useState<Record<string, number>>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [settings, setSettings] = useState<Settings>({ password_min_length: 10 });

  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [sourceForm, setSourceForm] = useState({
    source: "",
    enabled: true,
    frequency: "daily_07:00",
    api_base: "",
    api_key: "",
    scope_labels: [""] as string[],
    notes: "",
  });
  const [userForm, setUserForm] = useState({ username: "", password: "", role: "viewer", enabled: true });
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [draftRole, setDraftRole] = useState<"viewer" | "operator" | "admin">("viewer");
  const [draftEnabled, setDraftEnabled] = useState(true);
  const [draftNewPassword, setDraftNewPassword] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const [sourceSearch, setSourceSearch] = useState("");
  const [sourcePresets, setSourcePresets] = useState<SourcePresetRow[]>([]);
  const [sourcePresetsLoading, setSourcePresetsLoading] = useState(false);
  const [sourcePresetsError, setSourcePresetsError] = useState("");
  const [sourcePresetsOrigin, setSourcePresetsOrigin] = useState<"api" | "fallback" | null>(null);
  /** 数据源卡片「测试连接」可选密钥（仅浏览器内存，不写库） */
  const [sourceTestKeys, setSourceTestKeys] = useState<Record<string, string>>({});
  /** Bearer（OAuth）或 GitLab PRIVATE-TOKEN */
  const [sourceTestAuth, setSourceTestAuth] = useState<Record<string, "bearer" | "private_token">>({});
  const [formTestAuth, setFormTestAuth] = useState<"bearer" | "private_token">("bearer");
  const [sourceTestLoading, setSourceTestLoading] = useState<string | null>(null);
  const [sourceTestResult, setSourceTestResult] = useState<{
    key: string;
    ok: boolean;
    http_status: number;
    snippet: string;
    url_tested?: string;
  } | null>(null);

  const isAuthed = useMemo(() => !!me, [me]);
  const canManageSettings = me?.role === "admin";
  const canOperate = me?.role === "admin" || me?.role === "operator";

  const setTab = useCallback((t: TabKey) => {
    setTabState(t);
  }, []);

  const filteredSources = useMemo(() => {
    const q = sourceSearch.trim().toLowerCase();
    if (!q) return sources;
    return sources.filter((s) => s.source.toLowerCase().includes(q));
  }, [sources, sourceSearch]);

  /** 「全部数据源」不展示与上方「预设模板」同标识的库内占位行 */
  const sourcesForBoard = useMemo(
    () => filteredSources.filter((s) => !PRESET_TEMPLATE_SOURCE_SLUGS.has(s.source)),
    [filteredSources],
  );

  async function requestMe(): Promise<Me | null> {
    try {
      const m = await adminApi.me();
      setMe(m);
      if (typeof m.password_min_length === "number") {
        setSettings((p) => ({ ...p, password_min_length: m.password_min_length }));
      }
      setErr("");
      return m;
    } catch {
      setMe(null);
      return null;
    }
  }

  async function loadAdminData() {
    if (!isAuthed) return;
    const shared = await Promise.allSettled([
      adminApi.overview(),
      adminApi.health(),
      canManageSettings ? adminApi.dbInfo() : Promise.resolve(null),
    ]);
    if (shared[0].status === "fulfilled") setOverview(shared[0].value);
    if (shared[1].status === "fulfilled") setHealth(shared[1].value);
    if (shared[2].status === "fulfilled") setDbInfo(shared[2].value);
    if (!canManageSettings) setDbInfo(null);

    if (tab === "sources") {
      const src = await adminApi.sources("");
      setSources(src.items);
    } else if (tab === "settings" && canManageSettings) {
      const u = await adminApi.users("", "");
      setUsers(u.items);
    }
  }

  useEffect(() => {
    const u = new URL(window.location.href);
    if (u.searchParams.has("tab")) {
      u.searchParams.delete("tab");
      window.history.replaceState({}, "", `${u.pathname}${u.search}${u.hash}`);
    }
    requestMe();
  }, []);

  useEffect(() => {
    if (!me) return;
    if (tab === "sources" && !canOperate) {
      setErr("没有权限访问该页面：需要运营或管理员角色。");
      setTab("overview");
      return;
    }
  }, [me, tab, canManageSettings, canOperate, setTab]);

  useEffect(() => {
    loadAdminData().catch((e) => setErr(friendlyErr(e instanceof Error ? e.message : "load failed")));
  }, [isAuthed, tab, refreshSeq, canManageSettings]);

  const loadSourcePresets = useCallback(async () => {
    if (tab !== "sources" || !isAuthed || !canOperate) return;
    setSourcePresetsLoading(true);
    setSourcePresetsError("");
    setSourcePresetsOrigin(null);
    try {
      const d = await adminApi.sourcePresets();
      setSourcePresets(d.items ?? []);
      setSourcePresetsOrigin(d.origin);
    } catch (e) {
      setSourcePresets([]);
      setSourcePresetsOrigin(null);
      setSourcePresetsError(friendlyErr(e instanceof Error ? e.message : "加载失败"));
    } finally {
      setSourcePresetsLoading(false);
    }
  }, [tab, isAuthed, canOperate]);

  useEffect(() => {
    loadSourcePresets();
  }, [loadSourcePresets]);

  const fillSourceFormFromRow = useCallback((row: Source | SourcePresetRow) => {
    const scope_labels =
      row.scope_labels && row.scope_labels.length > 0
        ? [...row.scope_labels]
        : row.scope_label?.trim()
          ? [row.scope_label.trim()]
          : [""];
    setSourceForm({
      source: row.source,
      api_base: row.api_base,
      scope_labels,
      api_key: "",
      frequency: row.frequency,
      enabled: row.enabled,
      notes: row.notes || "",
    });
    queueMicrotask(() =>
      document.getElementById("admin-source-form")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  }, []);

  const openPresetInEditor = useCallback(
    (p: SourcePresetRow) => {
      const saved = sources.find((s) => s.source === p.source);
      if (saved) fillSourceFormFromRow(saved);
      else fillSourceFormFromRow(p);
    },
    [sources, fillSourceFormFromRow],
  );

  async function runSourceTest(
    payload: { source?: string; api_base?: string; api_key?: string },
    resultKey: string,
    authMode: "bearer" | "private_token",
  ) {
    setSourceTestLoading(resultKey);
    setSourceTestResult(null);
    setErr("");
    try {
      const data = await adminApi.testSource({ ...payload, auth_mode: authMode });
      setSourceTestResult({
        key: resultKey,
        ok: data.ok,
        http_status: data.http_status,
        snippet: data.snippet,
        url_tested: data.url_tested,
      });
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : String(error)));
    } finally {
      setSourceTestLoading(null);
    }
  }

  useEffect(() => {
    if (!selectedAccount) return;
    const u = users.find((x) => x.username === selectedAccount);
    if (!u) return;
    setDraftRole(u.role as "viewer" | "operator" | "admin");
    setDraftEnabled(u.enabled);
    setDraftNewPassword("");
  }, [selectedAccount]);

  useEffect(() => {
    if (!selectedAccount) return;
    if (!users.some((x) => x.username === selectedAccount)) setSelectedAccount(null);
  }, [users, selectedAccount]);


  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setLoginSubmitting(true);
    try {
      await adminApi.login(loginForm.username, loginForm.password);
      const current = await requestMe();
      if (!current) {
        setErr("登录态校验失败，请重试。");
        return;
      }
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "login failed"));
    } finally {
      setLoginSubmitting(false);
    }
  }

  async function onLogout() {
    await adminApi.logout();
    setMe(null);
    setSources([]);
    setUsers([]);
    setHealth(null);
    setDbInfo(null);
  }

  async function onSaveSource(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await adminApi.saveSource({
        source: sourceForm.source,
        enabled: sourceForm.enabled,
        frequency: sourceForm.frequency,
        api_base: sourceForm.api_base,
        api_key: sourceForm.api_key,
        notes: sourceForm.notes,
        scope_labels: sourceForm.scope_labels.map((s) => s.trim()).filter(Boolean),
      });
      setSourceForm((p) => ({ ...p, api_key: "" }));
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save failed"));
    }
  }

  async function onDeleteSourceKey(sourceKey: string, displayName?: string) {
    if (!canOperate) return;
    const label = displayName || sourceKey;
    if (!window.confirm(`确定删除数据源「${label}」（标识：${sourceKey}）？删除后不可恢复。`)) return;
    setErr("");
    try {
      await adminApi.deleteSource(sourceKey);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "delete failed"));
    }
  }

  async function onSeedDemo() {
    if (!canManageSettings) return;
    if (!window.confirm("将向数据库写入示例趋势、信号、数据源等数据，确认初始化？")) return;
    setErr("");
    try {
      await adminApi.seedDemo();
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "seed failed"));
    }
  }

  async function onClearDemo() {
    if (!canManageSettings) return;
    if (!window.confirm("确认清空测试业务数据吗？这会清空趋势、信号、数据源等。")) return;
    setErr("");
    try {
      await adminApi.clearDemo();
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "clear failed"));
    }
  }

  async function onCreateUser(e: FormEvent) {
    e.preventDefault();
    setErr("");
    const username = userForm.username.trim();
    if (username.length < 2) {
      setErr("用户名至少 2 个字符");
      return;
    }
    if (userForm.password.length < settings.password_min_length) {
      setErr(`密码至少 ${settings.password_min_length} 位（当前安全策略）`);
      return;
    }
    try {
      await adminApi.createUser({ ...userForm, username });
      setUserForm({ username: "", password: "", role: "viewer", enabled: true });
      setShowCreateModal(false);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "create user failed"));
    }
  }

  async function onSaveSelectedAccount(e: FormEvent) {
    e.preventDefault();
    if (!selectedAccount) return;
    const cur = users.find((u) => u.username === selectedAccount);
    if (!cur) return;
    setErr("");
    const payload: { role?: string; enabled?: boolean; password?: string } = {};
    if (draftRole !== cur.role) payload.role = draftRole;
    if (draftEnabled !== cur.enabled) payload.enabled = draftEnabled;
    if (draftNewPassword.trim()) {
      if (draftNewPassword.length < settings.password_min_length) {
        setErr(`新密码至少 ${settings.password_min_length} 位`);
        return;
      }
      payload.password = draftNewPassword;
    }
    if (Object.keys(payload).length === 0) {
      return;
    }
    try {
      await adminApi.updateUser(selectedAccount, payload);
      setDraftNewPassword("");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "update user failed"));
    }
  }

  async function onDeleteSelectedAccount() {
    if (!selectedAccount) return;
    const name = selectedAccount;
    if (!window.confirm(`确认删除账号「${name}」吗？此操作不可恢复。`)) return;
    setErr("");
    try {
      await adminApi.deleteUser(name);
      setSelectedAccount(null);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "delete user failed"));
    }
  }

  if (!isAuthed) {
    return (
      <main className="login-screen">
        <div className="login-brand">
          <h1>AISoul Admin</h1>
          <p>后台管理台 · 基于会话登录</p>
          <div className="muted tiny" style={{ marginTop: 10 }}>仅浏览可查数据；运营可管理数据源；管理员可管理账号。</div>
        </div>
        <form className="card grid" onSubmit={onLogin}>
          <div className="form-field">
            <label>用户名</label>
            <input value={loginForm.username} onChange={(e) => setLoginForm((p) => ({ ...p, username: e.target.value }))} placeholder="请输入用户名" autoComplete="username" />
          </div>
          <div className="form-field">
            <label>密码</label>
            <input
              value={loginForm.password}
              type="password"
              onChange={(e) => setLoginForm((p) => ({ ...p, password: e.target.value }))}
              placeholder="请输入密码"
              autoComplete="current-password"
            />
          </div>
          <button type="submit" disabled={loginSubmitting}>{loginSubmitting ? "登录中..." : "登录"}</button>
          {err ? <div className="err-text">{err}</div> : null}
        </form>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar card">
        <h2 style={{ marginTop: 0 }}>AISoul Admin</h2>
        <p className="muted tiny">
          {me?.username} · {zhRole(me?.role)}
        </p>
        <nav className="grid">
          <button
            type="button"
            className={tab === "overview" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("overview")}
          >
            总览
          </button>
          <button
            type="button"
            className={tab === "queries" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("queries")}
          >
            数据查询
          </button>
          <button
            type="button"
            className={tab === "sources" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("sources")}
            disabled={!canOperate}
            title={!canOperate ? "需要运营或管理员角色" : undefined}
          >
            数据源管理
          </button>
          <button
            type="button"
            className={tab === "settings" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("settings")}
          >
            账号管理
          </button>
        </nav>
        {!canOperate || !canManageSettings ? (
          <div className="permission-hint">
            {!canOperate ? <div>当前为仅浏览角色：无法进入数据源管理。</div> : null}
            {!canManageSettings ? (
              <div>
                管理其他账号需要<strong>管理员</strong>角色。
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="grid" style={{ marginTop: 10 }}>
          <button type="button" className="btn-ghost" onClick={onLogout}>
            退出登录
          </button>
        </div>
      </aside>

      <section className="content grid">
        {err ? (
          <div className="card toast-bar err flash-banner">
            <span className="err-text">{err}</span>
          </div>
        ) : null}

        {tab === "overview" ? (
          <>
            <section className="grid grid-3">
              <div className="stat-tile"><div className="muted tiny">数据源</div><h2>{overview.sources ?? 0}</h2></div>
              <div className="stat-tile"><div className="muted tiny">趋势数量</div><h2>{overview.trends ?? 0}</h2></div>
              <div className="stat-tile"><div className="muted tiny">信号数量</div><h2>{overview.signals ?? 0}</h2></div>
              <div className="stat-tile"><div className="muted tiny">管理员账号</div><h2>{overview.admin_users ?? 0}</h2></div>
            </section>
            <section className="card">
              <div className="row between">
                <h3>系统健康</h3>
                <span className={health?.status === "ok" ? "tag ok" : "tag"}>{health?.status ?? "unknown"}</span>
              </div>
              <div className="muted tiny">数据库: {health?.db ?? "-"}</div>
              <div className="muted tiny">更新时间: {health?.time ? new Date(health.time).toLocaleString() : "-"}</div>
            </section>
            <section className="card">
              <div className="row between">
                <h3>测试/正式数据库</h3>
                <span className={dbInfo?.mode === "prod" ? "tag" : "tag ok"}>{canManageSettings ? dbInfo?.mode ?? "unknown" : "仅管理员可见"}</span>
              </div>
              {canManageSettings ? (
                <>
                  <div className="muted tiny">current: {dbInfo?.database_url ?? "-"}</div>
                  <div className="muted tiny">test: {dbInfo?.test_url ?? "-"}</div>
                  <div className="muted tiny">prod: {dbInfo?.prod_url ?? "-"}</div>
                  <div className="muted tiny">切换方式：设置后端环境变量 `AISOU_DB_MODE=test|prod`，然后重启后端服务。</div>
                </>
              ) : (
                <div className="muted tiny">数据库环境、初始化模拟数据和清空业务数据仅对管理员开放，其他角色可查看业务概览但不展示敏感环境信息。</div>
              )}
            </section>
          </>
        ) : null}

        {tab === "queries" ? <DataQueryPanel onError={(m) => setErr(friendlyErr(m))} /> : null}

        {tab === "sources" ? (
          <section className="sources-page">
            <div className="card source-preset-hero">
              <div className="row between" style={{ flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: 0 }}>预设模板</h3>
                  <p className="muted tiny" style={{ margin: "8px 0 0" }}>
                    与后端内置站点列表同步。点击某张卡片将把标识、API Base、主题标签等填入下方表单；补全 API Key 后保存即可。已配置的标识会标为「已有」。
                    GitLab 请使用接口路径如 <code>https://gitlab.com/api/v4/version</code>，测试时授权方式选「GitLab Private Token」并粘贴 PAT；仅根路径{" "}
                    <code>/api/v4</code> 常返回 404。若本机或服务器访问 gitlab.com 超时，多为网络限制，需代理或自建 GitLab。
                  </p>
                  {sourcePresetsOrigin === "fallback" ? (
                    <p className="preset-fallback-hint" style={{ margin: "10px 0 0" }}>
                      当前后端未返回预设接口（常见于未重启的旧进程），已使用前端内置模板副本。重启或升级后端到含{" "}
                      <code>GET /api/admin/v1/sources/presets</code> 的版本后，将自动与后端保持一致。
                    </p>
                  ) : null}
                </div>
                <button type="button" className="btn-ghost" disabled={sourcePresetsLoading} onClick={() => loadSourcePresets()}>
                  刷新模板列表
                </button>
              </div>
              {sourcePresetsLoading ? <p className="muted tiny" style={{ marginTop: 12 }}>正在加载预设模板…</p> : null}
              {sourcePresetsError ? (
                <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
                  <span className="err-text">{sourcePresetsError}</span>
                  <button type="button" className="btn-ghost" onClick={() => loadSourcePresets()}>
                    重试
                  </button>
                </div>
              ) : null}
              {!sourcePresetsLoading && !sourcePresetsError && sourcePresets.length === 0 ? (
                <p className="muted tiny" style={{ marginTop: 12 }}>
                  未获取到模板条目。请确认已登录且后端提供 <code>GET /api/admin/v1/sources/presets</code>，或点击「刷新模板列表」。
                </p>
              ) : null}
              {sourcePresets.length > 0 ? (
                <div className="sources-board sources-board--presets">
                  {sourcePresets.map((p) => {
                    const exists = sources.some((s) => s.source === p.source);
                    return (
                      <article
                        key={p.source}
                        className={`source-card source-card--preset${exists ? " source-card--preset-exists" : ""}`}
                        title={p.notes}
                      >
                        <div className="source-card__head">
                          <h4 className="source-card__title">{p.label}</h4>
                          <span className={exists ? "tag ok" : "tag"}>{exists ? "已有" : "模板"}</span>
                        </div>
                        <dl className="source-card__meta">
                          <div className="source-card__meta-row">
                            <dt>标识</dt>
                            <dd style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{p.source}</dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>API Base</dt>
                            <dd className="source-card__preset-url">{p.api_base || "—"}</dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>同步频率</dt>
                            <dd>{formatSourceFrequency(p.frequency)}</dd>
                          </div>
                          {p.scope_label || (p.scope_labels && p.scope_labels.length > 0) ? (
                            <div className="source-card__meta-row">
                              <dt>主题</dt>
                              <dd>{p.scope_labels?.length ? p.scope_labels.join("；") : p.scope_label}</dd>
                            </div>
                          ) : null}
                        </dl>
                        {canOperate ? (
                          <>
                            <div className="source-card__actions row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                              <select
                                title="GitLab 使用 PRIVATE-TOKEN 头"
                                value={
                                  sourceTestAuth[`preset:${p.source}`] ??
                                  ((p.api_base || "").includes("gitlab") ? "private_token" : "bearer")
                                }
                                onChange={(e) =>
                                  setSourceTestAuth((prev) => ({
                                    ...prev,
                                    [`preset:${p.source}`]: e.target.value as "bearer" | "private_token",
                                  }))
                                }
                                style={{ minWidth: 118 }}
                              >
                                <option value="bearer">Bearer</option>
                                <option value="private_token">GitLab PAT</option>
                              </select>
                              <input
                                type="password"
                                autoComplete="off"
                                placeholder="测试用密钥（可选）"
                                value={sourceTestKeys[`preset:${p.source}`] ?? ""}
                                onChange={(e) =>
                                  setSourceTestKeys((prev) => ({ ...prev, [`preset:${p.source}`]: e.target.value }))
                                }
                                style={{ minWidth: 140, flex: "1 1 140px", maxWidth: 220 }}
                              />
                              <button
                                type="button"
                                className="btn-ghost"
                                disabled={
                                  sourceTestLoading === `preset:${p.source}` || !(p.api_base || "").trim()
                                }
                                title={!(p.api_base || "").trim() ? "模板未配置 API Base" : "对模板中的接口地址发起 GET 测试"}
                                onClick={() =>
                                  void runSourceTest(
                                    {
                                      api_base: p.api_base,
                                      api_key: sourceTestKeys[`preset:${p.source}`] ?? "",
                                    },
                                    `preset:${p.source}`,
                                    sourceTestAuth[`preset:${p.source}`] ??
                                      ((p.api_base || "").includes("gitlab") ? "private_token" : "bearer"),
                                  )
                                }
                              >
                                {sourceTestLoading === `preset:${p.source}` ? "测试中…" : "测试连接"}
                              </button>
                              <button type="button" className="btn-ghost" onClick={() => openPresetInEditor(p)}>
                                编辑
                              </button>
                              <button
                                type="button"
                                className="btn-ghost"
                                disabled={!exists}
                                title={exists ? "从库中删除该标识" : "库内尚无此标识，无需删除"}
                                onClick={() => onDeleteSourceKey(p.source, p.label)}
                              >
                                删除
                              </button>
                            </div>
                            {sourceTestResult?.key === `preset:${p.source}` ? (
                              <div className="source-test-result" style={{ marginTop: 10 }}>
                                <div className={sourceTestResult.ok ? "tag ok" : "tag"} style={{ display: "inline-block" }}>
                                  HTTP {sourceTestResult.http_status}
                                  {sourceTestResult.ok ? " · 可达" : " · 请检查地址或密钥"}
                                </div>
                                {sourceTestResult.url_tested ? (
                                  <div className="muted tiny" style={{ marginTop: 6 }}>
                                    {sourceTestResult.url_tested}
                                  </div>
                                ) : null}
                                <pre
                                  style={{
                                    margin: "8px 0 0",
                                    fontSize: 11,
                                    maxHeight: 100,
                                    overflow: "auto",
                                    whiteSpace: "pre-wrap",
                                    wordBreak: "break-word",
                                  }}
                                >
                                  {sourceTestResult.snippet || "—"}
                                </pre>
                              </div>
                            ) : null}
                          </>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : null}
            </div>

            {sources.length > 0 ? (
              <>
                <div className="card compact row between" style={{ flexWrap: "wrap", gap: 12, alignItems: "center", marginTop: 16 }}>
                  <div>
                    <h3 style={{ margin: 0 }}>全部数据源</h3>
                    <p className="muted tiny" style={{ margin: "6px 0 0" }}>
                      共 {sourcesForBoard.length} 条可管理项（与「预设模板」同标识的占位行不在此列出）；可本地筛选标识。
                    </p>
                  </div>
                  <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                    <input
                      placeholder="筛选标识（本地）"
                      value={sourceSearch}
                      onChange={(e) => setSourceSearch(e.target.value)}
                    />
                  </div>
                </div>
                {sourcesForBoard.length > 0 ? (
                  <div className="sources-board">
                    {sourcesForBoard.map((s) => (
                      <article key={s.source} className="source-card">
                        <div className="source-card__head">
                          <h4 className="source-card__title">{s.source}</h4>
                          <span className={s.enabled ? "tag ok" : "tag"}>{s.enabled ? "已启用" : "已停用"}</span>
                        </div>
                        <dl className="source-card__meta">
                          <div className="source-card__meta-row">
                            <dt>同步频率</dt>
                            <dd>{formatSourceFrequency(s.frequency)}</dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>接口地址</dt>
                            <dd>{s.api_base || "—"}</dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>领域主题</dt>
                            <dd>
                              {s.scope_labels && s.scope_labels.length > 0
                                ? s.scope_labels.join("；")
                                : s.scope_label?.trim()
                                  ? s.scope_label
                                  : "—"}
                            </dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>密钥掩码</dt>
                            <dd style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{s.api_key_masked || "—"}</dd>
                          </div>
                          <div className="source-card__meta-row">
                            <dt>备注</dt>
                            <dd>{s.notes?.trim() ? s.notes : "—"}</dd>
                          </div>
                        </dl>
                        {canOperate ? (
                          <>
                            <div className="source-card__actions row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                              <select
                                title="GitLab 使用 PRIVATE-TOKEN 头"
                                value={
                                  sourceTestAuth[`saved:${s.source}`] ??
                                  ((s.api_base || "").includes("gitlab") ? "private_token" : "bearer")
                                }
                                onChange={(e) =>
                                  setSourceTestAuth((prev) => ({
                                    ...prev,
                                    [`saved:${s.source}`]: e.target.value as "bearer" | "private_token",
                                  }))
                                }
                                style={{ minWidth: 118 }}
                              >
                                <option value="bearer">Bearer</option>
                                <option value="private_token">GitLab PAT</option>
                              </select>
                              <input
                                type="password"
                                autoComplete="off"
                                placeholder="测试用密钥（可选）"
                                value={sourceTestKeys[`saved:${s.source}`] ?? ""}
                                onChange={(e) =>
                                  setSourceTestKeys((prev) => ({ ...prev, [`saved:${s.source}`]: e.target.value }))
                                }
                                style={{ minWidth: 140, flex: "1 1 140px", maxWidth: 220 }}
                              />
                              <button
                                type="button"
                                className="btn-ghost"
                                disabled={sourceTestLoading === `saved:${s.source}` || !(s.api_base || "").trim()}
                                title={!(s.api_base || "").trim() ? "请先填写接口地址" : "对已保存的接口地址发起 GET"}
                                onClick={() =>
                                  void runSourceTest(
                                    {
                                      source: s.source,
                                      api_key: sourceTestKeys[`saved:${s.source}`] ?? "",
                                    },
                                    `saved:${s.source}`,
                                    sourceTestAuth[`saved:${s.source}`] ??
                                      ((s.api_base || "").includes("gitlab") ? "private_token" : "bearer"),
                                  )
                                }
                              >
                                {sourceTestLoading === `saved:${s.source}` ? "测试中…" : "测试连接"}
                              </button>
                              <button type="button" className="btn-ghost" onClick={() => fillSourceFormFromRow(s)}>
                                编辑
                              </button>
                              <button type="button" className="btn-ghost" onClick={() => onDeleteSourceKey(s.source, s.source)}>
                                删除
                              </button>
                            </div>
                            {sourceTestResult?.key === `saved:${s.source}` ? (
                              <div className="source-test-result" style={{ marginTop: 10 }}>
                                <div className={sourceTestResult.ok ? "tag ok" : "tag"} style={{ display: "inline-block" }}>
                                  HTTP {sourceTestResult.http_status}
                                  {sourceTestResult.ok ? " · 可达" : " · 请检查地址或密钥"}
                                </div>
                                {sourceTestResult.url_tested ? (
                                  <div className="muted tiny" style={{ marginTop: 6 }}>
                                    {sourceTestResult.url_tested}
                                  </div>
                                ) : null}
                                <pre
                                  style={{
                                    margin: "8px 0 0",
                                    fontSize: 11,
                                    maxHeight: 100,
                                    overflow: "auto",
                                    whiteSpace: "pre-wrap",
                                    wordBreak: "break-word",
                                  }}
                                >
                                  {sourceTestResult.snippet || "—"}
                                </pre>
                              </div>
                            ) : null}
                          </>
                        ) : null}
                      </article>
                    ))}
                  </div>
                ) : filteredSources.length > 0 ? (
                  <p className="muted tiny">
                    当前结果均为与预设模板同标识的占位，已不在此列表展示；请调整筛选或添加其它标识的数据源。
                  </p>
                ) : (
                  <p className="muted tiny">无匹配项，请清空筛选关键词。</p>
                )}
              </>
            ) : null}

            <div className="source-card-wrap" style={{ marginTop: 16 }}>
              <article id="admin-source-form" className="source-card source-card--form">
                <div className="source-card__head">
                  <h4 className="source-card__title">{sources.length === 0 ? "新增数据源" : "添加或更新数据源"}</h4>
                  <span className="tag">表单</span>
                </div>
                <p className="muted tiny" style={{ margin: 0 }}>
                  填写标识与接口信息保存即可；标识与已有 source 相同时为更新。也可在上方「预设模板」或「全部数据源」卡片上点击「编辑」载入表单。
                </p>
                <form className="source-card__form" onSubmit={onSaveSource}>
                  <div className="form-field">
                    <label>数据源标识</label>
                    <input
                      value={sourceForm.source}
                      onChange={(e) => setSourceForm((p) => ({ ...p, source: e.target.value }))}
                      placeholder="如 github"
                      required
                      autoComplete="off"
                    />
                  </div>
                  <div className="form-field">
                    <label>接口地址（API Base）</label>
                    <input
                      value={sourceForm.api_base}
                      onChange={(e) => setSourceForm((p) => ({ ...p, api_base: e.target.value }))}
                      placeholder="https://…"
                    />
                  </div>
                  <div className="form-field">
                    <label>领域主题（可多条）</label>
                    <p className="muted tiny" style={{ margin: "0 0 8px" }}>
                      每条一行一个主题；可用「大类｜细分」写在同一行，系统会合并为单一主题归类，避免行业/板块无限分叉。同一数据源需多主题时添加多行即可。
                    </p>
                    {sourceForm.scope_labels.map((line, idx) => (
                      <div key={idx} className="row" style={{ gap: 8, marginBottom: 8, alignItems: "center" }}>
                        <input
                          style={{ flex: 1 }}
                          value={line}
                          onChange={(e) => {
                            const v = e.target.value;
                            setSourceForm((p) => {
                              const next = [...p.scope_labels];
                              next[idx] = v;
                              return { ...p, scope_labels: next };
                            });
                          }}
                          placeholder="如：AI｜大模型、财经·行情、通用·社区"
                        />
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={sourceForm.scope_labels.length <= 1}
                          onClick={() =>
                            setSourceForm((p) => ({
                              ...p,
                              scope_labels: p.scope_labels.filter((_, i) => i !== idx),
                            }))
                          }
                        >
                          删除
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => setSourceForm((p) => ({ ...p, scope_labels: [...p.scope_labels, ""] }))}
                    >
                      添加一条主题
                    </button>
                  </div>
                  <div className="form-field">
                    <label>API Key</label>
                    <input
                      value={sourceForm.api_key}
                      onChange={(e) => setSourceForm((p) => ({ ...p, api_key: e.target.value }))}
                      placeholder="明文仅本次提交；留空则不更新已有密钥"
                      type="password"
                      autoComplete="new-password"
                    />
                  </div>
                  <div className="form-field">
                    <label>同步频率</label>
                    <select value={sourceForm.frequency} onChange={(e) => setSourceForm((p) => ({ ...p, frequency: e.target.value }))}>
                      <option value="hourly">每小时同步</option>
                      <option value="daily_07:00">每日 07:00 同步</option>
                      <option value="daily">每天同步（未指定时刻）</option>
                      <option value="weekly">每周同步</option>
                    </select>
                  </div>
                  <label className="check-row">
                    <input type="checkbox" checked={sourceForm.enabled} onChange={(e) => setSourceForm((p) => ({ ...p, enabled: e.target.checked }))} />
                    创建或更新后启用该数据源
                  </label>
                  <div className="form-field">
                    <label>备注</label>
                    <textarea value={sourceForm.notes} onChange={(e) => setSourceForm((p) => ({ ...p, notes: e.target.value }))} placeholder="可选" rows={2} />
                  </div>
                  <div className="row" style={{ marginTop: 4, flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                    <button type="submit">保存</button>
                    {canOperate ? (
                      <>
                        <select
                          value={formTestAuth}
                          onChange={(e) => setFormTestAuth(e.target.value as "bearer" | "private_token")}
                          style={{ minWidth: 118 }}
                          title="与下方测试按钮配合；GitLab 选 PAT"
                        >
                          <option value="bearer">Bearer</option>
                          <option value="private_token">GitLab PAT</option>
                        </select>
                        <button
                          type="button"
                          className="btn-ghost"
                          disabled={sourceTestLoading === "form:draft" || !sourceForm.api_base.trim()}
                          onClick={() =>
                            void runSourceTest(
                              {
                                api_base: sourceForm.api_base.trim(),
                                api_key: sourceForm.api_key,
                              },
                              "form:draft",
                              formTestAuth,
                            )
                          }
                        >
                          {sourceTestLoading === "form:draft" ? "测试中…" : "测试当前接口"}
                        </button>
                      </>
                    ) : null}
                  </div>
                  {sourceTestResult?.key === "form:draft" ? (
                    <div className="source-test-result" style={{ marginTop: 12 }}>
                      <div className={sourceTestResult.ok ? "tag ok" : "tag"} style={{ display: "inline-block" }}>
                        HTTP {sourceTestResult.http_status}
                        {sourceTestResult.ok ? " · 可达" : " · 请检查地址或密钥"}
                      </div>
                      {sourceTestResult.url_tested ? (
                        <div className="muted tiny" style={{ marginTop: 6 }}>
                          {sourceTestResult.url_tested}
                        </div>
                      ) : null}
                      <pre
                        style={{
                          margin: "8px 0 0",
                          fontSize: 11,
                          maxHeight: 120,
                          overflow: "auto",
                          whiteSpace: "pre-wrap",
                          wordBreak: "break-word",
                        }}
                      >
                        {sourceTestResult.snippet || "—"}
                      </pre>
                    </div>
                  ) : null}
                </form>
              </article>
            </div>
          </section>
        ) : null}

        {tab === "settings" ? (
          <section className="settings-stack">
            {!canManageSettings ? (
              <div className="card settings-panel">
                <p className="muted tiny" style={{ margin: 0 }}>
                  管理账号需要<strong>管理员</strong>登录。
                </p>
              </div>
            ) : null}

            {canManageSettings ? (
              <>
                <div className="card settings-panel">
                  <div className="row between" style={{ flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                    <h3 className="settings-title" style={{ margin: 0, border: "none", padding: 0 }}>
                      账号管理
                    </h3>
                    <button type="button" onClick={() => setShowCreateModal(true)}>
                      新建账号
                    </button>
                  </div>
                  <p className="muted tiny" style={{ marginTop: 8 }}>
                    须先选择账号后才能保存修改、删除或为其重置密码。
                  </p>
                  <div className="form-field" style={{ marginTop: 12 }}>
                    <label>选择账号</label>
                    <select
                      value={selectedAccount ?? ""}
                      onChange={(e) => setSelectedAccount(e.target.value || null)}
                    >
                      <option value="">— 请选择 —</option>
                      {users.map((u) => (
                        <option key={u.username} value={u.username}>
                          {u.username}（{zhRole(u.role)}）
                        </option>
                      ))}
                    </select>
                  </div>

                  <fieldset
                    disabled={!selectedAccount}
                    style={{ border: "none", margin: 0, padding: 0, marginTop: 16, minWidth: 0 }}
                  >
                    {!selectedAccount ? (
                      <p className="muted tiny" style={{ margin: 0 }}>
                        共 {users.length} 个账号；请从上方选择一条后再操作。
                      </p>
                    ) : (() => {
                      const cur = users.find((u) => u.username === selectedAccount);
                      if (!cur) {
                        return <p className="muted tiny">所选账号不存在或已移除，请重新选择。</p>;
                      }
                      return (
                        <form className="create-user-form" onSubmit={onSaveSelectedAccount}>
                          <div className="user-detail-readonly muted tiny" style={{ marginBottom: 8 }}>
                            <div>
                              登录名：<strong style={{ color: "#f8fafc" }}>{cur.username}</strong>
                            </div>
                            <div style={{ marginTop: 4 }}>
                              失败次数：{cur.failed_attempts}
                              {cur.locked_until ? (
                                <span className="err-text"> · 锁定至 {new Date(cur.locked_until).toLocaleString()}</span>
                              ) : null}
                            </div>
                            {cur.created_at ? <div style={{ marginTop: 4 }}>创建时间：{new Date(cur.created_at).toLocaleString()}</div> : null}
                            <div style={{ marginTop: 4 }}>最近更新：{new Date(cur.updated_at).toLocaleString()}</div>
                          </div>
                          <div className="form-field">
                            <label>角色</label>
                            <select value={draftRole} onChange={(e) => setDraftRole(e.target.value as "viewer" | "operator" | "admin")}>
                              <option value="viewer">仅浏览（viewer）</option>
                              <option value="operator">运营（operator）</option>
                              <option value="admin">管理员（admin）</option>
                            </select>
                          </div>
                          <label className="check-row">
                            <input type="checkbox" checked={draftEnabled} onChange={(e) => setDraftEnabled(e.target.checked)} />
                            允许登录
                          </label>
                          <div className="form-field">
                            <label>重置该账号密码（留空则不修改）</label>
                            <input
                              type="password"
                              value={draftNewPassword}
                              onChange={(e) => setDraftNewPassword(e.target.value)}
                              placeholder={`至少 ${settings.password_min_length} 位`}
                              autoComplete="new-password"
                            />
                          </div>
                          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                            <button type="submit" disabled={!selectedAccount}>
                              保存修改
                            </button>
                            <button
                              type="button"
                              className="btn-ghost"
                              disabled={!selectedAccount || me?.username === selectedAccount}
                              title={me?.username === selectedAccount ? "不能删除当前登录账号" : undefined}
                              onClick={() => void onDeleteSelectedAccount()}
                            >
                              删除账号
                            </button>
                          </div>
                        </form>
                      );
                    })()}
                  </fieldset>
                </div>

                {showCreateModal ? (
                  <div
                    className="modal-overlay"
                    role="presentation"
                    onClick={() => {
                      setShowCreateModal(false);
                    }}
                  >
                    <div
                      className="card modal-dialog"
                      role="dialog"
                      aria-modal="true"
                      aria-labelledby="modal-create-user-title"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <h3 id="modal-create-user-title" className="settings-title">
                        新建账号
                      </h3>
                      <p className="muted tiny" style={{ marginTop: 0 }}>
                        初始密码须 ≥ <strong>{settings.password_min_length}</strong> 位。
                      </p>
                      <form
                        className="create-user-form"
                        onSubmit={(e) => {
                          void onCreateUser(e);
                        }}
                      >
                        <div className="form-field">
                          <label>登录名</label>
                          <input
                            value={userForm.username}
                            onChange={(e) => setUserForm((p) => ({ ...p, username: e.target.value }))}
                            placeholder="例如 operator1"
                            required
                            autoComplete="off"
                          />
                        </div>
                        <div className="form-field">
                          <label>初始密码</label>
                          <input
                            value={userForm.password}
                            type="password"
                            onChange={(e) => setUserForm((p) => ({ ...p, password: e.target.value }))}
                            placeholder={`至少 ${settings.password_min_length} 位`}
                            required
                            autoComplete="new-password"
                          />
                        </div>
                        <div className="form-field">
                          <label>角色</label>
                          <select value={userForm.role} onChange={(e) => setUserForm((p) => ({ ...p, role: e.target.value }))}>
                            <option value="viewer">仅浏览</option>
                            <option value="operator">运营</option>
                            <option value="admin">管理员</option>
                          </select>
                        </div>
                        <label className="check-row">
                          <input type="checkbox" checked={userForm.enabled} onChange={(e) => setUserForm((p) => ({ ...p, enabled: e.target.checked }))} />
                          创建后允许登录
                        </label>
                        <div className="row" style={{ marginTop: 8, gap: 8 }}>
                          <button type="submit">创建</button>
                          <button type="button" className="btn-ghost" onClick={() => setShowCreateModal(false)}>
                            取消
                          </button>
                        </div>
                      </form>
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}
          </section>
        ) : null}
      </section>
    </main>
  );
}
