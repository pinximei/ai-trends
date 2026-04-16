from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, ensure_schema_compatibility, get_db, get_db_runtime_info
from .admin_auth import (
    audit,
    ensure_default_admin,
    get_session,
    hash_password,
    verify_password,
    login as admin_login,
    logout as admin_logout,
    require_role,
)
from .data_api_service import DataApiService
from .models import AdminSession, AdminSourceConfig, AdminUser, AuditLog, EvidenceSignal, PipelineRun, RemovalRequest, Trend
from .schemas import (
    AdminLoginRequest,
    AdminChangePasswordRequest,
    AdminSettingsUpdate,
    AdminSourceConfigUpsert,
    SignalOpsUpdate,
    TrendOpsUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    InternalRunRequest,
    RemovalRequestCreate,
)
from .security import AUTH_BOOTSTRAP_KEY, enforce_https, issue_access_token, verify_bearer_from_request, verify_hmac_signature
from .services import clear_business_data, create_removal_ticket, envelope, get_or_create_run, seed_demo_bundle, seed_if_empty

app = FastAPI(title="Agent Trend Platform")

root = Path(__file__).resolve().parent.parent

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_LANGS = {"zh", "en"}
DEFAULT_LANG = "zh"
VALID_PERIODS = {"day", "week", "month", "quarter", "year"}
I18N = {
    "nav.dashboard": {"zh": "仪表盘", "en": "Dashboard"},
    "nav.inspirations": {"zh": "灵感信号", "en": "Inspirations"},
    "nav.trends": {"zh": "趋势", "en": "Trends"},
    "nav.categories": {"zh": "分类", "en": "Categories"},
    "nav.new_signals": {"zh": "新信号", "en": "New Signals"},
    "nav.methodology": {"zh": "方法论", "en": "Methodology"},
    "nav.data_sources": {"zh": "数据来源", "en": "Data Sources"},
    "nav.privacy": {"zh": "隐私", "en": "Privacy"},
    "nav.terms": {"zh": "条款", "en": "Terms"},
    "nav.removal": {"zh": "删除申请", "en": "Removal"},
    "nav.admin": {"zh": "管理台", "en": "Admin"},
    "lang.zh": {"zh": "中文", "en": "中文"},
    "lang.en": {"zh": "English", "en": "English"},
    "home.title": {"zh": "Agent 趋势仪表盘", "en": "Agent Trend Dashboard"},
    "home.subtitle": {
        "zh": "公共生态趋势估计，不构成采购或合规结论。",
        "en": "Public ecosystem trend estimation. Not procurement or compliance conclusion.",
    },
    "home.top_trends": {"zh": "热门趋势", "en": "Top Trends"},
    "kpi.active_use_cases": {"zh": "活跃用例", "en": "Active Use Cases"},
    "kpi.new_apps": {"zh": "新增应用", "en": "New Apps"},
    "kpi.emerging_trends": {"zh": "新兴趋势", "en": "Emerging Trends"},
    "kpi.updated_at": {"zh": "更新时间", "en": "Updated At"},
    "common.trend": {"zh": "趋势", "en": "Trend"},
    "common.score": {"zh": "分数", "en": "Score"},
    "common.confidence": {"zh": "置信度", "en": "Confidence"},
    "common.sample": {"zh": "样本量", "en": "Sample"},
    "common.lifecycle": {"zh": "生命周期", "en": "Lifecycle"},
    "trends.subtitle": {"zh": "点击趋势查看时间线和证据链。", "en": "Click a trend to inspect timeline and evidence chain."},
    "inspirations.title": {"zh": "灵感信号", "en": "Inspirations"},
    "inspirations.subtitle": {
        "zh": "发现可落地的信号，并下钻到原始证据。",
        "en": "Explore practical signals and drill down to raw evidence.",
    },
    "trend.detail": {"zh": "趋势详情", "en": "Trend Detail"},
    "trend.timeline": {"zh": "时间线", "en": "Timeline"},
    "trend.next_step": {"zh": "建议下一步", "en": "Suggested Next Step"},
    "trend.next_step_text": {
        "zh": "建议：定义一个假设，进行 2 周试点，跟踪 1 个成功指标，并记录风险后再扩大。",
        "en": "Next Step: define one hypothesis, run a 2-week pilot, track one success metric, and record risks before scaling.",
    },
    "evidence.detail": {"zh": "证据详情", "en": "Evidence Detail"},
    "common.source": {"zh": "来源", "en": "Source"},
    "common.url": {"zh": "链接", "en": "URL"},
    "common.trace": {"zh": "追溯链", "en": "Trace"},
    "categories.subtitle": {"zh": "来自开源生态信号的分类分布。", "en": "Category distribution from open ecosystem signals."},
    "methodology.tip1": {"zh": "采取行动前必须核验证据。", "en": "Always review evidence before action."},
    "methodology.tip2": {"zh": "趋势结果用于提出假设，不是最终决策。", "en": "Use trend output as hypothesis input, not final decision."},
    "methodology.tip3": {"zh": "在强监管行业，需要额外合规审查。", "en": "For regulated domains, do an additional compliance review."},
    "methodology.summary": {
        "zh": "基于公开生态数据的趋势估计，非采购或合规结论。",
        "en": "Public ecosystem trend estimation; not procurement or compliance conclusion.",
    },
    "admin.title": {"zh": "管理台", "en": "Admin"},
    "admin.subtitle": {
        "zh": "用于管理数据源、分类体系、审核队列和合规工单。",
        "en": "Admin control center for sources, taxonomy, review queue, and compliance actions.",
    },
    "admin.review_queue": {"zh": "审核队列", "en": "Review queue"},
    "admin.taxonomy": {"zh": "分类体系", "en": "Taxonomy"},
    "admin.sources": {"zh": "数据源", "en": "Sources"},
    "admin.compliance": {"zh": "合规", "en": "Compliance"},
    "admin.compliance.subtitle": {
        "zh": "处理删除与纠错请求，并保留审计追踪。",
        "en": "Resolve removal and correction requests with audit trace.",
    },
    "common.ticket": {"zh": "工单", "en": "Ticket"},
    "common.status": {"zh": "状态", "en": "Status"},
    "common.action": {"zh": "操作", "en": "Action"},
    "common.resolve": {"zh": "处理", "en": "Resolve"},
    "common.done": {"zh": "完成", "en": "Done"},
    "admin.review.desc": {"zh": "审核低置信度事件与合规请求。", "en": "Review low-confidence events and compliance requests."},
    "admin.taxonomy.desc": {"zh": "管理趋势分类版本。", "en": "Manage trend taxonomy versions."},
    "admin.sources.desc": {"zh": "管理数据源开关和调度频率。", "en": "Manage source switches and schedule frequencies."},
    "signals.new.desc": {"zh": "用于下一轮迭代机会识别的新信号列表。", "en": "Emerging signal list for next iteration opportunities."},
    "legal.privacy.desc": {"zh": "运营方：AISoul 项目运营者。联系方式：legal@aisoul.local", "en": "Operator: AISoul Project Operator. Contact: legal@aisoul.local"},
    "legal.terms.desc": {
        "zh": "适用法律：运营方注册地法律。争议解决：注册地有管辖权法院。",
        "en": "Applicable law: operator registration jurisdiction. Dispute: competent court of that jurisdiction.",
    },
    "legal.sources.desc": {
        "zh": "GitHub、Hugging Face、Hacker News、Product Hunt、Reddit、MCP/Skills 索引。",
        "en": "GitHub, Hugging Face, Hacker News, Product Hunt, Reddit, MCP/Skills indexes.",
    },
    "legal.removal.desc": {"zh": "通过 API 提交：POST /api/v1/compliance/removal-requests", "en": "Submit through API: POST /api/v1/compliance/removal-requests"},
    "footer.tagline": {"zh": "AISoul · Agent 趋势与灵感信号", "en": "AISoul · agent trends & inspiration signals"},
    "api.ok": {"zh": "成功", "en": "ok"},
}

