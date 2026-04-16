import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { adminApi } from "./api";

function zhRole(role: string | undefined) {
  if (!role) return "—";
  if (role === "admin") return "管理员";
  if (role === "operator") return "运营";
  if (role === "viewer") return "仅浏览";
  return role;
}

function friendlyErr(msg: string): string {
  const m = msg.trim();
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
  if (/invalid credentials|incorrect password|401/i.test(m)) return "用户名或密码错误。";
  if (m.includes("old password incorrect")) return "旧密码不正确。";
  return msg;
}

type Me = { username: string; role: string; expires_at: string; password_min_length: number };
type Source = { source: string; enabled: boolean; frequency: string; api_base: string; api_key_masked: string; notes: string };
type Removal = {
  ticket_id: string;
  status: string;
  request_type: string;
  target_signal_id: string;
  reason: string;
  requester_contact: string;
  submitted_at: string;
};
type PlanItem = { key: string; title: string; description: string; status: "ready" | "planned" };
type AuditLog = { actor: string; action: string; target: string; detail: string; request_id: string; created_at: string };
type AdminUser = { username: string; role: string; enabled: boolean; failed_attempts: number; locked_until: string | null; updated_at: string };
type TrendRow = { trend_key: string; lifecycle_stage: string; trend_score: number; confidence: number; sample_size: number; updated_at: string };
type SignalRow = { signal_id: string; trend_key: string; source: string; status: string; evidence_score: number; created_at: string };
type Health = { status: string; db: string; time: string; metrics: Record<string, number> };
type Settings = { password_min_length: number; lock_minutes: number; max_failed_attempts: number };
type DbInfo = { mode: string; database_url: string; test_url: string; prod_url: string };
type TabKey = "overview" | "queries" | "sources" | "tickets" | "audit" | "settings";

const VALID_TABS: TabKey[] = ["overview", "queries", "sources", "tickets", "audit", "settings"];

function readTabFromUrl(): TabKey {
  const q = new URLSearchParams(window.location.search).get("tab");
  if (q && (VALID_TABS as string[]).includes(q)) return q as TabKey;
  return "overview";
}

