import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { adminApi } from "./api";
import { DataQueryPanel } from "./DataQueryPanel";

function zhRole(role: string | undefined) {
  if (!role) return "—";
  if (role === "admin") return "管理员";
  if (role === "operator") return "运营";
  if (role === "viewer") return "仅浏览";
  return role;
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
  if (/https required/i.test(m)) return "须通过 HTTPS 访问 API；请确认 Nginx 已设置 X-Forwarded-Proto。";
  if (m.includes("account locked")) return "账号已锁定，请稍后再试或联系管理员。";
  if (/HTTP 502|bad gateway/i.test(m)) return m;
  return msg;
}

function buildDiagLogClipboardText(
  logs: Array<{
    created_at?: string | null;
    level?: string;
    step?: string;
    message?: string;
    connector_id?: number | null;
    source_key?: string | null;
  }>,
  opts?: { runId?: string; diagVersion?: string },
): string {
  const head = [
    `# AiTrends 同步诊断日志`,
    opts?.diagVersion ? `# diag_v=${opts.diagVersion}` : "",
    opts?.runId ? `# run_id=${opts.runId}` : "",
    `# lines=${logs.length}`,
    "",
  ].filter(Boolean);
  return [...head, ...logs.map((r) => formatDiagLogLine(r))].join("\n");
}

function formatDiagLogLine(r: {
  created_at?: string | null;
  level?: string;
  step?: string;
  message?: string;
  connector_id?: number | null;
  source_key?: string | null;
}): string {
  const head = `[${r.created_at ?? ""}] [${r.level}] [${r.step}]`;
  const meta =
    (r.connector_id != null ? ` #${r.connector_id}` : "") + (r.source_key ? ` ${r.source_key}` : "");
  return `${head}${meta} ${r.message ?? ""}`;
}

/** 与后端 ``FEED_APPS_KEYS`` 对齐：仅下列标识默认进前台「应用」Feed。 */
const APPS_FEED_SOURCE_KEYS = new Set(["product_hunt"]);

function publicFeedLaneForSourceKey(sourceKey: string): { lane: "apps" | "news"; title: string; detail: string } {
  const k = sourceKey.trim().toLowerCase();
  if (APPS_FEED_SOURCE_KEYS.has(k)) {
    return {
      lane: "apps",
      title: "应用",
      detail: "默认进前台「应用」列表；主类为 Agent/大模型等或正文含模型资讯信号时仍可能归为资讯。",
    };
  }
  return {
    lane: "news",
    title: "资讯",
    detail: "默认进前台「资讯」列表（与当前后端 feed 规则一致）。",
  };
}

type SourceCardDraft = {
  api_base: string;
  scope_text: string;
  api_key: string;
  app_secret: string;
  fetch_limit: number;
};

function inferSourceTestAuth(
  source: string | undefined,
  apiBase: string,
): { auth_mode: "bearer" | "private_token" | "query_key"; key_param?: string } {
  const sk = (source || "").trim().toLowerCase();
  if (sk === "newsapi") return { auth_mode: "query_key", key_param: "apiKey" };
  if (sk === "thenewsapi") return { auth_mode: "query_key", key_param: "api_token" };
  if (apiBase.toLowerCase().includes("gitlab")) return { auth_mode: "private_token" };
  return { auth_mode: "bearer" };
}

/** 将后端 ``abcd...wxyz`` 掩码改为「首尾 + 中间星号」展示。 */
function formatApiKeyDisplay(masked: string | undefined | null): string {
  const s = (masked || "").trim();
  if (!s) return "";
  const i = s.indexOf("...");
  if (i > 0 && i + 3 < s.length) {
    const head = s.slice(0, i);
    const tail = s.slice(i + 3);
    return `${head}${"*".repeat(10)}${tail}`;
  }
  return s;
}