ADMIN_TOKEN = os.getenv("AISOU_ADMIN_TOKEN", "")
LEGACY_ADMIN_ENABLED = os.getenv("AISOU_LEGACY_ADMIN_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


def resolve_lang(request: Request) -> str:
    lang = request.query_params.get("lang") or request.cookies.get("lang") or DEFAULT_LANG
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def tr(key: str, lang: str) -> str:
    item = I18N.get(key)
    if not item:
        return key
    return item.get(lang) or item.get(DEFAULT_LANG) or key


def api_envelope(request: Request, data, message_key: str = "api.ok"):
    return envelope(data, message=tr(message_key, resolve_lang(request)))


def _token_ok(request: Request, token: str) -> bool:
    auth = request.headers.get("authorization") or ""
    if auth.startswith("Bearer ") and auth.removeprefix("Bearer ").strip() == token:
        return True
    if request.headers.get("x-admin-token") == token:
        return True
    return False


def require_admin(request: Request):
    if not LEGACY_ADMIN_ENABLED:
        raise HTTPException(status_code=410, detail="legacy admin api disabled")
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="legacy admin token missing")
    if _token_ok(request, ADMIN_TOKEN):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


def _mask_key(raw_key: str) -> str:
    cleaned = (raw_key or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def _validate_password_policy(db: Session, raw_password: str) -> None:
    settings = DataApiService(db).get_settings()
    if len(raw_password or "") < settings["password_min_length"]:
        raise HTTPException(status_code=400, detail=f"password too short, min={settings['password_min_length']}")


@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    enforce_https(request)
    path = request.url.path
    protected_signed = path.startswith("/api/v1/") or path.startswith("/api/public/v1/")
    allow_unauth = {"/api/v1/auth/token", "/api/admin/v1/auth/login", "/api/admin/v1/auth/logout", "/api/admin/v1/auth/me"}
    if request.method == "OPTIONS":
        return await call_next(request)
    if protected_signed and path not in allow_unauth:
        body = await request.body()
        verify_hmac_signature(request, body)
        verify_bearer_from_request(request)
    return await call_next(request)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    db = next(get_db())
    seed_demo_bundle(db)
    ensure_default_admin(db)
    db.close()


@app.get("/api/v1/dashboard/summary")
def dashboard_summary(request: Request, db: Session = Depends(get_db)):
    return api_envelope(request, DataApiService(db).get_dashboard_summary())


@app.get("/api/public/v1/dashboard/summary")
def dashboard_summary_public(request: Request, db: Session = Depends(get_db)):
    return api_envelope(request, DataApiService(db).get_dashboard_summary())


@app.post("/api/v1/auth/token")
def issue_token(request: Request):
    bootstrap = request.headers.get("x-bootstrap-key") or request.query_params.get("bootstrap_key") or ""
    if bootstrap != AUTH_BOOTSTRAP_KEY:
        raise HTTPException(status_code=401, detail="unauthorized")
    client_id = request.headers.get("x-client-id", "web-client")
    token = issue_access_token(client_id=client_id)
    return api_envelope(request, {"access_token": token, "token_type": "Bearer"})


@app.post("/api/admin/v1/auth/login")
def admin_auth_login(request: Request, response: Response, payload: AdminLoginRequest, db: Session = Depends(get_db)):
    data = admin_login(db, response, payload.username.strip(), payload.password)
    audit(db, actor=data["username"], action="auth.login", detail="admin login")
    return api_envelope(request, data)


@app.post("/api/admin/v1/auth/logout")
def admin_auth_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_actor = "anonymous"
    try:
        session = get_session(db, request)
        session_actor = session.username
    except HTTPException:
        pass
    result = admin_logout(db, request, response)
    audit(db, actor=session_actor, action="auth.logout", detail="admin logout")
    return api_envelope(request, result)


@app.get("/api/admin/v1/auth/me")
def admin_auth_me(request: Request, db: Session = Depends(get_db)):
    session = get_session(db, request)
    pw_min = DataApiService(db).get_settings()["password_min_length"]
    return api_envelope(
        request,
        {
            "username": session.username,
            "role": session.role,
            "expires_at": session.expires_at.isoformat(),
            "password_min_length": pw_min,
        },
    )


@app.post("/api/admin/v1/auth/change-password")
def admin_auth_change_password(
    request: Request,
    payload: AdminChangePasswordRequest,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    user = db.scalar(select(AdminUser).where(AdminUser.username == session.username))
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    _validate_password_policy(db, payload.new_password)
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="old password incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="auth.change_password")
    return api_envelope(request, {"ok": True})


@app.get("/api/v1/trends")
def trends(request: Request, period: str = "week", db: Session = Depends(get_db)):
    try:
        data = DataApiService(db).get_trends(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_envelope(request, data)


@app.get("/api/public/v1/trends")
def trends_public(request: Request, period: str = "week", db: Session = Depends(get_db)):
    return trends(request, period, db)


@app.get("/api/v1/trends/{trend_key}")
def trend_detail(request: Request, trend_key: str, db: Session = Depends(get_db)):
    data = DataApiService(db).get_trend_detail(trend_key)
    if not data:
        raise HTTPException(status_code=404, detail="trend not found")
    return api_envelope(request, data)


@app.get("/api/public/v1/trends/{trend_key}")
def trend_detail_public(request: Request, trend_key: str, db: Session = Depends(get_db)):
    return trend_detail(request, trend_key, db)


@app.get("/api/v1/trends/{trend_key}/timeline")
def trend_timeline(request: Request, trend_key: str, period: str = "week"):
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=400, detail="invalid period")
    seed = {
        "workflow-automation-agent": 78.2,
        "customer-support-agent": 73.4,
        "multimodal-content-agent": 69.1,
    }.get(trend_key, 56.0)
    step_days = {"day": 1, "week": 7, "month": 30, "quarter": 91, "year": 365}[period]
    span = {"day": 7, "week": 8, "month": 6, "quarter": 5, "year": 5}[period]
    points = []
    now = datetime.now(timezone.utc).date()
    for i in range(span):
        index_from_recent = span - i - 1
        date = now - timedelta(days=index_from_recent * step_days)
        score = max(35.0, round(seed - index_from_recent * 2.1, 1))
        points.append({"period_start": str(date), "score": score})
    return api_envelope(
        request,
        {
            "trend_key": trend_key,
            "period": period,
            "points": points,
        },
    )


@app.get("/api/v1/inspirations")
def inspirations(request: Request, period: str = "week", db: Session = Depends(get_db)):
    try:
        data = DataApiService(db).get_inspirations(period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_envelope(request, data)


@app.get("/api/public/v1/inspirations")
def inspirations_public(request: Request, period: str = "week", db: Session = Depends(get_db)):
    return inspirations(request, period, db)


@app.get("/api/v1/content/briefing")
def content_briefing(request: Request, period: str = "week", db: Session = Depends(get_db)):
    try:
        data = DataApiService(db).get_content_briefing(period=period, lang=resolve_lang(request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_envelope(request, data)


@app.get("/api/public/v1/content/briefing")
def content_briefing_public(request: Request, period: str = "week", db: Session = Depends(get_db)):
    return content_briefing(request, period, db)


@app.get("/api/v1/evidences/{signal_id}")
def evidence(request: Request, signal_id: str, db: Session = Depends(get_db)):
    data = DataApiService(db).get_evidence(signal_id)
    if not data:
        raise HTTPException(status_code=404, detail="evidence not found")
    return api_envelope(request, data)


@app.get("/api/public/v1/evidences/{signal_id}")
def evidence_public(request: Request, signal_id: str, db: Session = Depends(get_db)):
    return evidence(request, signal_id, db)


@app.get("/api/v1/categories")
def categories(request: Request):
    return api_envelope(request, {"items": ["code-agent", "workflow", "customer-support", "multimodal-content", "mcp", "skills"]})


@app.get("/api/v1/meta/methodology")
def methodology(request: Request):
    return api_envelope(
        request,
        {
            "summary": tr("methodology.summary", resolve_lang(request)),
            "must_show": ["data_source", "statistical_scope", "updated_at", "sample_size", "confidence_hint"],
        },
    )


@app.get("/api/v1/meta/taxonomy")
def taxonomy(request: Request):
    return api_envelope(request, {"version": "v1", "use_cases": ["workflow-automation-agent", "coding-agent"]})


@app.get("/api/v1/signals/new")
def signals_new(request: Request):
    return api_envelope(request, {"items": [{"signal_id": "sig_001", "newness_score": 0.73}]})


@app.get("/api/v1/lens/industry-region")
def industry_region_lens(request: Request):
    return api_envelope(
        request,
        {"items": [{"industry": "ecommerce", "region": "global", "trend_key": "workflow-automation-agent"}]},
    )


@app.get("/api/v1/subscriptions")
def subscriptions(request: Request):
    return api_envelope(request, {"items": [{"channel": "email", "enabled": False}]})


@app.get("/api/v1/export/trends.csv")
def export_trends_csv(request: Request):
    return api_envelope(request, {"download": "/exports/trends.csv", "status": "generated"})


@app.get("/api/v1/b2b/trends")
def b2b_trends(request: Request):
    return api_envelope(request, {"items": [{"trend_key": "workflow-automation-agent", "score": 78.2}]})


@app.get("/api/v1/admin/sources")
def admin_sources(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return api_envelope(request, {"items": DataApiService(db).list_admin_sources()})


@app.post("/api/v1/admin/sources")
def admin_sources_upsert(
    request: Request,
    payload: AdminSourceConfigUpsert,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    try:
        data = DataApiService(db).upsert_admin_source(payload.model_dump(), _mask_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_envelope(request, data)


@app.post("/api/v1/admin/bootstrap/seed-demo")
def admin_seed_demo(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    seed_demo_bundle(db)
    trend_count = db.query(Trend).count()
    signal_count = db.query(EvidenceSignal).count()
    source_count = db.query(AdminSourceConfig).count()
    return api_envelope(
        request,
        {
            "status": "ok",
            "trend_count": trend_count,
            "signal_count": signal_count,
            "source_count": source_count,
        },
    )


@app.post("/api/v1/admin/bootstrap/clear-demo")
def admin_clear_demo(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    clear_business_data(db)
    return api_envelope(request, {"status": "ok", "message": "business data cleared"})


@app.post("/api/admin/v1/bootstrap/seed-demo")
def admin_seed_demo_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    result = admin_seed_demo(request, db)
    audit(db, actor=session.username, action="bootstrap.seed_demo")
    return result


@app.post("/api/admin/v1/bootstrap/clear-demo")
def admin_clear_demo_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    result = admin_clear_demo(request, db)
    audit(db, actor=session.username, action="bootstrap.clear_demo")
    return result


@app.get("/api/admin/v1/system/db-info")
def admin_db_info_v2(
    request: Request,
    session: AdminSession = Depends(require_role("admin")),
):
    _ = session
    info = get_db_runtime_info()
    return api_envelope(
        request,
        {
            "mode": info["mode"],
            "database_url": info["database_url"],
            "test_url": info["test_url"],
            "prod_url": info["prod_url"],
        },
    )


@app.get("/api/v1/admin/pages-plan")
def admin_pages_plan(request: Request, _: None = Depends(require_admin)):
    return api_envelope(
        request,
        {
            "items": [
                {
                    "key": "admin-overview",
                    "title": "后台总览",
                    "description": "查看数据覆盖、趋势/信号规模、系统健康度。",
                    "status": "ready",
                },
                {
                    "key": "source-center",
                    "title": "数据源与 API Key 管理",
                    "description": "管理第三方数据源开关、采集频率、API Base 和 Key。",
                    "status": "ready",
                },
                {
                    "key": "trend-ops",
                    "title": "趋势运营",
                    "description": "管理趋势标签、阶段、分数修正和人工标注。",
                    "status": "ready",
                },
                {
                    "key": "signal-ops",
                    "title": "信号运营",
                    "description": "审核信号质量、处理误报、查看证据链状态。",
                    "status": "ready",
                },
                {
                    "key": "compliance-workbench",
                    "title": "合规工单",
                    "description": "统一处理删除/纠错工单，形成审计闭环。",
                    "status": "ready",
                },
            ]
        },
    )


@app.get("/api/admin/v1/sources")
def admin_sources_v2(
    request: Request,
    keyword: str = "",
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, {"items": DataApiService(db).list_admin_sources(keyword=keyword.strip())})


@app.post("/api/admin/v1/sources")
def admin_sources_upsert_v2(
    request: Request,
    payload: AdminSourceConfigUpsert,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    try:
        data = DataApiService(db).upsert_admin_source(payload.model_dump(), _mask_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(db, actor=session.username, action="source.upsert", target=data["source"], detail=f"freq={data['frequency']}")
    return api_envelope(request, data)


@app.get("/api/admin/v1/compliance/removal-requests")
def admin_removal_requests_v2(
    request: Request,
    status: str = "",
    keyword: str = "",
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, {"items": DataApiService(db).list_removal_requests(status=status.strip(), keyword=keyword.strip())})


@app.post("/api/admin/v1/compliance/removal-requests/{ticket_id}/resolve")
def admin_resolve_v2(
    request: Request,
    ticket_id: str,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    data = DataApiService(db).resolve_removal_request(ticket_id)
    if not data:
        raise HTTPException(status_code=404, detail="ticket not found")
    audit(db, actor=session.username, action="removal.resolve", target=ticket_id)
    return api_envelope(request, data)


@app.get("/api/admin/v1/pages-plan")
def admin_pages_plan_v2(
    request: Request,
    session: AdminSession = Depends(require_role("viewer")),
):
    return admin_pages_plan(request)


@app.get("/api/admin/v1/overview")
def admin_overview_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, DataApiService(db).get_overview_metrics())


@app.get("/api/admin/v1/audit-logs")
def admin_audit_logs_v2(
    request: Request,
    limit: int = 50,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, {"items": DataApiService(db).list_audit_logs(limit)})


@app.get("/api/admin/v1/users")
def admin_users_v2(
    request: Request,
    role: str = "",
    keyword: str = "",
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    return api_envelope(request, {"items": DataApiService(db).list_admin_users(role=role.strip(), keyword=keyword.strip())})


@app.get("/api/admin/v1/query/trends")
def admin_query_trends_v2(
    request: Request,
    keyword: str = "",
    lifecycle: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(
        request,
        {"items": DataApiService(db).query_trends(keyword=keyword.strip(), lifecycle=lifecycle.strip(), limit=limit)},
    )


@app.get("/api/admin/v1/query/signals")
def admin_query_signals_v2(
    request: Request,
    keyword: str = "",
    source: str = "",
    status: str = "",
    limit: int = 80,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(
        request,
        {
            "items": DataApiService(db).query_signals(
                keyword=keyword.strip(),
                source=source.strip(),
                status=status.strip(),
                limit=limit,
            )
        },
    )


@app.post("/api/admin/v1/trend-ops/{trend_key}")
def admin_trend_ops_update_v2(
    request: Request,
    trend_key: str,
    payload: TrendOpsUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    data = DataApiService(db).update_trend_ops(trend_key, payload.model_dump())
    if not data:
        raise HTTPException(status_code=404, detail="trend not found")
    audit(db, actor=session.username, action="trend.update", target=trend_key, detail=str(payload.model_dump()))
    return api_envelope(request, data)


@app.post("/api/admin/v1/signal-ops/{signal_id}")
def admin_signal_ops_update_v2(
    request: Request,
    signal_id: str,
    payload: SignalOpsUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    data = DataApiService(db).update_signal_ops(signal_id, payload.model_dump())
    if not data:
        raise HTTPException(status_code=404, detail="signal not found")
    audit(db, actor=session.username, action="signal.update", target=signal_id, detail=str(payload.model_dump()))
    return api_envelope(request, data)


@app.post("/api/admin/v1/users")
def admin_users_create_v2(
    request: Request,
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    exists = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if exists:
        raise HTTPException(status_code=409, detail="username exists")
    _validate_password_policy(db, payload.password)
    item = AdminUser(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        enabled=payload.enabled,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    audit(db, actor=session.username, action="user.create", target=username, detail=f"role={payload.role}")
    return api_envelope(request, {"username": item.username, "role": item.role, "enabled": item.enabled})


@app.post("/api/admin/v1/users/{username}")
def admin_users_update_v2(
    request: Request,
    username: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    item = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not item:
        raise HTTPException(status_code=404, detail="user not found")
    if payload.role is not None:
        if item.username == session.username and payload.role != "admin":
            raise HTTPException(status_code=400, detail="cannot downgrade yourself")
        item.role = payload.role
    if payload.enabled is not None:
        if item.username == session.username and payload.enabled is False:
            raise HTTPException(status_code=400, detail="cannot disable yourself")
        item.enabled = payload.enabled
    if payload.password:
        _validate_password_policy(db, payload.password)
        item.password_hash = hash_password(payload.password)
        item.failed_attempts = 0
        item.locked_until = None
    item.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="user.update", target=username)
    return api_envelope(request, {"username": item.username, "role": item.role, "enabled": item.enabled})


@app.get("/api/admin/v1/settings")
def admin_settings_get_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    return api_envelope(request, DataApiService(db).get_settings())


@app.post("/api/admin/v1/settings")
def admin_settings_update_v2(
    request: Request,
    payload: AdminSettingsUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    data = DataApiService(db).update_settings(payload.model_dump())
    audit(db, actor=session.username, action="settings.update")
    return api_envelope(request, data)


@app.get("/api/admin/v1/health")
def admin_health_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    metrics = DataApiService(db).get_overview_metrics()
    return api_envelope(request, {"status": "ok", "db": "up", "metrics": metrics, "time": datetime.utcnow().isoformat()})


@app.get("/api/v1/admin/taxonomy")
def admin_taxonomy(request: Request, _: None = Depends(require_admin)):
    return api_envelope(request, {"version": "v1", "items": ["workflow-automation-agent", "coding-agent"]})


@app.get("/api/v1/admin/compliance/removal-requests")
def admin_removal_requests(request: Request, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    return api_envelope(request, {"items": DataApiService(db).list_removal_requests()})


@app.post("/api/v1/admin/compliance/removal-requests/{ticket_id}/resolve")
def admin_resolve(request: Request, ticket_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    data = DataApiService(db).resolve_removal_request(ticket_id)
    if not data:
        raise HTTPException(status_code=404, detail="ticket not found")
    return api_envelope(request, data)


@app.post("/api/v1/compliance/removal-requests")
def create_removal(request: Request, req: RemovalRequestCreate, db: Session = Depends(get_db)):
    ticket = create_removal_ticket(db, req)
    return api_envelope(request, {"ticket_id": ticket.ticket_id, "token": ticket.token, "status": ticket.status})


@app.get("/api/v1/compliance/removal-requests/{ticket_id}")
def get_removal(request: Request, ticket_id: str, token: str = Query(...), db: Session = Depends(get_db)):
    item = db.scalar(select(RemovalRequest).where(RemovalRequest.ticket_id == ticket_id))
    if not item or item.token != token:
        raise HTTPException(status_code=404, detail="ticket not found")
    return api_envelope(request, {"ticket_id": item.ticket_id, "status": item.status})


@app.post("/internal/run")
def internal_run(request: Request, req: InternalRunRequest, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    run = get_or_create_run(db, req)
    return api_envelope(request, {"run_id": run.run_id, "status": run.status, "idempotency_key": run.idempotency_key})


@app.get("/internal/runs/{run_id}")
def internal_run_status(request: Request, run_id: str, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    run = db.scalar(select(PipelineRun).where(PipelineRun.run_id == run_id))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return api_envelope(request, {"run_id": run.run_id, "job_type": run.job_type, "status": run.status, "retries": run.retries})


@app.get("/")
def api_root():
    """前后端分离：用户界面由 `frontend/`（Vite）提供，此处仅 API 入口说明。"""
    return {
        "service": "aisoul-api",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "ui": "http://127.0.0.1:5173",
        "hint": "cd frontend && npm install && npm run dev",
    }