function maskDbUrl(url?: string): string {
  if (!url) return "-";
  try {
    const u = new URL(url);
    if (u.password) u.password = "****";
    if (u.username) u.username = "***";
    return u.toString();
  } catch {
    return "***";
  }
}

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [loginSubmitting, setLoginSubmitting] = useState(false);
  const [tab, setTabState] = useState<TabKey>(readTabFromUrl);
  const [refreshSeq, setRefreshSeq] = useState(0);

  const [sources, setSources] = useState<Source[]>([]);
  const [tickets, setTickets] = useState<Removal[]>([]);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [overview, setOverview] = useState<Record<string, number>>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [dbInfo, setDbInfo] = useState<DbInfo | null>(null);
  const [settings, setSettings] = useState<Settings>({ password_min_length: 10, lock_minutes: 15, max_failed_attempts: 5 });
  const [trendRows, setTrendRows] = useState<TrendRow[]>([]);
  const [signalRows, setSignalRows] = useState<SignalRow[]>([]);

  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [sourceForm, setSourceForm] = useState({ source: "", enabled: true, frequency: "daily", api_base: "", api_key: "", notes: "" });
  const [userForm, setUserForm] = useState({ username: "", password: "", role: "viewer", enabled: true });
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "" });
  const [resetPasswordFor, setResetPasswordFor] = useState<{ username: string; password: string } | null>(null);

  const [sourceFilter, setSourceFilter] = useState("");
  const [ticketFilter, setTicketFilter] = useState({ status: "", keyword: "" });
  const [userFilter, setUserFilter] = useState({ role: "", keyword: "" });
  const [trendFilter, setTrendFilter] = useState({ keyword: "", lifecycle: "" });
  const [signalFilter, setSignalFilter] = useState({ keyword: "", source: "", status: "" });

  const isAuthed = useMemo(() => !!me, [me]);
  const canManageSettings = me?.role === "admin";
  const canOperate = me?.role === "admin" || me?.role === "operator";

  const setTab = useCallback((t: TabKey) => {
    setTabState(t);
    const u = new URL(window.location.href);
    u.searchParams.set("tab", t);
    window.history.replaceState({}, "", `${u.pathname}${u.search}${u.hash}`);
  }, []);

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
    setLoading(true);
    try {
      const shared = await Promise.allSettled([adminApi.overview(), adminApi.pagesPlan(), adminApi.health(), canManageSettings ? adminApi.dbInfo() : Promise.resolve(null)]);
      if (shared[0].status === "fulfilled") setOverview(shared[0].value);
      if (shared[1].status === "fulfilled") setPlanItems(shared[1].value.items);
      if (shared[2].status === "fulfilled") setHealth(shared[2].value);
      if (shared[3].status === "fulfilled") setDbInfo(shared[3].value);
      if (!canManageSettings) setDbInfo(null);

      if (tab === "sources") {
        const src = await adminApi.sources(sourceFilter);
        setSources(src.items);
      } else if (tab === "tickets") {
        const tk = await adminApi.tickets(ticketFilter.status, ticketFilter.keyword);
        setTickets(tk.items);
      } else if (tab === "audit") {
        const au = await adminApi.audits();
        setAuditLogs(au.items);
      } else if (tab === "queries") {
        const [tr, sg] = await Promise.all([
          adminApi.queryTrends(trendFilter.keyword, trendFilter.lifecycle),
          adminApi.querySignals(signalFilter.keyword, signalFilter.source, signalFilter.status),
        ]);
        setTrendRows(tr.items);
        setSignalRows(sg.items);
      } else if (tab === "settings" && canManageSettings) {
        const results = await Promise.allSettled([adminApi.users(userFilter.role, userFilter.keyword), adminApi.getSettings()]);
        if (results[0].status === "fulfilled") setUsers(results[0].value.items);
        if (results[1].status === "fulfilled") setSettings(results[1].value);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    requestMe();
  }, []);

  useEffect(() => {
    if (!me) return;
    if ((tab === "sources" || tab === "tickets") && !canOperate) {
      setErr("没有权限访问该页面：需要运营或管理员角色。");
      setTab("overview");
      return;
    }
    if (tab === "settings" && !canManageSettings) {
      setErr("没有权限访问该页面：需要管理员角色。");
      setTab("overview");
    }
  }, [me, tab, canManageSettings, canOperate, setTab]);

  useEffect(() => {
    loadAdminData().catch((e) => setErr(friendlyErr(e instanceof Error ? e.message : "load failed")));
  }, [isAuthed, tab, refreshSeq, canManageSettings]);

  useEffect(() => {
    if (me?.role !== "admin") return;
    adminApi.getSettings().then(setSettings).catch(() => {});
  }, [me?.role, me?.username]);

  function applyFilters() {
    setRefreshSeq((v) => v + 1);
  }

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    setLoginSubmitting(true);
    try {
      await adminApi.login(loginForm.username, loginForm.password);
      const current = await requestMe();
      if (!current) {
        setErr("登录态校验失败，请重试。");
        return;
      }
      setMsg(`登录成功，当前角色：${zhRole(current.role)}`);
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
    setTickets([]);
    setPlanItems([]);
    setAuditLogs([]);
    setUsers([]);
    setHealth(null);
    setDbInfo(null);
  }

  async function onSaveSource(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    try {
      await adminApi.saveSource(sourceForm);
      setMsg("数据源已保存");
      setSourceForm((p) => ({ ...p, api_key: "" }));
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save failed"));
    }
  }

  async function onSeedDemo() {
    if (!canManageSettings) return;
    if (!window.confirm("将向数据库写入示例趋势、信号、工单等数据，确认初始化？")) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.seedDemo();
      setMsg("示例数据初始化成功");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "seed failed"));
    }
  }

  async function onClearDemo() {
    if (!canManageSettings) return;
    if (!window.confirm("确认清空测试业务数据吗？这会清空趋势、信号、工单、数据源和审计日志。")) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.clearDemo();
      setMsg("业务数据已清空");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "clear failed"));
    }
  }

  async function onResolveTicket(ticketId: string) {
    if (!window.confirm(`确认处理工单 ${ticketId} 吗？`)) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.resolveTicket(ticketId);
      setMsg(`工单 ${ticketId} 已处理`);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "resolve failed"));
    }
  }

  async function onCreateUser(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    const username = userForm.username.trim();
    if (username.length < 2) {
      setErr("用户名至少 2 个字符");
      return;
    }
    if (userForm.password.length < settings.password_min_length) {
      setErr(`密码至少 ${settings.password_min_length} 位（当前安全策略）`);
      return;
    }
    if (userForm.role === "admin" && !window.confirm("创建管理员账号将拥有完整后台权限（含账号与安全策略），确认？")) {
      return;
    }
    try {
      await adminApi.createUser({ ...userForm, username });
      setUserForm({ username: "", password: "", role: "viewer", enabled: true });
      setMsg("账号已创建");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "create user failed"));
    }
  }

  async function onToggleUser(user: AdminUser) {
    const action = user.enabled ? "禁用" : "启用";
    if (!window.confirm(`确认${action}用户 ${user.username} 吗？`)) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.updateUser(user.username, { enabled: !user.enabled });
      setMsg(`用户 ${user.username} 状态已更新`);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "update user failed"));
    }
  }

  async function onChangeUserRole(user: AdminUser, newRole: "viewer" | "operator" | "admin") {
    if (user.role === newRole) return;
    if (
      !window.confirm(
        newRole === "admin"
          ? `将「${user.username}」设为管理员？对方将获得完整后台权限。`
          : `确认将「${user.username}」角色改为「${zhRole(newRole)}」吗？`
      )
    ) {
      return;
    }
    setErr("");
    setMsg("");
    try {
      await adminApi.updateUser(user.username, { role: newRole });
      setMsg(`用户 ${user.username} 角色已更新`);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "update role failed"));
    }
  }

  async function onResetUserPassword(username: string) {
    if (!resetPasswordFor || resetPasswordFor.username !== username || !resetPasswordFor.password) {
      setErr("请先在输入框中填写新密码");
      return;
    }
    if (resetPasswordFor.password.length < settings.password_min_length) {
      setErr(`新密码至少 ${settings.password_min_length} 位`);
      return;
    }
    if (!window.confirm(`确认重置用户 ${username} 的密码吗？`)) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.updateUser(username, { password: resetPasswordFor.password });
      setResetPasswordFor(null);
      setMsg(`用户 ${username} 密码已重置`);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "reset password failed"));
    }
  }

  async function onSaveSettings(e: FormEvent) {
    e.preventDefault();
    if (!window.confirm("确认保存全局安全策略吗？新的密码长度与锁定规则会立即生效。")) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.saveSettings(settings);
      setMsg("安全策略已保存");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save settings failed"));
    }
  }

  async function onChangeMyPassword(e: FormEvent) {
    e.preventDefault();
    setErr("");
    setMsg("");
    if (passwordForm.new_password.length < settings.password_min_length) {
      setErr(`新密码长度不能小于 ${settings.password_min_length}`);
      return;
    }
    if (passwordForm.new_password === passwordForm.old_password) {
      setErr("新密码不能和旧密码相同");
      return;
    }
    try {
      await adminApi.changePassword(passwordForm.old_password, passwordForm.new_password);
      setPasswordForm({ old_password: "", new_password: "" });
      setMsg("当前账号密码已更新");
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "change password failed"));
    }
  }

  async function onUpdateTrendOps(trendKey: string, lifecycle_stage: string) {
    if (!window.confirm(`确认将趋势 ${trendKey} 更新为 ${lifecycle_stage} 吗？`)) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.updateTrendOps(trendKey, { lifecycle_stage });
      setMsg(`趋势 ${trendKey} 已更新为 ${lifecycle_stage}`);
      applyFilters();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "trend update failed"));
    }
  }

  async function onUpdateSignalOps(signalId: string, status: string) {
    if (!window.confirm(`确认将信号 ${signalId} 更新为 ${status} 吗？`)) return;
    setErr("");
    setMsg("");
    try {
      await adminApi.updateSignalOps(signalId, { status });
      setMsg(`信号 ${signalId} 状态已更新为 ${status}`);
      applyFilters();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "signal update failed"));
    }
  }

  if (!isAuthed) {
    return (
      <main className="login-screen">
        <div className="login-brand">
          <h1>AISoul Admin</h1>
          <p>后台管理台 · 基于会话登录</p>
          <div className="muted tiny" style={{ marginTop: 10 }}>仅浏览可查数据，运营可处理业务，管理员可管理账号与安全策略。</div>
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
          <button className={tab === "overview" ? "tab tab-active" : "tab"} onClick={() => setTab("overview")}>
            总览
          </button>
          <button className={tab === "queries" ? "tab tab-active" : "tab"} onClick={() => setTab("queries")}>
            数据查询
          </button>
          <button
            type="button"
            className={tab === "sources" ? "tab tab-active" : "tab"}
            onClick={() => setTab("sources")}
            disabled={!canOperate}
            title={!canOperate ? "需要运营或管理员角色" : undefined}
          >
            数据源管理
          </button>
          <button
            type="button"
            className={tab === "tickets" ? "tab tab-active" : "tab"}
            onClick={() => setTab("tickets")}
            disabled={!canOperate}
            title={!canOperate ? "需要运营或管理员角色" : undefined}
          >
            合规工单
          </button>
          <button className={tab === "audit" ? "tab tab-active" : "tab"} onClick={() => setTab("audit")}>
            审计日志
          </button>
          <button
            type="button"
            className={tab === "settings" ? "tab tab-active" : "tab"}
            onClick={() => setTab("settings")}
            disabled={!canManageSettings}
            title={canManageSettings ? undefined : "需要管理员角色"}
          >
            账号与安全
          </button>
        </nav>
        {!canOperate || !canManageSettings ? (
          <div className="permission-hint">
            {!canOperate ? <div>当前为仅浏览角色: 无法进入数据源管理和合规工单。</div> : null}
            {!canManageSettings ? <div>只有管理员可以进入账号与安全、初始化或清空业务数据。</div> : null}
          </div>
        ) : null}
        <div className="grid" style={{ marginTop: 10 }}>
          <button type="button" className="btn-ghost" onClick={onLogout}>退出登录</button>
        </div>
        <div className="card compact" style={{ marginTop: 12 }}>
          <h3 className="settings-title" style={{ margin: 0, fontSize: "0.95rem", borderBottom: "none", paddingBottom: 0 }}>
            修改我的密码
          </h3>
          <p className="muted tiny" style={{ marginTop: 0 }}>
            至少 {settings.password_min_length} 位（与服务器安全策略一致）。
          </p>
          <form className="grid tight" onSubmit={onChangeMyPassword}>
            <input
              type="password"
              placeholder="当前密码"
              value={passwordForm.old_password}
              onChange={(e) => setPasswordForm((p) => ({ ...p, old_password: e.target.value }))}
              autoComplete="current-password"
            />
            <input
              type="password"
              placeholder={`新密码（≥${settings.password_min_length} 位）`}
              value={passwordForm.new_password}
              onChange={(e) => setPasswordForm((p) => ({ ...p, new_password: e.target.value }))}
              autoComplete="new-password"
            />
            <button type="submit">更新密码</button>
          </form>
        </div>
      </aside>

      <section className="content grid">
        <header className="card page-header">
          <div className="row between">
            <div>
              <h1 style={{ margin: 0 }}>后台管理中心</h1>
              <p className="muted tiny">按任务处理数据、工单和账号安全</p>
            </div>
            {loading ? <span className="tag">加载中</span> : <span className="tag ok">已同步</span>}
          </div>
        </header>

        {msg ? (
          <div className="card toast-bar flash-banner">
            <span className="ok-text">{msg}</span>
          </div>
        ) : null}
        {err ? (
          <div className="card toast-bar err flash-banner">
            <span className="err-text">{err}</span>
          </div>
        ) : null}

        {tab === "overview" ? (
          <>
            <section className="grid grid-3">
              <div className="stat-tile"><div className="muted tiny">数据源</div><h2>{overview.sources ?? 0}</h2></div>
              <div className="stat-tile"><div className="muted tiny">工单总量</div><h2>{overview.tickets ?? 0}</h2></div>
              <div className="stat-tile"><div className="muted tiny">待处理工单</div><h2>{overview.pending_tickets ?? 0}</h2></div>
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
            <section className="card">
              <h3>后台模块清单（应纳入后台）</h3>
              <div className="grid">
                {planItems.map((item) => (
                  <div key={item.key} className="card compact">
                    <div className="row between">
                      <strong>{item.title}</strong>
                      <span className={item.status === "ready" ? "tag ok" : "tag"}>{item.status}</span>
                    </div>
                    <div className="muted">{item.description}</div>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}

        {tab === "queries" ? (
          <section className="grid grid-2">
            <div className="card">
              <h3>趋势数据查询</h3>
              <div className="row">
                <input placeholder="关键词" value={trendFilter.keyword} onChange={(e) => setTrendFilter((p) => ({ ...p, keyword: e.target.value }))} />
                <select value={trendFilter.lifecycle} onChange={(e) => setTrendFilter((p) => ({ ...p, lifecycle: e.target.value }))}>
                  <option value="">全部生命周期</option>
                  <option value="growth">增长（growth）</option>
                  <option value="emerging">新兴（emerging）</option>
                  <option value="declining">衰退（declining）</option>
                </select>
                <button type="button" onClick={applyFilters}>查询</button>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {trendRows.length === 0 ? <div className="card compact muted">未找到匹配趋势</div> : null}
                {trendRows.map((t) => (
                  <div key={t.trend_key} className="card compact">
                    <div className="row between"><strong>{t.trend_key}</strong><span className="tag">{t.lifecycle_stage}</span></div>
                    <div className="muted tiny">score {t.trend_score} / confidence {t.confidence} / sample {t.sample_size}</div>
                    {canOperate ? (
                      <div className="row" style={{ marginTop: 8 }}>
                        <button type="button" onClick={() => onUpdateTrendOps(t.trend_key, "growth")}>设为 growth</button>
                        <button type="button" onClick={() => onUpdateTrendOps(t.trend_key, "emerging")}>设为 emerging</button>
                        <button type="button" onClick={() => onUpdateTrendOps(t.trend_key, "declining")}>设为 declining</button>
                      </div>
                    ) : (
                      <div className="muted tiny" style={{ marginTop: 8 }}>仅浏览角色不可修改趋势</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <h3>信号数据查询</h3>
              <div className="grid">
                <input placeholder="关键词 signal_id/trend_key" value={signalFilter.keyword} onChange={(e) => setSignalFilter((p) => ({ ...p, keyword: e.target.value }))} />
                <div className="row">
                  <input placeholder="数据源（如 github）" value={signalFilter.source} onChange={(e) => setSignalFilter((p) => ({ ...p, source: e.target.value }))} />
                  <select value={signalFilter.status} onChange={(e) => setSignalFilter((p) => ({ ...p, status: e.target.value }))}>
                    <option value="">全部状态</option>
                    <option value="active">生效中（active）</option>
                    <option value="archived">已归档（archived）</option>
                  </select>
                  <button type="button" onClick={applyFilters}>查询</button>
                </div>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {signalRows.length === 0 ? <div className="card compact muted">未找到匹配信号</div> : null}
                {signalRows.map((s) => (
                  <div key={s.signal_id} className="card compact">
                    <div className="row between"><strong>{s.signal_id}</strong><span className="tag">{s.status}</span></div>
                    <div className="muted tiny">{s.trend_key} · {s.source} · score {s.evidence_score}</div>
                    {canOperate ? (
                      <div className="row" style={{ marginTop: 8 }}>
                        <button type="button" onClick={() => onUpdateSignalOps(s.signal_id, "active")}>设为 active</button>
                        <button type="button" onClick={() => onUpdateSignalOps(s.signal_id, "archived")}>设为 archived</button>
                      </div>
                    ) : (
                      <div className="muted tiny" style={{ marginTop: 8 }}>仅浏览角色不可修改信号</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {tab === "sources" ? (
          <section className="grid grid-2">
            <div className="card">
              <h3>新增 / 更新数据源</h3>
              <form className="grid" onSubmit={onSaveSource}>
                <input value={sourceForm.source} onChange={(e) => setSourceForm((p) => ({ ...p, source: e.target.value }))} placeholder="数据源标识（如 github）" required />
                <input value={sourceForm.api_base} onChange={(e) => setSourceForm((p) => ({ ...p, api_base: e.target.value }))} placeholder="接口地址（API Base URL）" />
                <input value={sourceForm.api_key} onChange={(e) => setSourceForm((p) => ({ ...p, api_key: e.target.value }))} placeholder="API Key（明文仅本次提交）" />
                <select value={sourceForm.frequency} onChange={(e) => setSourceForm((p) => ({ ...p, frequency: e.target.value }))}>
                  <option value="hourly">每小时同步</option><option value="daily">每天同步</option><option value="weekly">每周同步</option>
                </select>
                <label className="row"><input type="checkbox" checked={sourceForm.enabled} onChange={(e) => setSourceForm((p) => ({ ...p, enabled: e.target.checked }))} />启用</label>
                <textarea value={sourceForm.notes} onChange={(e) => setSourceForm((p) => ({ ...p, notes: e.target.value }))} placeholder="备注（可选）" />
                <div className="row">
                  <button type="submit">保存</button>
                </div>
              </form>
            </div>
            <div className="card">
              <h3>当前数据源</h3>
              <div className="row">
                <input placeholder="source 关键词过滤" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} />
                <button type="button" onClick={applyFilters}>查询</button>
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                {sources.length === 0 ? <div className="card compact muted">未找到匹配数据源</div> : null}
                {sources.map((s) => (
                  <div key={s.source} className="card compact">
                    <div className="row between"><strong>{s.source}</strong><span className={s.enabled ? "tag ok" : "tag"}>{s.enabled ? "已启用" : "已停用"}</span></div>
                    <div className="muted tiny">同步频率: {s.frequency}</div>
                    <div className="muted tiny">接口地址: {s.api_base || "-"}</div>
                    <div className="muted tiny">密钥掩码: {s.api_key_masked || "-"}</div>
                    <div className="muted tiny">{s.notes || "-"}</div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        ) : null}

        {tab === "tickets" ? (
          <section className="card">
            <h3>合规工单处理</h3>
            <div className="row">
              <input placeholder="ticket_id 关键词" value={ticketFilter.keyword} onChange={(e) => setTicketFilter((p) => ({ ...p, keyword: e.target.value }))} />
              <select value={ticketFilter.status} onChange={(e) => setTicketFilter((p) => ({ ...p, status: e.target.value }))}>
                <option value="">全部状态</option>
                <option value="submitted">待处理（submitted）</option>
                <option value="executed">已处理（executed）</option>
              </select>
              <button type="button" onClick={applyFilters}>查询</button>
            </div>
            <div className="grid" style={{ marginTop: 10 }}>
              {tickets.length === 0 ? <div className="card compact muted">没有匹配的工单</div> : null}
              {tickets.map((t) => (
                <div key={t.ticket_id} className="card compact row between">
                  <div>
                    <strong>{t.ticket_id}</strong>
                    <div className="muted tiny">status: {t.status} · {t.request_type}</div>
                    <div className="muted tiny">target: {t.target_signal_id} · {new Date(t.submitted_at).toLocaleString()}</div>
                    <div className="muted tiny">{t.reason}</div>
                  </div>
                  <button onClick={() => onResolveTicket(t.ticket_id)} disabled={t.status === "executed"}>{t.status === "executed" ? "已处理" : "处理工单"}</button>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "audit" ? (
          <section className="card">
            <h3>审计日志</h3>
            <div className="grid">
              {auditLogs.length === 0 ? <div className="card compact muted">暂无审计日志</div> : null}
              {auditLogs.map((log, i) => (
                <div key={`${log.created_at}-${i}`} className="card compact">
                  <div className="row between"><strong>{log.action}</strong><span className="muted tiny">{new Date(log.created_at).toLocaleString()}</span></div>
                  <div className="muted tiny">actor: {log.actor || "-"}</div>
                  <div className="muted tiny">target: {log.target || "-"}</div>
                  <div className="muted tiny">{log.detail || "-"}</div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {tab === "settings" ? (
          <section className="settings-stack">
            <div className="card settings-panel">
              <h3 className="settings-title">筛选账号</h3>
              <p className="muted tiny" style={{ marginTop: 0 }}>
                用关键字搜用户名，或按角色缩小范围后点「查询」。
              </p>
              <div className="filter-bar">
                <div className="form-field">
                  <label>关键字</label>
                  <input
                    placeholder="用户名包含…"
                    value={userFilter.keyword}
                    onChange={(e) => setUserFilter((p) => ({ ...p, keyword: e.target.value }))}
                    onKeyDown={(e) => e.key === "Enter" && applyFilters()}
                  />
                </div>
                <div className="form-field">
                  <label>角色</label>
                  <select value={userFilter.role} onChange={(e) => setUserFilter((p) => ({ ...p, role: e.target.value }))}>
                    <option value="">全部</option>
                    <option value="viewer">仅浏览（viewer）</option>
                    <option value="operator">运营（operator）</option>
                    <option value="admin">管理员（admin）</option>
                  </select>
                </div>
                <div className="filter-actions">
                  <button type="button" onClick={applyFilters}>
                    查询
                  </button>
                </div>
              </div>
            </div>

            <div className="card settings-panel settings-panel-accent">
              <h3 className="settings-title">新建账号</h3>
              <p className="muted tiny" style={{ marginTop: 0 }}>
                仅<strong>管理员</strong>可创建。密码长度须 ≥ <strong>{settings.password_min_length}</strong> 位（受安全策略约束）。
              </p>
              <form className="create-user-form" onSubmit={onCreateUser}>
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
                  <label>角色权限</label>
                  <select value={userForm.role} onChange={(e) => setUserForm((p) => ({ ...p, role: e.target.value }))}>
                    <option value="viewer">仅浏览 — 只看数据，不能改</option>
                    <option value="operator">运营 — 管数据源、工单、趋势操作</option>
                    <option value="admin">管理员 — 含账号与安全策略</option>
                  </select>
                </div>
                <label className="check-row">
                  <input type="checkbox" checked={userForm.enabled} onChange={(e) => setUserForm((p) => ({ ...p, enabled: e.target.checked }))} />
                  创建后允许登录
                </label>
                <button type="submit">创建账号</button>
              </form>
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title">已有账号</h3>
              <div className="user-list">
                {users.length === 0 ? (
                  <div className="muted tiny">没有匹配的用户，请调整筛选或新建账号。</div>
                ) : null}
                {users.map((user) => (
                  <div key={user.username} className="user-row">
                    <div className="user-row-main">
                      <div className="user-name">{user.username}</div>
                      <div className="user-meta">
                        <span className="role-pill">{zhRole(user.role)}</span>
                        <span className={user.enabled ? "status-on" : "status-off"}>{user.enabled ? "已启用" : "已禁用"}</span>
                        {user.failed_attempts > 0 ? <span className="muted tiny">失败 {user.failed_attempts} 次</span> : null}
                        {user.locked_until ? <span className="err-text tiny">锁定至 {new Date(user.locked_until).toLocaleString()}</span> : null}
                      </div>
                    </div>
                    <div className="user-row-actions">
                      <select
                        value={user.role}
                        onChange={(e) => onChangeUserRole(user, e.target.value as "viewer" | "operator" | "admin")}
                        title="修改账号角色"
                      >
                        <option value="viewer">仅浏览</option>
                        <option value="operator">运营</option>
                        <option value="admin">管理员</option>
                      </select>
                      <button type="button" className="btn-ghost" onClick={() => onToggleUser(user)}>
                        {user.enabled ? "禁用" : "启用"}
                      </button>
                      <button type="button" onClick={() => onResetUserPassword(user.username)}>
                        重置密码
                      </button>
                    </div>
                    <div className="form-field">
                      <input
                        type="password"
                        placeholder={`为 ${user.username} 设置新密码（至少 ${settings.password_min_length} 位）`}
                        value={resetPasswordFor?.username === user.username ? resetPasswordFor.password : ""}
                        onChange={(e) => setResetPasswordFor({ username: user.username, password: e.target.value })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginBottom: "0.5rem" }}>
                全局安全策略
              </h3>
              <p className="muted tiny">影响所有管理员密码与锁定逻辑。</p>
              <form className="grid tight" onSubmit={onSaveSettings}>
                <div className="form-field">
                  <label>最小密码长度</label>
                  <input type="number" min={6} max={128} value={settings.password_min_length} onChange={(e) => setSettings((p) => ({ ...p, password_min_length: Number(e.target.value) || 10 }))} />
                </div>
                <div className="form-field">
                  <label>登录失败锁定（分钟）</label>
                  <input type="number" min={1} value={settings.lock_minutes} onChange={(e) => setSettings((p) => ({ ...p, lock_minutes: Number(e.target.value) || 15 }))} />
                </div>
                <div className="form-field">
                  <label>连续失败多少次锁定</label>
                  <input type="number" min={1} value={settings.max_failed_attempts} onChange={(e) => setSettings((p) => ({ ...p, max_failed_attempts: Number(e.target.value) || 5 }))} />
                </div>
                <button type="submit">保存策略</button>
              </form>
            </div>
          </section>
        ) : null}
      </section>
    </main>
  );
}