type Me = { username: string; role: string; expires_at: string; password_min_length: number };
type ConnectorTokenStatus = {
  connector_id: number;
  name: string;
  enabled: boolean;
  has_api_key: boolean;
  has_oauth_client_secret?: boolean;
};
type Source = {
  source: string;
  enabled: boolean;
  api_base: string;
  api_key_masked: string;
  app_secret_masked?: string;
  /** 数据源表单里是否曾保存过密钥（仅掩码展示；定时同步不读此字段） */
  admin_key_configured?: boolean;
  /** 绑定到该 source 的连接器及 config_json.api_key 是否非空（同步实际用此密钥） */
  connectors_token_status?: ConnectorTokenStatus[];
  scope_label?: string;
  scope_labels?: string[];
  notes: string;
  fetch_limit?: number;
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
type TabKey = "overview" | "queries" | "sources" | "ai" | "software" | "logs" | "settings";

type SwPkgRow = {
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
};

type LlmSettingsView = {
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: string;
  has_api_key: boolean;
  pipeline: Array<{ id: string; label: string }>;
};

type SchedulerSettingsView = {
  connector_scheduler_enabled: boolean;
  connector_sync_interval_hours: number;
  last_connector_batch_at: string | null;
  gate_interval_minutes: number;
  scheduler_timezone?: string;
  daily_slot_times_local?: string;
};

type NewsletterSettingsView = import("./api").NewsletterSettingsResponse;

function newsletterFormFromView(nl: NewsletterSettingsView) {
  return {
    email_enabled: nl.send_enabled,
    feishu_enabled: nl.feishu_enabled ?? false,
    public_site_base_url: nl.public_site_base_url,
    smtp_host: nl.smtp_host,
    smtp_port: nl.smtp_port,
    smtp_user: nl.smtp_user,
    smtp_password: "",
    mail_from: nl.mail_from,
    feishu_webhook_url: "",
  };
}

type SourcePresetRow = {
  source: string;
  label: string;
  api_base: string;
  scope_label: string;
  scope_labels: string[];
  notes: string;
  enabled: boolean;
  /** 为 false 时卡片不展示 API Key 输入（公开/免 Key 模板）；缺省按 true */
  show_api_key_field?: boolean;
  /** 为 true 时另展示 OAuth Client Secret（如 Product Hunt） */
  show_app_secret_field?: boolean;
  fetch_limit?: number;
  /** 与后端预设 content_role 一致；旧后端可能无此字段 */
  content_role?: string;
  content_role_label_zh?: string;
};

function scopeTextFromSavedOrPreset(saved: Source | undefined, preset: SourcePresetRow | undefined): string {
  if (saved?.scope_labels && saved.scope_labels.length > 0) return saved.scope_labels.join("\n");
  if (preset?.scope_labels && preset.scope_labels.length > 0) return preset.scope_labels.join("\n");
  return (saved?.scope_label || preset?.scope_label || "").trim();
}

function defaultSourceCardDraft(saved: Source | undefined, preset: SourcePresetRow | undefined): SourceCardDraft {
  const fl = saved?.fetch_limit ?? preset?.fetch_limit ?? 10;
  return {
    api_base: (saved?.api_base ?? preset?.api_base ?? "").trim(),
    scope_text: scopeTextFromSavedOrPreset(saved, preset),
    api_key: "",
    app_secret: "",
    fetch_limit: fl,
  };
}

function sourceNotesForUpsert(saved: Source | undefined, preset: SourcePresetRow | undefined): string {
  return (saved?.notes ?? preset?.notes ?? "").trim();
}

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
    api_base: "",
    api_key: "",
    app_secret: "",
    scope_labels: [""] as string[],
    notes: "",
    fetch_limit: 10,
  });
  const [userForm, setUserForm] = useState({ username: "", password: "", role: "viewer", enabled: true });
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null);
  const [draftRole, setDraftRole] = useState<"viewer" | "operator" | "admin">("viewer");
  const [draftEnabled, setDraftEnabled] = useState(true);
  const [draftNewPassword, setDraftNewPassword] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  const [sourcePresets, setSourcePresets] = useState<SourcePresetRow[]>([]);
  const [sourcePresetsLoading, setSourcePresetsLoading] = useState(false);
  const [sourcePresetsError, setSourcePresetsError] = useState("");
  /** 数据源卡片草稿（需密钥的预置/自定义含 api_key；免 Key 预置不传密钥） */
  const [sourceCardDrafts, setSourceCardDrafts] = useState<Record<string, SourceCardDraft>>({});
  const [sourceCardSaving, setSourceCardSaving] = useState<string | null>(null);
  /** 数据源卡片上「启用/停用」提交中（key 为 source 标识） */
  const [sourceToggleBusy, setSourceToggleBusy] = useState<string | null>(null);
  /** Product Hunt：仅 Access Token 直连（清除 OAuth Secret，不走 client_credentials） */
  const [phTokenDirect, setPhTokenDirect] = useState(true);
  const [formTestAuth, setFormTestAuth] = useState<"bearer" | "private_token">("bearer");
  const [sourceTestLoading, setSourceTestLoading] = useState<string | null>(null);
  const [sourceTestResult, setSourceTestResult] = useState<{
    key: string;
    ok: boolean;
    http_status: number;
    snippet: string;
    url_tested?: string;
  } | null>(null);

  /** 根据当前表单「标识」与已加载的 sources，提示是否已配置密钥（掩码 + 连接器） */
  const sourceApiKeyStatusLine = useMemo(() => {
    const key = sourceForm.source.trim().toLowerCase();
    if (!key) return "";
    const s = sources.find((x) => x.source === key);
    if (!s) {
      return "该标识尚未入库：保存时若在下方填写 API Key，会写入掩码并同步到绑定连接器；留空则首次不写入密钥。";
    }
    const mask = (s.api_key_masked || "").trim();
    const rows = s.connectors_token_status ?? [];
    const connPart =
      rows.length > 0
        ? `连接器：${rows.map((c) => `${c.name}（#${c.connector_id}）${c.has_api_key ? "已填 api_key" : "未填"}`).join("；")}。`
        : "尚无绑定到该标识的连接器。";
    const maskPart = mask ? `数据源掩码（已保存过密钥）：${mask}。` : "数据源侧尚无掩码（未在保存时填过密钥，或仅连接器内有 Key）。";
    return `${maskPart}${connPart}修改密钥：在下方输入新值并保存；留空表示不改动已有密钥。`;
  }, [sources, sourceForm.source]);

  const sourceFormPreset = useMemo(
    () => sourcePresets.find((p) => p.source === sourceForm.source.trim().toLowerCase()),
    [sourcePresets, sourceForm.source],
  );
  const sourceFormShowsAppSecret = sourceFormPreset?.show_app_secret_field === true;

  const [llmSettings, setLlmSettings] = useState<LlmSettingsView | null>(null);
  const [llmForm, setLlmForm] = useState({ provider: "deepseek", base_url: "", model: "", api_key: "" });
  const [llmSaving, setLlmSaving] = useState(false);
  const [schedulerSettings, setSchedulerSettings] = useState<SchedulerSettingsView | null>(null);
  const [schedulerForm, setSchedulerForm] = useState({ enabled: true, hours: 6 });
  const [schedulerSaving, setSchedulerSaving] = useState(false);
  const [newsletterSettings, setNewsletterSettings] = useState<NewsletterSettingsView | null>(null);
  const [newsletterForm, setNewsletterForm] = useState(() =>
    newsletterFormFromView({
      send_enabled: false,
      feishu_enabled: false,
      public_site_base_url: "",
      smtp_host: "",
      smtp_port: 465,
      smtp_user: "",
      smtp_password_masked: "",
      has_smtp_password: false,
      mail_from: "",
      feishu_webhook_masked: "",
      has_feishu_webhook: false,
    } as NewsletterSettingsView),
  );
  const [newsletterSaving, setNewsletterSaving] = useState(false);
  const [digestPreview, setDigestPreview] = useState<{
    digest_date: string;
    active_subscribers: number;
    digest: { subject: string; body_md: string; status: string; sent_at: string | null; feishu_sent_at: string | null; error_message: string | null } | null;
  } | null>(null);
  const [digestRunBusy, setDigestRunBusy] = useState(false);
  const [clearIngestBusy, setClearIngestBusy] = useState(false);
  const [themeFetchBusy, setThemeFetchBusy] = useState(false);
  const [diagLogs, setDiagLogs] = useState<
    Array<{
      id: number;
      run_id: string;
      created_at: string | null;
      level: string;
      step: string;
      message: string;
      connector_id: number | null;
      source_key: string | null;
    }>
  >([]);
  const [diagRunIds, setDiagRunIds] = useState<string[]>([]);
  const [diagRunFilter, setDiagRunFilter] = useState("");
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagPipelineVersion, setDiagPipelineVersion] = useState("");
  const [diagCopyOk, setDiagCopyOk] = useState(false);
  /** 与公开接口同源：便于核对后台看到的后端是否为当前部署 */
  const [publicApiRelease, setPublicApiRelease] = useState<string | null>(null);

  const adminUiRelease = import.meta.env.VITE_APP_RELEASE ?? "—";

  const [swPackages, setSwPackages] = useState<SwPkgRow[]>([]);
  const [swFile, setSwFile] = useState<File | null>(null);
  const [swTitle, setSwTitle] = useState("");
  const [swSummary, setSwSummary] = useState("");
  const [swPlatform, setSwPlatform] = useState<"ios" | "android">("android");
  const [swCatSlug, setSwCatSlug] = useState("general");
  const [swCatLabel, setSwCatLabel] = useState("");
  const [swBusy, setSwBusy] = useState(false);

  type RuntimeView = {
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
  };
  const [runtimeView, setRuntimeView] = useState<RuntimeView | null>(null);
  const [runtimeForm, setRuntimeForm] = useState({
    cors_origins_csv: "",
    jwt_ttl_seconds: 1800,
    allowed_skew_seconds: 300,
    require_https: true,
    allow_insecure_localhost: true,
    admin_cookie_secure: true,
    app_env: "dev",
    force_demo_seed: false,
    legacy_admin_enabled: false,
    app_release_label: "",
    hot_llm_model: "rule-based",
  });
  const [runtimeSaving, setRuntimeSaving] = useState(false);

  const isAuthed = useMemo(() => !!me, [me]);
  const canManageSettings = me?.role === "admin";
  const canOperate = me?.role === "admin" || me?.role === "operator";

  const setTab = useCallback((t: TabKey) => {
    setTabState(t);
  }, []);

  useEffect(() => {
    if (!me) return;
    let cancelled = false;
    void fetch("/api/public/v1/version")
      .then((r) => r.json())
      .then((j: { code?: number; data?: { release?: string } }) => {
        if (!cancelled && j.code === 0 && j.data?.release) setPublicApiRelease(j.data.release);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [me]);

  const presetSourceIds = useMemo(() => new Set(sourcePresets.map((p) => p.source)), [sourcePresets]);

  const customSourcesOnly = useMemo(
    () => sources.filter((s) => !presetSourceIds.has(s.source)),
    [sources, presetSourceIds],
  );

  const showSourceBoard = sourcePresets.length > 0 || customSourcesOnly.length > 0;

  function scopeLabelsPayloadFromSource(row: Source): string[] {
    if (row.scope_labels && row.scope_labels.length > 0) {
      return row.scope_labels.map((x) => x.trim()).filter(Boolean);
    }
    if (row.scope_label?.trim()) return [row.scope_label.trim()];
    return [];
  }

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
      const [u, rt] = await Promise.all([adminApi.users("", ""), adminApi.getRuntimeSettings()]);
      setUsers(u.items);
      setRuntimeView(rt);
      setRuntimeForm({
        cors_origins_csv: rt.cors_origins_csv,
        jwt_ttl_seconds: rt.jwt_ttl_seconds,
        allowed_skew_seconds: rt.allowed_skew_seconds,
        require_https: rt.require_https,
        allow_insecure_localhost: rt.allow_insecure_localhost,
        admin_cookie_secure: rt.admin_cookie_secure,
        app_env: rt.app_env,
        force_demo_seed: rt.demo_seed_enabled === true,
        legacy_admin_enabled: rt.legacy_admin_enabled,
        app_release_label: rt.app_release_label,
        hot_llm_model: rt.hot_llm_model,
      });
    } else if (tab === "ai") {
      const [llm, sched, nl] = await Promise.all([
        adminApi.getLlmSettings(),
        adminApi.getSchedulerSettings(),
        adminApi.getNewsletterSettings(),
      ]);
      setLlmSettings(llm);
      setSchedulerSettings(sched);
      setNewsletterSettings(nl);
      setNewsletterForm(newsletterFormFromView(nl));
      try {
        const dp = await adminApi.getNewsletterDigestToday();
        setDigestPreview(dp);
      } catch {
        setDigestPreview(null);
      }
      setSchedulerForm({ enabled: sched.connector_scheduler_enabled, hours: sched.connector_sync_interval_hours });
      setLlmForm((p) => ({
        ...p,
        provider: llm.provider,
        base_url: llm.base_url,
        model: llm.model,
        api_key: "",
      }));
    } else if (tab === "software") {
      const pk = await adminApi.softwarePackages(100);
      setSwPackages(pk);
    } else if (tab === "logs") {
      await loadDiagnosticLogs(diagRunFilter || undefined);
    }
  }

  async function loadDiagnosticLogs(runId?: string) {
    setDiagLoading(true);
    try {
      const d = await adminApi.syncDiagnosticLogs({ run_id: runId, limit: 800 });
      setDiagLogs(d.items ?? []);
      setDiagRunIds(d.recent_run_ids ?? []);
      setDiagPipelineVersion(d.diag_pipeline_version ?? "");
      if (runId) setDiagRunFilter(runId);
    } catch (e) {
      setErr(friendlyErr(e instanceof Error ? e.message : "load diagnostic logs failed"));
    } finally {
      setDiagLoading(false);
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
    try {
      const d = await adminApi.sourcePresets();
      setSourcePresets(d.items ?? []);
    } catch (e) {
      setSourcePresets([]);
      setSourcePresetsError(friendlyErr(e instanceof Error ? e.message : "加载失败"));
    } finally {
      setSourcePresetsLoading(false);
    }
  }, [tab, isAuthed, canOperate]);

  useEffect(() => {
    loadSourcePresets();
  }, [loadSourcePresets]);

  async function runSourceTest(
    payload: { source?: string; api_base?: string; api_key?: string },
    resultKey: string,
    auth: { auth_mode: "bearer" | "private_token" | "query_key"; key_param?: string },
  ) {
    setSourceTestLoading(resultKey);
    setSourceTestResult(null);
    setErr("");
    try {
      const data = await adminApi.testSource({ ...payload, auth_mode: auth.auth_mode, key_param: auth.key_param });
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
    setLlmSettings(null);
    setSwPackages([]);
  }

  async function onUploadSoftware(e: FormEvent) {
    e.preventDefault();
    if (!canOperate) return;
    if (!swFile) {
      setErr("请选择安装包文件");
      return;
    }
    if (!swTitle.trim()) {
      setErr("请填写应用名称");
      return;
    }
    setSwBusy(true);
    setErr("");
    try {
      const fd = new FormData();
      fd.append("file", swFile);
      fd.append("title", swTitle.trim());
      fd.append("summary", swSummary);
      fd.append("platform", swPlatform);
      fd.append("category_slug", (swCatSlug || "general").trim());
      fd.append("category_label", (swCatLabel || swCatSlug || "general").trim());
      fd.append("sort_order", "0");
      await adminApi.uploadSoftwarePackage(fd);
      setSwFile(null);
      setSwTitle("");
      setSwSummary("");
      const pk = await adminApi.softwarePackages(100);
      setSwPackages(pk);
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "upload failed"));
    } finally {
      setSwBusy(false);
    }
  }

  async function onDeleteSoftwareRow(id: number) {
    if (!canOperate) return;
    if (!window.confirm(`确定删除应用包 id=${id}？文件将从磁盘移除。`)) return;
    setErr("");
    try {
      await adminApi.deleteSoftwarePackage(id);
      setSwPackages((p) => p.filter((x) => x.id !== id));
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "delete failed"));
    }
  }

  async function onSaveLlm(e: FormEvent) {
    e.preventDefault();
    if (!canOperate) return;
    setLlmSaving(true);
    setErr("");
    try {
      const payload: { provider?: string; base_url?: string; model?: string; api_key?: string } = {
        provider: llmForm.provider.trim() || undefined,
        base_url: llmForm.base_url.trim() || undefined,
        model: llmForm.model.trim() || undefined,
      };
      if (llmForm.api_key.trim()) payload.api_key = llmForm.api_key.trim();
      const out = await adminApi.saveLlmSettings(payload);
      setLlmSettings(out);
      setLlmForm((p) => ({
        ...p,
        api_key: "",
        provider: out.provider,
        base_url: out.base_url,
        model: out.model,
      }));
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save llm failed"));
    } finally {
      setLlmSaving(false);
    }
  }

  async function onSaveScheduler(e: FormEvent) {
    e.preventDefault();
    if (!canOperate) return;
    const h = Math.min(168, Math.max(1, Math.floor(Number(schedulerForm.hours)) || 6));
    setSchedulerSaving(true);
    setErr("");
    try {
      const out = await adminApi.saveSchedulerSettings({
        connector_scheduler_enabled: schedulerForm.enabled,
        connector_sync_interval_hours: h,
      });
      setSchedulerSettings(out);
      setSchedulerForm({ enabled: out.connector_scheduler_enabled, hours: out.connector_sync_interval_hours });
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save scheduler failed"));
    } finally {
      setSchedulerSaving(false);
    }
  }

  async function onSaveNewsletter(e: FormEvent) {
    e.preventDefault();
    if (!canOperate) return;
    const emailOn = newsletterForm.email_enabled;
    const feishuOn = newsletterForm.feishu_enabled;
    if (!emailOn && !feishuOn) {
      setErr("请至少启用邮件或飞书其一。");
      return;
    }
    if (emailOn) {
      if (!newsletterForm.public_site_base_url.trim()) {
        setErr("启用邮件时请填写站点根 URL（用于退订链接）。");
        return;
      }
      if (!newsletterForm.smtp_host.trim() || !newsletterForm.smtp_user.trim() || !newsletterForm.mail_from.trim()) {
        setErr("启用邮件时请填写 SMTP 主机、用户名与发件人。");
        return;
      }
      if (!newsletterSettings?.has_smtp_password && !newsletterForm.smtp_password.trim()) {
        setErr("启用邮件时请填写 SMTP 密码。");
        return;
      }
    }
    if (feishuOn && !newsletterSettings?.has_feishu_webhook && !newsletterForm.feishu_webhook_url.trim()) {
      setErr("启用飞书时请填写 Webhook URL。");
      return;
    }
    setNewsletterSaving(true);
    setErr("");
    try {
      const anyOn = emailOn || feishuOn;
      const port = Math.min(65535, Math.max(1, Math.floor(Number(newsletterForm.smtp_port)) || 465));
      const payload: Record<string, unknown> = {
        send_enabled: emailOn,
        feishu_enabled: feishuOn,
        cron_enabled: anyOn,
        generate_enabled: anyOn,
        daily_digest_job_enabled: anyOn,
      };
      if (emailOn) {
        payload.public_site_base_url = newsletterForm.public_site_base_url.trim();
        payload.smtp_host = newsletterForm.smtp_host.trim();
        payload.smtp_port = port;
        payload.smtp_user = newsletterForm.smtp_user.trim();
        payload.mail_from = newsletterForm.mail_from.trim();
        payload.smtp_use_tls = port !== 465;
      }
      if (newsletterForm.smtp_password.trim()) payload.smtp_password = newsletterForm.smtp_password.trim();
      if (newsletterForm.feishu_webhook_url.trim()) payload.feishu_webhook_url = newsletterForm.feishu_webhook_url.trim();
      const out = await adminApi.saveNewsletterSettings(payload);
      setNewsletterSettings(out);
      setNewsletterForm(newsletterFormFromView(out));
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save newsletter failed"));
    } finally {
      setNewsletterSaving(false);
    }
  }

  async function onRunNewsletterDigest(opts: { regenerate?: boolean; pushOnly?: boolean }) {
    if (!canOperate) return;
    setDigestRunBusy(true);
    setErr("");
    try {
      const out = await adminApi.runNewsletterDigest({
        regenerate: opts.regenerate === true,
        push_only: opts.pushOnly === true,
      });
      const dp = await adminApi.getNewsletterDigestToday();
      setDigestPreview(dp);
      const skipped = Boolean((out as { skipped?: boolean }).skipped);
      const ok = Boolean((out as { ok?: boolean }).ok);
      if (skipped) {
        const reason = (out as { reason?: string }).reason;
        const msg = (out as { message?: string }).message;
        setErr(msg || (reason ? `已跳过：${reason}` : "今日摘要任务已跳过"));
      } else if (!ok) {
        setErr(typeof (out as { error?: string }).error === "string" ? (out as { error: string }).error : "摘要任务未完全成功");
      } else {
        const msg = (out as { message?: string }).message;
        if (msg) setErr("");
      }
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "digest run failed"));
    } finally {
      setDigestRunBusy(false);
    }
  }

  async function onSaveRuntime(e: FormEvent) {
    e.preventDefault();
    if (!canManageSettings) return;
    setRuntimeSaving(true);
    setErr("");
    try {
      const payload: Record<string, unknown> = {
        cors_origins_csv: runtimeForm.cors_origins_csv.trim(),
        jwt_ttl_seconds: Math.min(864000, Math.max(60, Math.floor(Number(runtimeForm.jwt_ttl_seconds)) || 1800)),
        allowed_skew_seconds: Math.min(3600, Math.max(30, Math.floor(Number(runtimeForm.allowed_skew_seconds)) || 300)),
        require_https: runtimeForm.require_https,
        allow_insecure_localhost: runtimeForm.allow_insecure_localhost,
        admin_cookie_secure: runtimeForm.admin_cookie_secure,
        app_env: runtimeForm.app_env.trim() || "dev",
        demo_seed_enabled: runtimeForm.force_demo_seed ? true : null,
        legacy_admin_enabled: runtimeForm.legacy_admin_enabled,
        app_release_label: runtimeForm.app_release_label.trim(),
        hot_llm_model: runtimeForm.hot_llm_model.trim() || "rule-based",
      };
      const rt = await adminApi.saveRuntimeSettings(payload);
      setRuntimeView(rt);
      setRuntimeForm({
        cors_origins_csv: rt.cors_origins_csv,
        jwt_ttl_seconds: rt.jwt_ttl_seconds,
        allowed_skew_seconds: rt.allowed_skew_seconds,
        require_https: rt.require_https,
        allow_insecure_localhost: rt.allow_insecure_localhost,
        admin_cookie_secure: rt.admin_cookie_secure,
        app_env: rt.app_env,
        force_demo_seed: rt.demo_seed_enabled === true,
        legacy_admin_enabled: rt.legacy_admin_enabled,
        app_release_label: rt.app_release_label,
        hot_llm_model: rt.hot_llm_model,
      });
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save runtime failed"));
    } finally {
      setRuntimeSaving(false);
    }
  }

  async function onToggleSourceEnabled(row: Source) {
    if (!canOperate) return;
    const key = row.source;
    const preset = sourcePresets.find((p) => p.source === key);
    const draft = sourceCardDrafts[key] ?? defaultSourceCardDraft(row, preset);
    const showKey = preset?.show_api_key_field !== false;
    const showAppSecret = preset?.show_app_secret_field === true;
    setSourceToggleBusy(key);
    setErr("");
    try {
      await adminApi.saveSource({
        source: row.source,
        enabled: !row.enabled,
        api_base: draft.api_base.trim(),
        api_key: showKey ? draft.api_key.trim() : "",
        app_secret: showAppSecret ? draft.app_secret.trim() : "",
        notes: (row.notes ?? "").trim(),
        fetch_limit: Math.min(80, Math.max(1, Math.floor(Number(draft.fetch_limit)) || 10)),
        scope_labels: draft.scope_text
          .split(/[\n\r]+/)
          .map((x) => x.trim())
          .filter(Boolean),
      });
      setSourceCardDrafts((prev) => ({
        ...prev,
        [key]: { ...draft, api_key: "", app_secret: "" },
      }));
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save failed"));
    } finally {
      setSourceToggleBusy(null);
    }
  }

  async function saveSourceCard(sourceKey: string) {
    if (!canOperate) return;
    const saved = sources.find((s) => s.source === sourceKey);
    const preset = sourcePresets.find((p) => p.source === sourceKey);
    const draft = sourceCardDrafts[sourceKey] ?? defaultSourceCardDraft(saved, preset);
    const showKey = preset?.show_api_key_field !== false;
    const showAppSecret = preset?.show_app_secret_field === true;
    const enabled = saved?.enabled ?? preset?.enabled ?? true;
    setSourceCardSaving(sourceKey);
    setErr("");
    try {
      const row = (await adminApi.saveSource({
        source: sourceKey,
        enabled,
        api_base: draft.api_base.trim(),
        api_key: showKey ? draft.api_key.trim() : "",
        app_secret: showAppSecret && !phTokenDirect ? draft.app_secret.trim() : "",
        clear_app_secret: sourceKey === "product_hunt" && phTokenDirect,
        notes: sourceNotesForUpsert(saved, preset),
        fetch_limit: Math.min(80, Math.max(1, Math.floor(Number(draft.fetch_limit)) || 10)),
        scope_labels: draft.scope_text
          .split(/[\n\r]+/)
          .map((x) => x.trim())
          .filter(Boolean),
      })) as Source;
      setSourceCardDrafts((prev) => ({
        ...prev,
        [sourceKey]: {
          api_base: row.api_base || "",
          scope_text:
            row.scope_labels && row.scope_labels.length > 0
              ? row.scope_labels.join("\n")
              : (row.scope_label || "").trim(),
          api_key: "",
          app_secret: "",
          fetch_limit: row.fetch_limit ?? draft.fetch_limit,
        },
      }));
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save failed"));
    } finally {
      setSourceCardSaving(null);
    }
  }

  async function onSaveSource(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await adminApi.saveSource({
        source: sourceForm.source,
        enabled: sourceForm.enabled,
        api_base: sourceForm.api_base,
        api_key: sourceForm.api_key,
        app_secret:
          sourceFormShowsAppSecret && !(sourceForm.source.trim().toLowerCase() === "product_hunt" && phTokenDirect)
            ? sourceForm.app_secret
            : "",
        clear_app_secret: sourceForm.source.trim().toLowerCase() === "product_hunt" && phTokenDirect,
        notes: sourceForm.notes,
        fetch_limit: Math.min(80, Math.max(1, Math.floor(Number(sourceForm.fetch_limit)) || 10)),
        scope_labels: sourceForm.scope_labels.map((s) => s.trim()).filter(Boolean),
      });
      setSourceForm((p) => ({ ...p, api_key: "", app_secret: "" }));
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "save failed"));
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

  async function onClearProductIngest() {
    if (!canManageSettings) return;
    if (
      !window.confirm(
        "将删除所有已入库的资源文章、指标点、连接器同步日志、热门快照与 LLM 用量记录，并重置各连接器的上次同步时间（连接器配置、行业/板块、CMS 页、软件包保留）。确定？",
      )
    )
      return;
    setClearIngestBusy(true);
    setErr("");
    try {
      const counts = await adminApi.clearProductIngestData();
      const lines = Object.entries(counts)
        .map(([k, v]) => `${k}: ${v}`)
        .join("\n");
      window.alert(`已清空。\n${lines}`);
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "clear ingest failed"));
    } finally {
      setClearIngestBusy(false);
    }
  }

  async function copyDiagnosticLogsToClipboard() {
    const runId = diagRunFilter.trim();
    try {
      let text: string;
      if (runId) {
        try {
          text = await adminApi.exportSyncDiagnosticLogs(runId, 800);
        } catch {
          text = buildDiagLogClipboardText(diagLogs, {
            runId,
            diagVersion: diagPipelineVersion || undefined,
          });
        }
      } else {
        text = buildDiagLogClipboardText(diagLogs, { diagVersion: diagPipelineVersion || undefined });
      }
      await navigator.clipboard.writeText(text);
      setDiagCopyOk(true);
      window.setTimeout(() => setDiagCopyOk(false), 2500);
    } catch (e) {
      setErr(friendlyErr(e instanceof Error ? e.message : "复制失败"));
    }
  }

  async function onThemeFetch() {
    if (!canManageSettings) return;
    setThemeFetchBusy(true);
    setErr("");
    try {
      const r = await adminApi.themeFetchProductData({});
      if (r.diagnostic_run_id) {
        setDiagRunFilter(r.diagnostic_run_id);
        setTab("logs");
        await loadDiagnosticLogs(r.diagnostic_run_id);
      } else {
        await loadDiagnosticLogs();
        setTab("logs");
      }
      await loadAdminData();
      const failed = (r.details ?? []).filter((d) => d.error);
      const summary = `拉取完成：成功 ${r.ok}/${r.connectors_total}，新建文章合计 ${(r.details ?? []).reduce((n, d) => n + (d.articles_created ?? 0), 0)}。`;
      if (r.fail > 0 || failed.length > 0) {
        const lines = failed
          .map((d) => `· ${d.name ?? d.connector_id}: ${d.error ?? "失败"}`)
          .join("\n");
        setErr(
          `${summary}\n${lines}\n\n${r.log_hint ?? "请到「同步日志」复制本批日志发给运维。"}`,
        );
      } else if (r.log_hint) {
        window.alert(`${summary}\n\n${r.log_hint}`);
      }
    } catch (error) {
      const msg = friendlyErr(error instanceof Error ? error.message : "theme fetch failed");
      setErr(`${msg}\n\n拉取可能已部分执行：请到顶部「同步日志」查看最新 run_id 并复制日志。`);
      setTab("logs");
      await loadDiagnosticLogs(diagRunFilter || undefined);
    } finally {
      setThemeFetchBusy(false);
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
      <>
        <div className="admin-status-strip" aria-hidden="false">
          <span className="admin-status-strip__left">
            <span className="admin-status-pulse" />
            Ai-trends 管理
          </span>
          <span className="admin-status-strip__right">
            <span className="admin-status-meta">
              build <span className="admin-status-build">{adminUiRelease}</span>
            </span>
            <span className="admin-status-meta">{new Date().toISOString().slice(0, 10)} UTC</span>
          </span>
        </div>
        <main className="login-screen">
          <div className="login-brand">
            <h1>Ai-trends 管理</h1>
            <p>后台管理台 · 基于会话登录</p>
            <div className="muted tiny" style={{ marginTop: 10 }}>
              仅浏览可查数据；运营可管理数据源；管理员可管理账号。
            </div>
            <div className="muted tiny" style={{ marginTop: 8, fontSize: 11, opacity: 0.85 }}>
              前端构建 {adminUiRelease}
            </div>
          </div>
          <form className="card grid login-card" onSubmit={onLogin}>
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
      </>
    );
  }

  return (
    <>
      <div className="admin-status-strip">
        <span className="admin-status-strip__left">
          <span className="admin-status-pulse" />
          Ai-trends 管理
        </span>
        <span className="admin-status-strip__right">
          <span className="admin-status-meta">
            build <span className="admin-status-build">{adminUiRelease}</span>
            {publicApiRelease ? (
              <>
                {" "}
                · api <span className="admin-status-api">{publicApiRelease}</span>
              </>
            ) : (
              <span className="admin-status-wait"> · api …</span>
            )}
          </span>
          <span className="admin-status-meta">{new Date().toISOString().slice(0, 10)} UTC</span>
        </span>
      </div>
      <main className="shell">
      <aside className="sidebar">
        <h2 style={{ marginTop: 0 }}>Ai-trends 管理</h2>
        <p className="muted tiny">
          {me?.username} · {zhRole(me?.role)}
        </p>
        <p className="muted tiny" style={{ fontSize: 10, lineHeight: 1.5, marginTop: 6 }}>
          前端 {adminUiRelease}
          <br />
          API {publicApiRelease ?? "…"}
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
            className={tab === "ai" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("ai")}
            title="含 LLM、定时同步、清空资源入库数据"
          >
            AI 资讯与数据
          </button>
          <button
            type="button"
            className={tab === "software" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("software")}
          >
            应用分发
          </button>
          <button
            type="button"
            className={tab === "logs" ? "admin-nav-tab admin-nav-tab--active" : "admin-nav-tab"}
            onClick={() => setTab("logs")}
            title="连接器拉取与入库步骤日志"
          >
            同步日志
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
              <div className="muted tiny" style={{ marginTop: 10 }}>
                发布标识：前端 <strong style={{ color: "#312e81" }}>{adminUiRelease}</strong> · API{" "}
                <strong style={{ color: "#312e81" }}>{publicApiRelease ?? "…"}</strong>
              </div>
            </section>
            {canManageSettings ? (
              <section className="card">
                <div className="row between">
                  <h3>清空资源入库数据</h3>
                  <span className="tag">管理员</span>
                </div>
                <p className="muted tiny" style={{ marginTop: 8, lineHeight: 1.6 }}>
                  删除连接器产生的文章、指标点、同步日志、热门快照、LLM 用量记录；同步清空由数据源合并的「领域」行业及其下属板块（主题分类）；并重置各连接器上次同步时间（连接器与数据源账号配置保留，演示用「AI」等行业不受影响）。详细说明与 LLM 在同一页：「AI
                  资讯与数据」。
                </p>
                <div style={{ marginTop: 14 }}>
                  <button
                    type="button"
                    disabled={clearIngestBusy}
                    onClick={() => void onClearProductIngest()}
                    style={{
                      border: "1px solid rgba(220, 38, 38, 0.45)",
                      color: "#991b1b",
                      background: "rgba(254, 226, 226, 0.95)",
                      fontWeight: 600,
                      padding: "10px 16px",
                      borderRadius: 10,
                      cursor: clearIngestBusy ? "not-allowed" : "pointer",
                    }}
                  >
                    {clearIngestBusy ? "清空中…" : "清空资源入库数据"}
                  </button>
                </div>
                <div style={{ marginTop: 22, paddingTop: 18, borderTop: "1px solid rgba(148,163,184,0.2)" }}>
                  <p className="muted tiny" style={{ margin: "0 0 10px", lineHeight: 1.6 }}>
                    先同步数据源领域到行业/板块，再对<strong>已启用</strong>连接器整批立即拉取（与定时任务同逻辑，且绕过单连接器最短间隔）。
                  </p>
                  <button
                    type="button"
                    disabled={themeFetchBusy || clearIngestBusy}
                    onClick={() => void onThemeFetch()}
                    style={{
                      border: "1px solid rgba(14, 165, 233, 0.45)",
                      color: "#0c4a6e",
                      background: "rgba(224, 242, 254, 0.95)",
                      fontWeight: 600,
                      padding: "10px 16px",
                      borderRadius: 10,
                      cursor: themeFetchBusy || clearIngestBusy ? "not-allowed" : "pointer",
                    }}
                  >
                    {themeFetchBusy ? "拉取中…" : "拉取全部数据"}
                  </button>
                </div>
              </section>
            ) : (
              <section className="card">
                <h3>清空资源入库数据</h3>
                <p className="muted tiny" style={{ marginTop: 8, lineHeight: 1.6 }}>
                  仅<strong>管理员</strong>可在「总览」使用此项，或在「AI 资讯与数据」页操作。
                </p>
              </section>
            )}
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
                  <div className="muted tiny">切换方式：设置后端环境变量 `AITRENDS_DB_MODE=test|prod`，然后重启后端服务。</div>
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
              <div>
                <h3 style={{ margin: 0 }}>数据源</h3>
                <p className="muted tiny" style={{ margin: "8px 0 0" }}>
                  上方卡片为<strong>内置模板 + 已保存的自定义标识</strong>同一列表：未入库时显示模板默认值与「未入库」；保存后展示库内接口与领域主题。生产环境请用卡片上的<strong>启用 / 停用</strong>控制是否参与调度，无需在后台删除整条配置。定时拉取在「AI
                  资讯与数据」页配置；连接器绑定标识后参与调度。内置模板现仅保留 <strong>AI 向</strong> 源（代码协作、Spaces、应用首发等）；一次同步仍由系统聚合成<strong>一篇</strong>站内稿。GitLab 等地址在<strong>测试连接</strong>时会根据接口地址自动选择 Bearer 或 Private Token 头。
                </p>
                <p className="muted tiny" style={{ margin: "10px 0 0" }}>
                  连接器对「api_base」只做<strong>单次 HTTP GET</strong>（可选密钥头），<strong>不模拟浏览器、不执行站点前端 JS、也不代你登录任意网站后台</strong>，因此拿不到依赖登录页或整页 HTML 渲染才出现的「门户正文」；若上游 JSON
                  本身只有元数据、计数、行情或目录字段，结果就会像「统计/目录」而非报道。要拉<strong>可读的条目型内容</strong>，请优先配置<strong>RSS/Atom</strong>或<strong>带标题/摘要/链接（或正文）字段的官方 API</strong>；整站爬取、无头浏览器、复杂登录流不在当前内置范围内。
                </p>
                <p className="muted tiny" style={{ margin: "10px 0 0" }}>
                  <strong>密钥与同步</strong>：公开/免 Key 的预置模板卡片<strong>不展示</strong>密钥输入，仅在有掩码时显示一行脱敏；需 Token 的预置（如 Product Hunt 需 <strong>Bearer access_token</strong>，且可另存 <strong>OAuth Client Secret</strong>）及<strong>自定义标识</strong>可在卡片上填写。亦可始终在页面下方<strong>保存数据源</strong>表单维护：保存时写入绑定连接器的 <code>config_json.api_key</code> / <code>oauth_client_secret</code>（后者仅 Product Hunt 等），留空表示<strong>不修改</strong>已有值。「连接器 Token」显示各连接器内是否已有 api_key 与（若适用）OAuth Secret。
                </p>
              </div>
              {sourcePresetsLoading ? <p className="muted tiny" style={{ marginTop: 12 }}>正在加载数据源列表…</p> : null}
              {sourcePresetsError ? (
                <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
                  <span className="err-text">{sourcePresetsError}</span>
                  <button type="button" className="btn-ghost" onClick={() => loadSourcePresets()}>
                    重试
                  </button>
                </div>
              ) : null}
              {!sourcePresetsLoading && !sourcePresetsError && !showSourceBoard ? (
                <p className="muted tiny" style={{ marginTop: 12 }}>
                  未获取到条目。请确认已登录且后端提供 <code>GET /api/admin/v1/sources/presets</code>，或切换离开本页再进入以重试加载。
                </p>
              ) : null}
              {showSourceBoard && (!sourcePresetsError || customSourcesOnly.length > 0) ? (
                <>
                  <div className="sources-board sources-board--presets">
                    {sourcePresets.map((p) => {
                        const saved = sources.find((s) => s.source === p.source);
                        const pubFeed = publicFeedLaneForSourceKey(p.source);
                        const draft = sourceCardDrafts[p.source] ?? defaultSourceCardDraft(saved, p);
                        const testBase = draft.api_base.trim() || (saved?.api_base || "").trim() || p.api_base || "";
                        const maskLine = saved?.api_key_masked ? formatApiKeyDisplay(saved.api_key_masked) : "";
                        const cardTestKey = `card:${p.source}`;
                        const showApiKey = p.show_api_key_field !== false;
                        const showAppSecret = p.show_app_secret_field === true;
                        const secretMaskLine = saved?.app_secret_masked
                          ? formatApiKeyDisplay(saved.app_secret_masked)
                          : "";
                        return (
                          <article
                            key={p.source}
                            className={`source-card source-card--preset${saved ? " source-card--preset-exists" : ""}`}
                          >
                            <div className="source-card__head">
                              <h4 className="source-card__title">{p.label}</h4>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", justifyContent: "flex-end" }}>
                                <span
                                  className={pubFeed.lane === "apps" ? "tag ok" : "tag"}
                                  title={pubFeed.detail}
                                  style={{ fontWeight: 600 }}
                                >
                                  前台：{pubFeed.title}
                                </span>
                                <span className={saved ? (saved.enabled ? "tag ok" : "tag") : "tag"}>
                                  {saved ? (saved.enabled ? "已启用" : "已停用") : "未入库"}
                                </span>
                              </div>
                            </div>
                            {p.content_role_label_zh ? (
                              <p className="muted tiny" style={{ margin: "6px 0 0" }}>
                                内容类型：{p.content_role_label_zh}
                              </p>
                            ) : null}
                            <dl className="source-card__meta">
                              <div className="source-card__meta-row">
                                <dt>前台 Feed</dt>
                                <dd className="muted tiny" title={pubFeed.detail}>
                                  {pubFeed.title}
                                </dd>
                              </div>
                              <div className="source-card__meta-row">
                                <dt>标识</dt>
                                <dd style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{p.source}</dd>
                              </div>
                              <div className="source-card__meta-row">
                                <dt>接口地址</dt>
                                <dd style={{ margin: 0 }}>
                                  <input
                                    style={{
                                      width: "100%",
                                      boxSizing: "border-box",
                                      fontFamily: "var(--font-mono)",
                                      fontSize: 12,
                                      padding: "6px 8px",
                                    }}
                                    value={draft.api_base}
                                    onChange={(e) =>
                                      setSourceCardDrafts((prev) => ({
                                        ...prev,
                                        [p.source]: { ...(prev[p.source] ?? defaultSourceCardDraft(saved, p)), api_base: e.target.value },
                                      }))
                                    }
                                  />
                                </dd>
                              </div>
                              <div className="source-card__meta-row">
                                <dt>拉取节奏</dt>
                                <dd className="muted tiny">统一定时（「AI 资讯与数据」页配置间隔）</dd>
                              </div>
                              <div className="source-card__meta-row">
                                <dt>单次拉取条数</dt>
                                <dd style={{ margin: 0 }}>
                                  <input
                                    type="number"
                                    min={1}
                                    max={80}
                                    style={{ width: 88, padding: "4px 8px", fontSize: 12 }}
                                    value={draft.fetch_limit}
                                    onChange={(e) =>
                                      setSourceCardDrafts((prev) => ({
                                        ...prev,
                                        [p.source]: {
                                          ...(prev[p.source] ?? defaultSourceCardDraft(saved, p)),
                                          fetch_limit: Number(e.target.value),
                                        },
                                      }))
                                    }
                                  />
                                  <span className="muted tiny" style={{ marginLeft: 8 }}>
                                    热度 Top N（Product Hunt 建议 ≤30）
                                  </span>
                                </dd>
                              </div>
                              <div className="source-card__meta-row source-card__meta-row--scope-inline">
                                <dt>领域主题</dt>
                                <dd>
                                  <textarea
                                    rows={2}
                                    style={{
                                      width: "100%",
                                      boxSizing: "border-box",
                                      fontSize: 12,
                                      resize: "vertical",
                                      padding: "6px 8px",
                                    }}
                                    placeholder="每行一个主题，可用「大类｜细分」"
                                    value={draft.scope_text}
                                    onChange={(e) =>
                                      setSourceCardDrafts((prev) => ({
                                        ...prev,
                                        [p.source]: { ...(prev[p.source] ?? defaultSourceCardDraft(saved, p)), scope_text: e.target.value },
                                      }))
                                    }
                                  />
                                </dd>
                              </div>
                              {saved ? (
                                <div className="source-card__meta-row">
                                  <dt>连接器 Token</dt>
                                  <dd className="muted tiny">
                                    {saved.connectors_token_status && saved.connectors_token_status.length > 0 ? (
                                      saved.connectors_token_status.map((c) => (
                                        <span key={c.connector_id} style={{ display: "block" }}>
                                          {c.name}（#{c.connector_id}
                                          {c.enabled ? "" : "，已停用"}）：{c.has_api_key ? "已填 api_key" : "未填 api_key（同步不会带头）"}
                                          {showAppSecret
                                            ? `；OAuth Client Secret：${c.has_oauth_client_secret ? "已填" : "未填"}`
                                            : ""}
                                        </span>
                                      ))
                                    ) : (
                                      <>无绑定连接器；请到「连接器」绑定该标识或重启后端由系统补全。</>
                                    )}
                                  </dd>
                                </div>
                              ) : null}
                            </dl>
                            {!showApiKey && maskLine ? (
                              <div
                                className="muted tiny"
                                style={{ marginTop: 10, fontFamily: "var(--font-mono)", fontSize: 12, wordBreak: "break-all" }}
                              >
                                {maskLine}
                              </div>
                            ) : null}
                            {canOperate ? (
                              <>
                                {showApiKey ? (
                                  <div className="source-card__meta-row" style={{ marginTop: 10 }}>
                                    <dt>{showAppSecret ? "Bearer Access Token" : "API Key"}</dt>
                                    <dd style={{ margin: 0 }}>
                                      <input
                                        type="password"
                                        autoComplete="off"
                                        placeholder={
                                          showAppSecret && p.source === "product_hunt" && phTokenDirect
                                            ? "粘贴 Product Hunt Access Token"
                                            : showAppSecret
                                              ? "OAuth 换到的 access_token；留空保存不修改"
                                              : "填写新密钥；留空并保存表示不修改已有密钥"
                                        }
                                        style={{
                                          width: "100%",
                                          boxSizing: "border-box",
                                          fontFamily: "var(--font-mono)",
                                          fontSize: 12,
                                          padding: "6px 8px",
                                        }}
                                        value={draft.api_key}
                                        onChange={(e) =>
                                          setSourceCardDrafts((prev) => ({
                                            ...prev,
                                            [p.source]: { ...(prev[p.source] ?? defaultSourceCardDraft(saved, p)), api_key: e.target.value },
                                          }))
                                        }
                                      />
                                      {maskLine ? (
                                        <div
                                          className="muted tiny"
                                          style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 12, wordBreak: "break-all" }}
                                        >
                                          已保存 Token：{maskLine}
                                        </div>
                                      ) : (
                                        <div className="muted tiny" style={{ marginTop: 8 }}>
                                          {showAppSecret && p.source === "product_hunt" && phTokenDirect
                                            ? "在 Product Hunt 开发者后台创建 Access Token，粘贴到上方并保存。"
                                            : showAppSecret
                                              ? "Client ID 在 Product Hunt 开发者后台查看；此处填换到的 Bearer Token。"
                                              : "保存后在此显示首尾掩码；留空保存不改动已有密钥。"}
                                        </div>
                                      )}
                                    </dd>
                                  </div>
                                ) : null}
                                {showApiKey && p.source === "product_hunt" ? (
                                  <div className="source-card__meta-row" style={{ marginTop: 10 }}>
                                    <dt>鉴权方式</dt>
                                    <dd style={{ margin: 0 }}>
                                      <label className="row" style={{ gap: 8, alignItems: "center", cursor: "pointer" }}>
                                        <input
                                          type="checkbox"
                                          checked={phTokenDirect}
                                          onChange={(e) => setPhTokenDirect(e.target.checked)}
                                        />
                                        <span className="muted tiny">
                                          仅使用 Access Token（Bearer 直连；保存时清除已存的 APP Secret）
                                        </span>
                                      </label>
                                    </dd>
                                  </div>
                                ) : null}
                                {showApiKey && showAppSecret && !(p.source === "product_hunt" && phTokenDirect) ? (
                                  <div className="source-card__meta-row" style={{ marginTop: 10 }}>
                                    <dt>APP Secret</dt>
                                    <dd style={{ margin: 0 }}>
                                      <input
                                        type="password"
                                        autoComplete="off"
                                        placeholder="OAuth Client Secret；留空保存不修改"
                                        style={{
                                          width: "100%",
                                          boxSizing: "border-box",
                                          fontFamily: "var(--font-mono)",
                                          fontSize: 12,
                                          padding: "6px 8px",
                                        }}
                                        value={draft.app_secret}
                                        onChange={(e) =>
                                          setSourceCardDrafts((prev) => ({
                                            ...prev,
                                            [p.source]: { ...(prev[p.source] ?? defaultSourceCardDraft(saved, p)), app_secret: e.target.value },
                                          }))
                                        }
                                      />
                                      {secretMaskLine ? (
                                        <div
                                          className="muted tiny"
                                          style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 12, wordBreak: "break-all" }}
                                        >
                                          已保存 Secret：{secretMaskLine}
                                        </div>
                                      ) : (
                                        <div className="muted tiny" style={{ marginTop: 8 }}>
                                          与 Developer OAuth 的 client_secret 一致；写入绑定连接器 config_json.oauth_client_secret。
                                        </div>
                                      )}
                                    </dd>
                                  </div>
                                ) : null}
                                <div className="source-card__actions row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
                                  <button
                                    type="button"
                                    className="btn-ghost"
                                    disabled={sourceTestLoading === cardTestKey || !testBase.trim() || !!sourceCardSaving}
                                    title={
                                      !testBase.trim()
                                        ? "请先填写接口地址"
                                        : showApiKey
                                          ? "测试连接（不落库）"
                                          : "测试连接（不落库；免 Key 模板通常不带鉴权头）"
                                    }
                                    onClick={() =>
                                      void runSourceTest(
                                        saved
                                          ? {
                                              source: p.source,
                                              ...(draft.api_key.trim() && showApiKey ? { api_key: draft.api_key.trim() } : {}),
                                            }
                                          : {
                                              api_base: testBase,
                                              ...(draft.api_key.trim() && showApiKey ? { api_key: draft.api_key.trim() } : {}),
                                            },
                                        cardTestKey,
                                        inferSourceTestAuth(saved ? p.source : undefined, testBase),
                                      )
                                    }
                                  >
                                    {sourceTestLoading === cardTestKey ? "测试中…" : "测试连接"}
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-ghost"
                                    disabled={!!sourceCardSaving || !!sourceToggleBusy}
                                    style={{ fontWeight: 600 }}
                                    title={
                                      showApiKey
                                        ? showAppSecret
                                          ? "保存接口、领域主题、Bearer Token 与 APP Secret（留空不修改对应项）"
                                          : "保存当前卡片中的接口、领域主题与密钥（留空密钥不修改）"
                                        : "保存当前卡片中的接口与领域主题（密钥请在下方表单或需密钥的预置卡片上维护）"
                                    }
                                    onClick={() => void saveSourceCard(p.source)}
                                  >
                                    {sourceCardSaving === p.source ? "保存中…" : "保存"}
                                  </button>
                                  {saved ? (
                                    <button
                                      type="button"
                                      className="btn-ghost"
                                      disabled={sourceToggleBusy === saved.source || !!sourceCardSaving}
                                      title={saved.enabled ? "暂停参与连接器调度" : "恢复参与连接器调度"}
                                      onClick={() => void onToggleSourceEnabled(saved)}
                                    >
                                      {sourceToggleBusy === saved.source ? "保存中…" : saved.enabled ? "停用" : "启用"}
                                    </button>
                                  ) : null}
                                </div>
                                {sourceTestResult?.key === cardTestKey ? (
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
                      {customSourcesOnly.map((s) => {
                        const pubFeed = publicFeedLaneForSourceKey(s.source);
                        const draft = sourceCardDrafts[s.source] ?? defaultSourceCardDraft(s, undefined);
                        const testBase = draft.api_base.trim() || (s.api_base || "").trim();
                        const maskLine = s.api_key_masked ? formatApiKeyDisplay(s.api_key_masked) : "";
                        const cardTestKey = `card:${s.source}`;
                        return (
                        <article key={s.source} className="source-card source-card--preset-exists">
                          <div className="source-card__head">
                            <h4 className="source-card__title">{s.source}</h4>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", justifyContent: "flex-end" }}>
                              <span
                                className={pubFeed.lane === "apps" ? "tag ok" : "tag"}
                                title={pubFeed.detail}
                                style={{ fontWeight: 600 }}
                              >
                                前台：{pubFeed.title}
                              </span>
                              <span className={s.enabled ? "tag ok" : "tag"}>{s.enabled ? "已启用" : "已停用"}</span>
                            </div>
                          </div>
                          <dl className="source-card__meta">
                            <div className="source-card__meta-row">
                              <dt>前台 Feed</dt>
                              <dd className="muted tiny" title={pubFeed.detail}>
                                {pubFeed.title}
                              </dd>
                            </div>
                            <div className="source-card__meta-row">
                              <dt>拉取节奏</dt>
                              <dd className="muted tiny">统一定时（「AI 资讯与数据」页配置间隔）</dd>
                            </div>
                            <div className="source-card__meta-row">
                              <dt>单次拉取条数</dt>
                              <dd style={{ margin: 0 }}>
                                <input
                                  type="number"
                                  min={1}
                                  max={80}
                                  style={{ width: 88, padding: "4px 8px", fontSize: 12 }}
                                  value={draft.fetch_limit}
                                  onChange={(e) =>
                                    setSourceCardDrafts((prev) => ({
                                      ...prev,
                                      [s.source]: {
                                        ...(prev[s.source] ?? defaultSourceCardDraft(s, undefined)),
                                        fetch_limit: Number(e.target.value),
                                      },
                                    }))
                                  }
                                />
                                <span className="muted tiny" style={{ marginLeft: 8 }}>
                                  热度 Top N（1～80）
                                </span>
                              </dd>
                            </div>
                            <div className="source-card__meta-row">
                              <dt>接口地址</dt>
                              <dd style={{ margin: 0 }}>
                                <input
                                  style={{
                                    width: "100%",
                                    boxSizing: "border-box",
                                    fontFamily: "var(--font-mono)",
                                    fontSize: 12,
                                    padding: "6px 8px",
                                  }}
                                  value={draft.api_base}
                                  onChange={(e) =>
                                    setSourceCardDrafts((prev) => ({
                                      ...prev,
                                      [s.source]: { ...(prev[s.source] ?? defaultSourceCardDraft(s, undefined)), api_base: e.target.value },
                                    }))
                                  }
                                />
                              </dd>
                            </div>
                            <div className="source-card__meta-row source-card__meta-row--scope-inline">
                              <dt>领域主题</dt>
                              <dd>
                                <textarea
                                  rows={2}
                                  style={{
                                    width: "100%",
                                    boxSizing: "border-box",
                                    fontSize: 12,
                                    resize: "vertical",
                                    padding: "6px 8px",
                                  }}
                                  placeholder="每行一个主题，可用「大类｜细分」"
                                  value={draft.scope_text}
                                  onChange={(e) =>
                                    setSourceCardDrafts((prev) => ({
                                      ...prev,
                                      [s.source]: { ...(prev[s.source] ?? defaultSourceCardDraft(s, undefined)), scope_text: e.target.value },
                                    }))
                                  }
                                />
                              </dd>
                            </div>
                            <div className="source-card__meta-row">
                              <dt>连接器 Token</dt>
                              <dd className="muted tiny">
                                {s.connectors_token_status && s.connectors_token_status.length > 0 ? (
                                  s.connectors_token_status.map((c) => (
                                    <span key={c.connector_id} style={{ display: "block" }}>
                                      {c.name}（#{c.connector_id}
                                      {c.enabled ? "" : "，已停用"}）：{c.has_api_key ? "已填 api_key" : "未填 api_key（同步不会带头）"}
                                    </span>
                                  ))
                                ) : (
                                  <>无绑定连接器；请到「连接器」绑定该标识。</>
                                )}
                              </dd>
                            </div>
                          </dl>
                          {canOperate ? (
                            <>
                              <div className="source-card__meta-row" style={{ marginTop: 10 }}>
                                <dt>API Key</dt>
                                <dd style={{ margin: 0 }}>
                                  <input
                                    type="password"
                                    autoComplete="off"
                                    placeholder="填写新密钥；留空并保存表示不修改已有密钥"
                                    style={{
                                      width: "100%",
                                      boxSizing: "border-box",
                                      fontFamily: "var(--font-mono)",
                                      fontSize: 12,
                                      padding: "6px 8px",
                                    }}
                                    value={draft.api_key}
                                    onChange={(e) =>
                                      setSourceCardDrafts((prev) => ({
                                        ...prev,
                                        [s.source]: { ...(prev[s.source] ?? defaultSourceCardDraft(s, undefined)), api_key: e.target.value },
                                      }))
                                    }
                                  />
                                  {maskLine ? (
                                    <div
                                      className="muted tiny"
                                      style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 12, wordBreak: "break-all" }}
                                    >
                                      已保存：{maskLine}
                                    </div>
                                  ) : (
                                    <div className="muted tiny" style={{ marginTop: 8 }}>
                                      保存后在此显示首尾掩码；留空保存不改动已有密钥。
                                    </div>
                                  )}
                                </dd>
                              </div>
                              <div className="source-card__actions row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 12 }}>
                                <button
                                  type="button"
                                  className="btn-ghost"
                                  disabled={sourceTestLoading === cardTestKey || !testBase.trim() || !!sourceCardSaving}
                                  title={!testBase.trim() ? "请先填写接口地址" : "测试连接（不落库）"}
                                  onClick={() =>
                                    void runSourceTest(
                                      {
                                        source: s.source,
                                        ...(draft.api_key.trim() ? { api_key: draft.api_key.trim() } : {}),
                                      },
                                      cardTestKey,
                                      inferSourceTestAuth(s.source, testBase),
                                    )
                                  }
                                >
                                  {sourceTestLoading === cardTestKey ? "测试中…" : "测试连接"}
                                </button>
                                <button
                                  type="button"
                                  className="btn-ghost"
                                  disabled={!!sourceCardSaving || !!sourceToggleBusy}
                                  style={{ fontWeight: 600 }}
                                  title="保存当前卡片中的接口、领域主题与密钥（留空密钥不修改）"
                                  onClick={() => void saveSourceCard(s.source)}
                                >
                                  {sourceCardSaving === s.source ? "保存中…" : "保存"}
                                </button>
                                <button
                                  type="button"
                                  className="btn-ghost"
                                  disabled={sourceToggleBusy === s.source || !!sourceCardSaving}
                                  title={s.enabled ? "暂停参与连接器调度" : "恢复参与连接器调度"}
                                  onClick={() => void onToggleSourceEnabled(s)}
                                >
                                  {sourceToggleBusy === s.source ? "保存中…" : s.enabled ? "停用" : "启用"}
                                </button>
                              </div>
                              {sourceTestResult?.key === cardTestKey ? (
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
                </>
              ) : null}
            </div>

            <div className="source-card-wrap" style={{ marginTop: 16 }}>
              <article id="admin-source-form" className="source-card source-card--form">
                <div className="source-card__head">
                  <h4 className="source-card__title">{sources.length === 0 ? "新增数据源" : "添加或更新数据源"}</h4>
                  <span className="tag">表单</span>
                </div>
                <p className="muted tiny" style={{ margin: 0 }}>
                  填写标识与接口信息保存即可；标识与已有 source 相同时为更新。上方卡片可编辑接口与领域主题并点<strong>保存</strong>；免 Key 预置无卡片密钥框时密钥在本表单填写。
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
                  <div className="form-field" style={{ maxWidth: 160 }}>
                    <label>单次拉取条数（1～80）</label>
                    <input
                      type="number"
                      min={1}
                      max={80}
                      value={sourceForm.fetch_limit}
                      onChange={(e) => setSourceForm((p) => ({ ...p, fetch_limit: Number(e.target.value) }))}
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
                          placeholder="如：AI｜大模型、AI｜Agent、开源模型"
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
                    <label>{sourceFormShowsAppSecret ? "Bearer Access Token（可修改）" : "API Key（可修改）"}</label>
                    {sourceForm.source.trim() ? (
                      <p className="muted tiny" style={{ margin: "0 0 6px" }}>
                        {sourceApiKeyStatusLine}
                      </p>
                    ) : null}
                    <input
                      value={sourceForm.api_key}
                      onChange={(e) => setSourceForm((p) => ({ ...p, api_key: e.target.value }))}
                      placeholder={
                        sourceFormShowsAppSecret
                          ? "OAuth access_token；留空则保存时不改动已有 Token"
                          : "输入新密钥以覆盖；留空则保存时不改动已有密钥"
                      }
                      type="password"
                      autoComplete="new-password"
                    />
                  </div>
                  {sourceFormShowsAppSecret ? (
                    <div className="form-field">
                      <label>APP Secret / OAuth Client Secret（可修改）</label>
                      <p className="muted tiny" style={{ margin: "0 0 6px" }}>
                        Product Hunt Developer 应用的 client_secret；留空保存表示不修改已存值。会同步到绑定连接器的{" "}
                        <code className="inline-code">oauth_client_secret</code>。
                      </p>
                      <input
                        value={sourceForm.app_secret}
                        onChange={(e) => setSourceForm((p) => ({ ...p, app_secret: e.target.value }))}
                        placeholder="留空则保存时不改动已有 Secret"
                        type="password"
                        autoComplete="new-password"
                      />
                    </div>
                  ) : null}
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

        {tab === "ai" ? (
          <section className="settings-stack ai-config-stack">
            <div className="card ai-hero-panel">
              <div className="ai-hero-grid">
                <div>
                  <p className="ai-hero-kicker">大模型 · OpenAI 兼容协议</p>
                  <h2 className="ai-hero-title">AI 资讯生成与去重</h2>
                  <p className="muted tiny" style={{ marginTop: 10, maxWidth: 520, lineHeight: 1.6 }}>
                    连接器拉取原始片段 → 入库指纹去重 → 规则价值分 → <strong>DeepSeek</strong>{" "}
                    全文重写（分类 + 多 tab）→ 展示指纹去重 → 发布；未配置模型则不入库。请在下方保存{" "}
                    <strong>Base URL / Model / API Key</strong>（保存后存于库表 <code className="inline-code">product_settings_kv.llm</code>）；接口仅返回脱敏掩码。可继续保留 <code className="inline-code">backend/.env</code> 中的 <code className="inline-code">AITRENDS_LLM_*</code> 作备份，若库内尚未配置，启动时会自动迁入。
                  </p>
                </div>
                <div className="ai-hero-metrics">
                  <div>
                    <span className="ai-metric-label">密钥状态</span>
                    <span className="ai-metric-value">{llmSettings?.has_api_key ? "已配置" : "未配置"}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="card settings-panel ai-pipeline-card">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                流水线（Agent 逻辑保持线性）
              </h3>
              <ol className="ai-pipeline-list">
                {(llmSettings?.pipeline ?? []).map((step, i) => (
                  <li key={step.id}>
                    <span className="ai-pipeline-idx">{i + 1}</span>
                    <span>{step.label}</span>
                  </li>
                ))}
              </ol>
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                定时同步与数据清理
              </h3>
              <p className="muted tiny" style={{ marginTop: 6, lineHeight: 1.6 }}>
                进程内每 <strong>{schedulerSettings?.gate_interval_minutes ?? 15} 分钟</strong>检查一次；仅在<strong>美东当日 23:00–24:00</strong>触发整批同步（与 NewsAPI 等按美国日切分的数据源对齐，每日最多一次）。对<strong>所有已启用</strong>连接器执行同步（与手动「同步」同逻辑，且<strong>不受</strong>单连接器{" "}
                <code className="inline-code">min_interval_seconds</code> 限制）。配置保存在{" "}
                <code className="inline-code">product_settings_kv.scheduler</code>。
              </p>
              {schedulerSettings ? (
                <p className="muted tiny" style={{ marginTop: 8 }}>
                  上次整批成功时间：<strong style={{ color: "#312e81" }}>{schedulerSettings.last_connector_batch_at || "—（尚未成功跑过一批）"}</strong>
                  {" · "}
                  当前整批间隔：<strong>{schedulerSettings.connector_sync_interval_hours}</strong> 小时
                  {schedulerSettings.daily_slot_times_local ? (
                    <>
                      {" · "}
                      拉取窗口（{schedulerSettings.scheduler_timezone ?? "America/New_York"}）：<strong>{schedulerSettings.daily_slot_times_local}</strong>
                    </>
                  ) : null}
                </p>
              ) : null}
              {canOperate ? (
                <form className="create-user-form" onSubmit={onSaveScheduler} style={{ marginTop: 14 }}>
                  <div className="form-field" style={{ maxWidth: 360 }}>
                    <label>
                      <input
                        type="checkbox"
                        checked={schedulerForm.enabled}
                        onChange={(e) => setSchedulerForm((p) => ({ ...p, enabled: e.target.checked }))}
                      />{" "}
                      启用定时批量同步
                    </label>
                  </div>
                  <div className="form-field" style={{ maxWidth: 200 }}>
                    <label>整批间隔（小时，1～168）</label>
                    <input
                      type="number"
                      min={1}
                      max={168}
                      value={schedulerForm.hours}
                      onChange={(e) => setSchedulerForm((p) => ({ ...p, hours: Number(e.target.value) }))}
                    />
                  </div>
                  <button type="submit" disabled={schedulerSaving}>
                    {schedulerSaving ? "保存中…" : "保存调度配置"}
                  </button>
                </form>
              ) : (
                <p className="muted tiny" style={{ marginTop: 10 }}>
                  只读：需要运营或管理员角色才可修改调度。
                </p>
              )}
              {canManageSettings ? (
                <div style={{ marginTop: 16 }}>
                  <button
                    type="button"
                    disabled={clearIngestBusy}
                    onClick={() => void onClearProductIngest()}
                    style={{
                      border: "1px solid rgba(220, 38, 38, 0.45)",
                      color: "#991b1b",
                      background: "rgba(254, 226, 226, 0.95)",
                      fontWeight: 600,
                      padding: "10px 16px",
                      borderRadius: 10,
                      cursor: clearIngestBusy ? "not-allowed" : "pointer",
                    }}
                  >
                    {clearIngestBusy ? "清空中…" : "清空资源入库数据"}
                  </button>
                  <p className="muted tiny" style={{ marginTop: 8 }}>
                    仅管理员。含数据源合并的领域主题板块清理；用于纠正错误入库后一键清空，随后可主题获取或手动同步以重建分类。
                  </p>
                  <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid rgba(148,163,184,0.2)" }}>
                    <p className="muted tiny" style={{ marginTop: 0, marginBottom: 10, lineHeight: 1.6 }}>
                      同步数据源领域后，对已启用连接器立即整批拉取（绕过最短间隔）。
                    </p>
                    <button
                      type="button"
                      disabled={themeFetchBusy || clearIngestBusy}
                      onClick={() => void onThemeFetch()}
                      style={{
                        border: "1px solid rgba(14, 165, 233, 0.45)",
                        color: "#0c4a6e",
                        background: "rgba(224, 242, 254, 0.95)",
                        fontWeight: 600,
                        padding: "10px 16px",
                        borderRadius: 10,
                        cursor: themeFetchBusy || clearIngestBusy ? "not-allowed" : "pointer",
                      }}
                    >
                      {themeFetchBusy ? "拉取中…" : "拉取全部数据"}
                    </button>
                  </div>
                </div>
              ) : (
                <p className="muted tiny" style={{ marginTop: 12 }}>
                  仅管理员可清空资源入库数据。
                </p>
              )}
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                订阅推送 · 邮件 / 飞书
              </h3>
              <p className="muted tiny" style={{ marginTop: 6, lineHeight: 1.6 }}>
                按<strong>美东（America/New_York）当天</strong>已发布应用/资讯拼一篇摘要，写入{" "}
                <code className="inline-code">newsletter_daily_digests</code>（每天一篇）。
                连接器在<strong>美东当日 23:00–24:00</strong>整批拉取（便于对齐 NewsAPI 等按 US 日切分的数据）；摘要默认定时{" "}
                <strong>23:50</strong> 美东（可在配置中改）。库中已有今日摘要时「立即推送」只发不重生成。
              </p>
              {canOperate ? (
                <form className="newsletter-push-form" onSubmit={onSaveNewsletter}>
                  <div className="push-channels">
                    <section
                      className={`push-channel-card push-channel-card--email${newsletterForm.email_enabled ? " is-on" : ""}`}
                    >
                      <button
                        type="button"
                        className="push-channel-card__head"
                        aria-expanded={newsletterForm.email_enabled}
                        onClick={() =>
                          setNewsletterForm((p) => ({ ...p, email_enabled: !p.email_enabled }))
                        }
                      >
                        <span className="push-channel-card__meta">
                          <span className="push-channel-card__icon" aria-hidden>
                            ✉
                          </span>
                          <span>
                            <span className="push-channel-card__title">邮件推送</span>
                            <span className="push-channel-card__desc">每日简报发给站内订阅用户</span>
                            <span className="push-channel-card__status">
                              {newsletterForm.email_enabled ? "已开启" : "未开启"}
                            </span>
                          </span>
                        </span>
                        <span
                          className="toggle-switch"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={newsletterForm.email_enabled}
                            onChange={(e) =>
                              setNewsletterForm((p) => ({ ...p, email_enabled: e.target.checked }))
                            }
                            aria-label="启用邮件推送"
                          />
                          <span className="toggle-switch__track" aria-hidden />
                        </span>
                      </button>
                      {newsletterForm.email_enabled ? (
                        <div className="push-channel-card__body">
                          <div className="form-field">
                            <label>站点根 URL（退订链接，必填）</label>
                            <input
                              value={newsletterForm.public_site_base_url}
                              onChange={(e) =>
                                setNewsletterForm((p) => ({ ...p, public_site_base_url: e.target.value }))
                              }
                              placeholder="https://www.ai-trends.news"
                              autoComplete="off"
                            />
                          </div>
                          <div className="form-field">
                            <label>SMTP 主机（必填）</label>
                            <input
                              value={newsletterForm.smtp_host}
                              onChange={(e) => setNewsletterForm((p) => ({ ...p, smtp_host: e.target.value }))}
                              placeholder="smtp.example.com"
                              autoComplete="off"
                            />
                          </div>
                          <div className="form-field" style={{ maxWidth: 140 }}>
                            <label>SMTP 端口（必填）</label>
                            <input
                              type="number"
                              min={1}
                              max={65535}
                              value={newsletterForm.smtp_port}
                              onChange={(e) =>
                                setNewsletterForm((p) => ({ ...p, smtp_port: Number(e.target.value) }))
                              }
                            />
                          </div>
                          <div className="form-field">
                            <label>SMTP 用户名（必填）</label>
                            <input
                              value={newsletterForm.smtp_user}
                              onChange={(e) => setNewsletterForm((p) => ({ ...p, smtp_user: e.target.value }))}
                              autoComplete="off"
                            />
                          </div>
                          <div className="form-field">
                            <label>
                              SMTP 密码（必填
                              {newsletterSettings?.has_smtp_password ? "，留空保留已存" : ""}）
                            </label>
                            <input
                              type="password"
                              value={newsletterForm.smtp_password}
                              onChange={(e) =>
                                setNewsletterForm((p) => ({ ...p, smtp_password: e.target.value }))
                              }
                              autoComplete="new-password"
                            />
                          </div>
                          <div className="form-field">
                            <label>发件人 From（必填）</label>
                            <input
                              value={newsletterForm.mail_from}
                              onChange={(e) => setNewsletterForm((p) => ({ ...p, mail_from: e.target.value }))}
                              placeholder="noreply@example.com"
                              autoComplete="off"
                            />
                          </div>
                        </div>
                      ) : null}
                    </section>

                    <section
                      className={`push-channel-card push-channel-card--feishu${newsletterForm.feishu_enabled ? " is-on" : ""}`}
                    >
                      <button
                        type="button"
                        className="push-channel-card__head"
                        aria-expanded={newsletterForm.feishu_enabled}
                        onClick={() =>
                          setNewsletterForm((p) => ({ ...p, feishu_enabled: !p.feishu_enabled }))
                        }
                      >
                        <span className="push-channel-card__meta">
                          <span className="push-channel-card__icon" aria-hidden>
                            💬
                          </span>
                          <span>
                            <span className="push-channel-card__title">飞书群推送</span>
                            <span className="push-channel-card__desc">通过群机器人 Webhook 发送同一份简报</span>
                            <span className="push-channel-card__status">
                              {newsletterForm.feishu_enabled ? "已开启" : "未开启"}
                            </span>
                          </span>
                        </span>
                        <span
                          className="toggle-switch"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <input
                            type="checkbox"
                            checked={newsletterForm.feishu_enabled}
                            onChange={(e) =>
                              setNewsletterForm((p) => ({ ...p, feishu_enabled: e.target.checked }))
                            }
                            aria-label="启用飞书群推送"
                          />
                          <span className="toggle-switch__track" aria-hidden />
                        </span>
                      </button>
                      {newsletterForm.feishu_enabled ? (
                        <div className="push-channel-card__body">
                          <div className="form-field">
                            <label>
                              群机器人 Webhook URL（必填
                              {newsletterSettings?.has_feishu_webhook ? "，留空保留已存" : ""}）
                            </label>
                            <input
                              value={newsletterForm.feishu_webhook_url}
                              onChange={(e) =>
                                setNewsletterForm((p) => ({ ...p, feishu_webhook_url: e.target.value }))
                              }
                              placeholder={
                                newsletterSettings?.has_feishu_webhook
                                  ? `已保存 ${newsletterSettings.feishu_webhook_masked}`
                                  : "https://open.feishu.cn/open-apis/bot/v2/hook/..."
                              }
                              autoComplete="off"
                            />
                          </div>
                        </div>
                      ) : null}
                    </section>
                  </div>
                  <button type="submit" disabled={newsletterSaving}>
                    {newsletterSaving ? "保存中…" : "保存推送配置"}
                  </button>
                </form>
              ) : (
                <p className="muted tiny" style={{ marginTop: 10 }}>
                  只读：需要运营或管理员角色才可修改。
                </p>
              )}
              {digestPreview ? (
                <div className="card" style={{ marginTop: 16, padding: 14, background: "rgba(15,23,42,0.04)" }}>
                  <p className="muted tiny" style={{ margin: "0 0 8px" }}>
                    今日摘要（{digestPreview.digest_date}）· 活跃订阅 {digestPreview.active_subscribers} 人
                    {digestPreview.digest?.article_ids &&
                    typeof digestPreview.digest.article_ids === "object" &&
                    !Array.isArray(digestPreview.digest.article_ids) ? (
                      <>
                        {" "}
                        · 含{" "}
                        {Array.isArray((digestPreview.digest.article_ids as { apps?: unknown }).apps)
                          ? (digestPreview.digest.article_ids as { apps: unknown[] }).apps.length
                          : 0}{" "}
                        应用 /{" "}
                        {Array.isArray((digestPreview.digest.article_ids as { news?: unknown }).news)
                          ? (digestPreview.digest.article_ids as { news: unknown[] }).news.length
                          : 0}{" "}
                        资讯（美东当天）
                      </>
                    ) : null}
                    {digestPreview.digest?.sent_at ? " · 邮件已发" : ""}
                    {digestPreview.digest?.feishu_sent_at ? " · 飞书已推" : ""}
                    {digestPreview.digest?.status ? ` · 状态 ${digestPreview.digest.status}` : ""}
                  </p>
                  {digestPreview.digest?.subject ? (
                    <p style={{ margin: "0 0 6px", fontWeight: 600 }}>{digestPreview.digest.subject}</p>
                  ) : null}
                  {digestPreview.digest?.body_md ? (
                    <pre className="mono tiny" style={{ maxHeight: 200, overflow: "auto", whiteSpace: "pre-wrap" }}>
                      {digestPreview.digest.body_md.slice(0, 2000)}
                      {digestPreview.digest.body_md.length > 2000 ? "\n…" : ""}
                    </pre>
                  ) : (
                    <p className="muted tiny">尚未生成今日摘要。</p>
                  )}
                  {digestPreview.digest?.error_message ? (
                    <p className="err-text tiny">{digestPreview.digest.error_message}</p>
                  ) : null}
                </div>
              ) : null}
              {canOperate ? (
                <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="secondary"
                    disabled={digestRunBusy}
                    title="库中已有今日摘要则只推送；否则先生成再推送"
                    onClick={() => onRunNewsletterDigest({ regenerate: false })}
                  >
                    {digestRunBusy ? "执行中…" : "立即推送"}
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={digestRunBusy}
                    title="按当日已发布内容重新生成摘要并推送"
                    onClick={() => onRunNewsletterDigest({ regenerate: true })}
                  >
                    重新生成并推送
                  </button>
                </div>
              ) : null}
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                DeepSeek / 兼容端点
              </h3>
              <p className="muted tiny" style={{ marginTop: 6 }}>
                默认 <code className="inline-code">https://api.deepseek.com/v1</code> 与{" "}
                <code className="inline-code">deepseek-chat</code>。连接器同步依赖 LLM：请在本页保存 Key（写入 <code className="inline-code">product_settings_kv.llm</code>）；<code className="inline-code">backend/.env</code> 里的 <code className="inline-code">AITRENDS_LLM_*</code> 可继续保留，库内为空时启动会自动迁入。
              </p>
              <form className="create-user-form" onSubmit={onSaveLlm} style={{ marginTop: 16 }}>
                <div className="form-field">
                  <label>提供商标识</label>
                  <input
                    value={llmForm.provider}
                    onChange={(e) => setLlmForm((p) => ({ ...p, provider: e.target.value }))}
                    disabled={!canOperate}
                    autoComplete="off"
                  />
                </div>
                <div className="form-field">
                  <label>Base URL（须含 /v1 前缀）</label>
                  <input
                    value={llmForm.base_url}
                    onChange={(e) => setLlmForm((p) => ({ ...p, base_url: e.target.value }))}
                    disabled={!canOperate}
                    placeholder="https://api.deepseek.com/v1"
                    autoComplete="off"
                  />
                </div>
                <div className="form-field">
                  <label>模型名</label>
                  <input
                    value={llmForm.model}
                    onChange={(e) => setLlmForm((p) => ({ ...p, model: e.target.value }))}
                    disabled={!canOperate}
                    placeholder="deepseek-chat"
                    autoComplete="off"
                  />
                </div>
                <div className="form-field">
                  <label>API Key（Bearer）</label>
                  <input
                    type="password"
                    value={llmForm.api_key}
                    onChange={(e) => setLlmForm((p) => ({ ...p, api_key: e.target.value }))}
                    disabled={!canOperate}
                    placeholder={llmSettings?.has_api_key ? "已保存 · 输入新值可覆盖" : "sk-…"}
                    autoComplete="new-password"
                  />
                  <p className="muted tiny" style={{ marginTop: 6 }}>
                    当前掩码：<strong style={{ color: "#312e81" }}>{llmSettings?.api_key_masked || "—"}</strong>
                  </p>
                </div>
                <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                  <button type="submit" disabled={!canOperate || llmSaving}>
                    {llmSaving ? "保存中…" : "保存配置"}
                  </button>
                  {!canOperate ? (
                    <span className="muted tiny">只读：需要运营或管理员角色才可保存。</span>
                  ) : null}
                </div>
              </form>
            </div>
          </section>
        ) : null}

        {tab === "software" ? (
          <section className="settings-stack">
            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                上传应用安装包
              </h3>
              <p className="muted tiny" style={{ marginTop: 6 }}>
                写入 <code className="inline-code">data/software_uploads/</code> 并发布；公开站「软件下载」将显示<strong>本地下载</strong>（非商店跳转）。
                命令行等价：<code className="inline-code">py -3.12 scripts/upload_software_app.py --file ...</code>
              </p>
              <form className="create-user-form" style={{ marginTop: 12 }} onSubmit={onUploadSoftware}>
                <div className="form-field">
                  <label>安装包文件</label>
                  <input
                    type="file"
                    disabled={!canOperate || swBusy}
                    onChange={(e) => setSwFile(e.target.files?.[0] ?? null)}
                  />
                </div>
                <div className="form-field">
                  <label>应用名称</label>
                  <input value={swTitle} disabled={!canOperate || swBusy} onChange={(e) => setSwTitle(e.target.value)} />
                </div>
                <div className="form-field">
                  <label>摘要</label>
                  <textarea value={swSummary} disabled={!canOperate || swBusy} rows={2} onChange={(e) => setSwSummary(e.target.value)} />
                </div>
                <div className="form-field">
                  <label>平台</label>
                  <select value={swPlatform} disabled={!canOperate || swBusy} onChange={(e) => setSwPlatform(e.target.value as "ios" | "android")}>
                    <option value="android">Android</option>
                    <option value="ios">iOS</option>
                  </select>
                </div>
                <div className="form-field">
                  <label>分类 slug</label>
                  <input value={swCatSlug} disabled={!canOperate || swBusy} onChange={(e) => setSwCatSlug(e.target.value)} placeholder="general" />
                </div>
                <div className="form-field">
                  <label>分类展示名</label>
                  <input value={swCatLabel} disabled={!canOperate || swBusy} onChange={(e) => setSwCatLabel(e.target.value)} placeholder="与 slug 一致可留空" />
                </div>
                <button type="submit" disabled={!canOperate || swBusy}>
                  {swBusy ? "上传中…" : "上传并发布"}
                </button>
                {!canOperate ? <p className="muted tiny">只读账号无法上传。</p> : null}
              </form>
            </div>

            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                已发布包（最近 {swPackages.length} 条）
              </h3>
              <div style={{ overflowX: "auto", marginTop: 10 }}>
                <table className="data-table" style={{ width: "100%", fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>标题</th>
                      <th>平台</th>
                      <th>分类</th>
                      <th>直链包</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {swPackages.map((r) => (
                      <tr key={r.id}>
                        <td>{r.id}</td>
                        <td>{r.title}</td>
                        <td>{r.platform}</td>
                        <td>{r.category_label || r.category_slug}</td>
                        <td>{r.has_artifact ? "是" : "否"}</td>
                        <td>
                          {canOperate ? (
                            <button type="button" className="btn-ghost" onClick={() => void onDeleteSoftwareRow(r.id)}>
                              删除
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        ) : null}

        {tab === "logs" ? (
          <section className="settings-stack">
            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                同步诊断日志
              </h3>
              <p className="muted tiny" style={{ marginTop: 6, lineHeight: 1.65 }}>
                仅记录每批/每连接器的起止，以及告警与失败（如 HTTP 失败、LLM 未配置、跳过入库原因等），便于排查。拉取完成后会自动打开本页；报错时请选中对应{" "}
                <strong>run_id</strong> 后点「复制本批日志」。
                {diagPipelineVersion ? (
                  <>
                    {" "}
                    当前诊断版本 <code className="inline-code">diag_v={diagPipelineVersion}</code>
                  </>
                ) : null}
              </p>
              <div className="row wrap" style={{ marginTop: 12, gap: 8, alignItems: "flex-end" }}>
                <div className="form-field" style={{ minWidth: 200, flex: 1 }}>
                  <label>批次 run_id</label>
                  <select
                    value={diagRunFilter}
                    onChange={(e) => {
                      const v = e.target.value;
                      setDiagRunFilter(v);
                      void loadDiagnosticLogs(v || undefined);
                    }}
                  >
                    <option value="">最近全部（最多 800 行）</option>
                    {diagRunIds.map((rid) => (
                      <option key={rid} value={rid}>
                        {rid}
                      </option>
                    ))}
                  </select>
                </div>
                <button type="button" onClick={() => void loadDiagnosticLogs(diagRunFilter || undefined)} disabled={diagLoading}>
                  {diagLoading ? "刷新中…" : "刷新"}
                </button>
                <button type="button" onClick={() => void copyDiagnosticLogsToClipboard()} disabled={!diagLogs.length}>
                  {diagCopyOk ? "已复制" : diagRunFilter ? "复制本批日志" : "复制日志"}
                </button>
                {canManageSettings ? (
                  <button
                    type="button"
                    onClick={() => {
                      if (!window.confirm("清空全部同步诊断日志？")) return;
                      void adminApi.clearSyncDiagnosticLogs().then(() => loadDiagnosticLogs());
                    }}
                  >
                    清空日志
                  </button>
                ) : null}
              </div>
              <pre
                className="mono"
                style={{
                  marginTop: 14,
                  maxHeight: "min(70vh, 640px)",
                  overflow: "auto",
                  padding: 12,
                  fontSize: 11,
                  lineHeight: 1.5,
                  background: "rgba(15,23,42,0.04)",
                  borderRadius: 8,
                  border: "1px solid rgba(148,163,184,0.25)",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {diagLoading
                  ? "加载中…"
                  : diagLogs.length
                    ? diagLogs
                        .map((r) => {
                          const head = `[${r.created_at ?? ""}] [${r.level}] [${r.step}]${r.connector_id != null ? ` #${r.connector_id}` : ""}${r.source_key ? ` ${r.source_key}` : ""}`;
                          return `${head}\n  ${r.message ?? ""}`;
                        })
                        .join("\n\n")
                    : "（暂无日志，请先点击「拉取全部数据」）"}
              </pre>
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
                  <h3 className="settings-title" style={{ marginTop: 0 }}>
                    运行参数（存库，替代多数 AITRENDS_* 环境项）
                  </h3>
                  <p className="muted tiny" style={{ marginTop: 6, lineHeight: 1.65 }}>
                    {runtimeView?.secrets_note ?? "加载中…"}
                  </p>
                  <p className="muted tiny" style={{ marginTop: 8 }}>
                    演示数据种子当前是否写入：<strong style={{ color: "#312e81" }}>{runtimeView?.demo_seed_effective ? "是" : "否"}</strong>
                    （未勾选「强制开启」时由 app_env 与 AITRENDS_ENABLE_DEMO_SEED 推断）
                  </p>
                  <form className="create-user-form" onSubmit={onSaveRuntime} style={{ marginTop: 14 }}>
                    <div className="form-field">
                      <label>CORS 允许来源（英文逗号分隔，须含协议与端口）</label>
                      <textarea
                        rows={3}
                        value={runtimeForm.cors_origins_csv}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, cors_origins_csv: e.target.value }))}
                        style={{ width: "100%", maxWidth: 720 }}
                      />
                    </div>
                    <div className="form-field" style={{ maxWidth: 200 }}>
                      <label>JWT 有效期（秒）</label>
                      <input
                        type="number"
                        min={60}
                        max={864000}
                        value={runtimeForm.jwt_ttl_seconds}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, jwt_ttl_seconds: Number(e.target.value) }))}
                      />
                    </div>
                    <div className="form-field" style={{ maxWidth: 200 }}>
                      <label>HMAC 时间戳允许偏差（秒）</label>
                      <input
                        type="number"
                        min={30}
                        max={3600}
                        value={runtimeForm.allowed_skew_seconds}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, allowed_skew_seconds: Number(e.target.value) }))}
                      />
                    </div>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={runtimeForm.require_https}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, require_https: e.target.checked }))}
                      />
                      要求 HTTPS（反代需正确传递 X-Forwarded-Proto）
                    </label>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={runtimeForm.allow_insecure_localhost}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, allow_insecure_localhost: e.target.checked }))}
                      />
                      本机 / testserver 可放行 HTTP
                    </label>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={runtimeForm.admin_cookie_secure}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, admin_cookie_secure: e.target.checked }))}
                      />
                      管理端 Cookie Secure
                    </label>
                    <div className="form-field" style={{ maxWidth: 280 }}>
                      <label>运行模式 app_env</label>
                      <select
                        value={runtimeForm.app_env}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, app_env: e.target.value }))}
                      >
                        <option value="dev">dev</option>
                        <option value="local">local</option>
                        <option value="staging">staging</option>
                        <option value="production">production</option>
                      </select>
                    </div>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={runtimeForm.force_demo_seed}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, force_demo_seed: e.target.checked }))}
                      />
                      强制开启演示种子写入（关闭则恢复自动推断）
                    </label>
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={runtimeForm.legacy_admin_enabled}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, legacy_admin_enabled: e.target.checked }))}
                      />
                      启用旧版 X-Admin-Token 内部接口
                    </label>
                    <div className="form-field" style={{ maxWidth: 480 }}>
                      <label>对外版本展示文案（可选，覆盖 AITRENDS_APP_RELEASE）</label>
                      <input
                        value={runtimeForm.app_release_label}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, app_release_label: e.target.value }))}
                        placeholder="留空则用环境变量或库内已保存的版本标签"
                      />
                    </div>
                    <div className="form-field" style={{ maxWidth: 360 }}>
                      <label>热门快照默认 llm_model 标签</label>
                      <input
                        value={runtimeForm.hot_llm_model}
                        onChange={(e) => setRuntimeForm((p) => ({ ...p, hot_llm_model: e.target.value }))}
                      />
                    </div>
                    <button type="submit" disabled={runtimeSaving}>
                      {runtimeSaving ? "保存中…" : "保存运行参数"}
                    </button>
                  </form>
                </div>

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
                              登录名：<strong style={{ color: "#1e1b4b" }}>{cur.username}</strong>
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
    </>
  );
}
