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
type TabKey = "overview" | "queries" | "sources" | "ai" | "software" | "settings";

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
  env_fallback: boolean;
  pipeline: Array<{ id: string; label: string }>;
};

type SchedulerSettingsView = {
  connector_scheduler_enabled: boolean;
  connector_sync_interval_hours: number;
  last_connector_batch_at: string | null;
  gate_interval_minutes: number;
  env_default_hours_hint: number;
};

type SourcePresetRow = {
  source: string;
  label: string;
  api_base: string;
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

  const [llmSettings, setLlmSettings] = useState<LlmSettingsView | null>(null);
  const [llmForm, setLlmForm] = useState({ provider: "deepseek", base_url: "", model: "", api_key: "" });
  const [llmSaving, setLlmSaving] = useState(false);
  const [schedulerSettings, setSchedulerSettings] = useState<SchedulerSettingsView | null>(null);
  const [schedulerForm, setSchedulerForm] = useState({ enabled: true, hours: 6 });
  const [schedulerSaving, setSchedulerSaving] = useState(false);
  const [clearIngestBusy, setClearIngestBusy] = useState(false);
  const [themeFetchBusy, setThemeFetchBusy] = useState(false);
  const [themeKeyword, setThemeKeyword] = useState("");
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
      const [llm, sched] = await Promise.all([adminApi.getLlmSettings(), adminApi.getSchedulerSettings()]);
      setLlmSettings(llm);
      setSchedulerSettings(sched);
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

  async function onSaveSource(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await adminApi.saveSource({
        source: sourceForm.source,
        enabled: sourceForm.enabled,
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

  async function onThemeFetch() {
    if (!canManageSettings) return;
    if (
      !window.confirm(
        "将先根据「数据源」中的领域标签刷新行业/板块结构，再对所有已启用的连接器立即执行一次同步（不受单次最短间隔限制），会访问外网。确定继续？",
      )
    )
      return;
    setThemeFetchBusy(true);
    setErr("");
    try {
      const kw = themeKeyword.trim();
      const r = await adminApi.themeFetchProductData(kw ? { theme: kw } : {});
      const lines = (r.details || [])
        .map((d) => {
          const err = d.error ? ` 错误: ${d.error}` : "";
          return `${d.name} (#${d.connector_id}) HTTP ${d.http_status ?? "—"} 文章+${d.articles_created ?? 0}${err}`;
        })
        .join("\n");
      window.alert(
        `主题获取完成。\n领域结构已同步；已启用连接器共 ${r.connectors_total} 个，成功 ${r.ok}，失败 ${r.fail}。${
          r.theme_applied_to_url ? `\n本次已在未自带搜索参数的 URL 上补充 q=${kw}。` : ""
        }\n\n${lines || "（无已启用连接器）"}`,
      );
      setThemeKeyword("");
      await loadAdminData();
    } catch (error) {
      setErr(friendlyErr(error instanceof Error ? error.message : "theme fetch failed"));
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
                  <h4 style={{ margin: "0 0 8px", fontSize: 15, fontWeight: 600 }}>主题获取数据</h4>
                  <p className="muted tiny" style={{ margin: "0 0 10px", lineHeight: 1.6 }}>
                    先同步数据源领域到行业/板块，再对<strong>已启用</strong>连接器整批立即拉取（与定时任务同逻辑，且绕过单连接器最短间隔）。可选填关键词：若连接器 URL
                    尚未带搜索参数，会在本次请求中追加 <code className="inline-code">q</code>（如 NewsAPI 等）。
                  </p>
                  <div className="form-field" style={{ maxWidth: 420, marginBottom: 10 }}>
                    <label htmlFor="theme-fetch-keyword">可选主题 / 搜索词</label>
                    <input
                      id="theme-fetch-keyword"
                      type="text"
                      value={themeKeyword}
                      onChange={(e) => setThemeKeyword(e.target.value)}
                      placeholder="留空则仅按数据源领域拉取"
                      disabled={themeFetchBusy || clearIngestBusy}
                      maxLength={200}
                      autoComplete="off"
                    />
                  </div>
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
                    {themeFetchBusy ? "拉取中…" : "主题获取数据"}
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
              <div className="row between" style={{ flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
                <div>
                  <h3 style={{ margin: 0 }}>预设模板</h3>
                  <p className="muted tiny" style={{ margin: "8px 0 0" }}>
                    与后端内置站点列表同步。点击某张卡片将把标识、API Base、主题标签等填入下方表单；补全 API Key 后保存即可。已配置的标识会标为「已有」。
                    实际拉取间隔不在此页配置：请到「AI 资讯与数据」中的<strong>定时同步</strong>设置整批间隔；连接器绑定本页数据源标识后才会按该调度参与拉取。
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
                            <dt>拉取节奏</dt>
                            <dd className="muted tiny">统一定时（「AI 资讯与数据」页配置间隔）</dd>
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
                            <dt>拉取节奏</dt>
                            <dd className="muted tiny">统一定时（「AI 资讯与数据」页配置间隔）</dd>
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
                    全文重写（分类 + 多 tab）→ 展示指纹去重 → 发布；未配置模型则不入库。密钥可仅存库内，或在服务端{" "}
                    <code className="inline-code">AITRENDS_LLM_API_KEY</code>（默认 DeepSeek 端点）；接口仅返回脱敏掩码。
                  </p>
                </div>
                <div className="ai-hero-metrics">
                  <div>
                    <span className="ai-metric-label">密钥状态</span>
                    <span className="ai-metric-value">{llmSettings?.has_api_key ? "已配置" : "未配置"}</span>
                  </div>
                  <div>
                    <span className="ai-metric-label">环境变量回退</span>
                    <span className="ai-metric-value">{llmSettings?.env_fallback ? "AITRENDS_LLM_* 可用" : "无"}</span>
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
                进程内每 <strong>{schedulerSettings?.gate_interval_minutes ?? 15} 分钟</strong>检查一次；若距上次<strong>整批成功</strong>已超过下方配置的间隔，则对<strong>所有已启用</strong>连接器执行同步（与手动「同步」同逻辑，且<strong>不受</strong>单连接器{" "}
                <code className="inline-code">min_interval_seconds</code> 限制，避免定时任务被 429 静默跳过）。间隔与开关保存在库表{" "}
                <code className="inline-code">product_settings_kv.scheduler</code>；新建库时默认小时数可来自环境变量{" "}
                <code className="inline-code">AITRENDS_CONNECTOR_SYNC_INTERVAL_HOURS</code>（仅首次建行参考）。整批跑完后会根据「数据源」中的领域主题刷新前台行业/板块结构。
              </p>
              {schedulerSettings ? (
                <p className="muted tiny" style={{ marginTop: 8 }}>
                  上次整批成功时间：<strong style={{ color: "#312e81" }}>{schedulerSettings.last_connector_batch_at || "—（尚未成功跑过一批）"}</strong>
                  {" · "}
                  环境默认小时提示：{schedulerSettings.env_default_hours_hint}
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
                    <h4 className="settings-title" style={{ marginTop: 0, marginBottom: 8, fontSize: 15 }}>
                      主题获取数据
                    </h4>
                    <p className="muted tiny" style={{ marginTop: 0, lineHeight: 1.6 }}>
                      同步数据源领域 → 已启用连接器立即整批拉取；可选关键词在无搜索参数时写入 URL 的 <code className="inline-code">q</code>。
                    </p>
                    <div className="form-field" style={{ maxWidth: 400, marginTop: 10 }}>
                      <label htmlFor="theme-fetch-keyword-ai">可选主题 / 搜索词</label>
                      <input
                        id="theme-fetch-keyword-ai"
                        type="text"
                        value={themeKeyword}
                        onChange={(e) => setThemeKeyword(e.target.value)}
                        placeholder="留空则仅按数据源领域拉取"
                        disabled={themeFetchBusy || clearIngestBusy}
                        maxLength={200}
                        autoComplete="off"
                      />
                    </div>
                    <button
                      type="button"
                      disabled={themeFetchBusy || clearIngestBusy}
                      onClick={() => void onThemeFetch()}
                      style={{
                        marginTop: 10,
                        border: "1px solid rgba(14, 165, 233, 0.45)",
                        color: "#0c4a6e",
                        background: "rgba(224, 242, 254, 0.95)",
                        fontWeight: 600,
                        padding: "10px 16px",
                        borderRadius: 10,
                        cursor: themeFetchBusy || clearIngestBusy ? "not-allowed" : "pointer",
                      }}
                    >
                      {themeFetchBusy ? "拉取中…" : "主题获取数据"}
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
                DeepSeek / 兼容端点
              </h3>
              <p className="muted tiny" style={{ marginTop: 6 }}>
                默认 <code className="inline-code">https://api.deepseek.com/v1</code> 与{" "}
                <code className="inline-code">deepseek-chat</code>。连接器同步依赖 LLM：可在本页保存 Key，或在{" "}
                <code className="inline-code">backend/.env</code> 设置 <code className="inline-code">AITRENDS_LLM_API_KEY</code>
                （可选 <code className="inline-code">AITRENDS_LLM_BASE_URL</code> / <code className="inline-code">AITRENDS_LLM_MODEL</code>
                ）；优先级为<strong>库内已存 Key</strong> → 环境变量。
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
                        placeholder="留空则用环境变量 / pyproject 版本"
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
