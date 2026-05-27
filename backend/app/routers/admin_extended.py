"""产品管理扩展 API：板块/指标/文章/连接器/配置/异动/灵感/用量。"""
from __future__ import annotations

import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..admin_auth import audit, require_role
from ..anomaly_service import compute_anomalies, get_anomaly_settings, list_anomaly_events, mark_anomaly_read, save_anomaly_settings
from ..db import get_db
from ..application.news_agent import pipeline_steps
from ..hot_service import get_hot_settings, save_hot_settings
from ..llm_settings_service import get_llm_settings_public, save_llm_settings_patch
from ..runtime_settings_service import get_runtime_settings_public, save_runtime_settings_patch
from ..newsletter_settings_service import get_newsletter_settings_public, save_newsletter_settings_patch
from ..scheduler_settings_service import get_scheduler_settings_public, save_scheduler_settings_patch
from ..llm_service import generate_inspiration_body
from ..models import AdminSession, AdminSourceConfig, NewsletterDailyDigest, NewsletterSubscriber
from ..product_models import (
    Article,
    HotSnapshot,
    Industry,
    Inspiration,
    InspirationVersion,
    LlmUsageLog,
    MetricDefinition,
    MetricPoint,
    ProductConnector,
    ProductConnectorLog,
    Segment,
)
from ..software_package_service import (
    create_software_package_with_file,
    delete_software_package,
    list_packages_admin,
)
from ..article_ingest import create_published_articles_for_connector_targets
from ..connector_heat_fetch import (
    arxiv_api_is_query_url,
    github_trending_is_discovery_url,
    hacker_news_algolia_is_search_url,
    huggingface_api_spaces_is_list_index,
    newsapi_is_v2_url,
    sync_arxiv_top_details,
    sync_github_trending_top_details,
    sync_hacker_news_top_details,
    sync_huggingface_spaces_top_details,
    sync_newsapi_top_headlines,
    sync_product_hunt_top_details,
    sync_thenewsapi_top_news,
    thenewsapi_is_news_url,
)
from ..domain.articles import (
    CONNECTOR_SNIPPET_MAX_CHARS,
    parse_connector_sync_item_snippets,
    unified_editorial_heat,
)
from ..source_segment_resolve import first_metric_for_segment, resolve_admin_source_key_to_segments

router = APIRouter(prefix="/api/admin/v1", tags=["admin-product-extended"])


def ok(data):
    return {"code": 0, "message": "ok", "data": data}


class HotSettingsPatch(BaseModel):
    top_n_trends: int | None = None
    top_n_articles: int | None = None
    llm_model: str | None = None


@router.get("/product/settings/hot")
def get_hot_setting(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(get_hot_settings(db))


@router.put("/product/settings/hot")
def put_hot_setting(
    payload: HotSettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    merged = save_hot_settings(db, patch)
    audit(db, actor=session.username, action="product.settings.hot", target="hot", detail=str(patch))
    return ok(merged)


@router.get("/product/settings/anomaly")
def get_anomaly_setting(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(get_anomaly_settings(db))


class LlmSettingsPatch(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = Field(None, description="非空则覆盖已存密钥；不传或空串表示保留原密钥")


@router.get("/product/settings/llm")
def get_llm_settings(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    data = get_llm_settings_public(db)
    return ok({**data, "pipeline": pipeline_steps()})


@router.put("/product/settings/llm")
def put_llm_settings(
    payload: LlmSettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    merged = save_llm_settings_patch(db, patch)
    audit(db, actor=session.username, action="product.settings.llm", target="llm", detail=str({k: v for k, v in patch.items() if k != "api_key"}))
    return ok({**merged, "pipeline": pipeline_steps()})


class SchedulerSettingsPatch(BaseModel):
    connector_scheduler_enabled: bool | None = None
    connector_sync_interval_hours: int | None = Field(None, ge=1, le=168)


@router.get("/product/settings/scheduler")
def get_scheduler_setting(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(get_scheduler_settings_public(db))


@router.put("/product/settings/scheduler")
def put_scheduler_setting(
    payload: SchedulerSettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    merged = save_scheduler_settings_patch(db, patch)
    audit(db, actor=session.username, action="product.settings.scheduler", target="scheduler", detail=str(patch))
    return ok(merged)


class NewsletterSettingsPatch(BaseModel):
    cron_enabled: bool | None = None
    generate_enabled: bool | None = None
    send_enabled: bool | None = None
    feishu_enabled: bool | None = None
    daily_digest_job_enabled: bool | None = None
    subscribe_verify_mx: bool | None = None
    article_limit: int | None = Field(None, ge=1, le=80)
    apps_limit: int | None = Field(None, ge=1, le=40)
    news_limit: int | None = Field(None, ge=1, le=40)
    llm_apps_limit: int | None = Field(None, ge=0, le=8, description="仅用于 LLM 写标题的 Top 应用数，0=不用 LLM")
    llm_news_limit: int | None = Field(None, ge=0, le=8, description="仅用于 LLM 写标题的 Top 资讯数，0=不用 LLM")
    daily_hour: int | None = Field(None, ge=0, le=23)
    daily_minute: int | None = Field(None, ge=0, le=59)
    public_site_base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_user: str | None = None
    smtp_password: str | None = Field(None, description="非空则覆盖已存 SMTP 密码；空串表示保留")
    mail_from: str | None = None
    smtp_use_tls: bool | None = None
    feishu_webhook_url: str | None = Field(None, description="非空则覆盖已存飞书 Webhook；空串表示保留")
    feishu_push_cadence: str | None = Field(None, description="飞书推送周期：daily | weekly | monthly")
    feishu_weekly_weekday: int | None = Field(None, ge=0, le=6, description="周报推送星期（0=周一，美东）")
    bcc_batch: int | None = Field(None, ge=1, le=80)
    footer_note: str | None = None


@router.get("/product/settings/newsletter")
def get_newsletter_setting(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(get_newsletter_settings_public(db))


@router.put("/product/settings/newsletter")
def put_newsletter_setting(
    payload: NewsletterSettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    patch = payload.model_dump(exclude_unset=True)
    merged = save_newsletter_settings_patch(db, patch)
    audit(
        db,
        actor=session.username,
        action="product.settings.newsletter",
        target="newsletter",
        detail=str({k: v for k, v in patch.items() if k not in ("smtp_password", "feishu_webhook_url")}),
    )
    return ok(merged)


class NewsletterDigestRunBody(BaseModel):
    digest_date: str | None = Field(None, description="YYYY-MM-DD，默认上海今日")
    regenerate: bool = False
    push_only: bool = Field(False, description="仅推送库内已有摘要，不生成（无当日摘要时报错）")


@router.get("/product/newsletter/digest/today")
def get_newsletter_digest_today(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    from ..application.newsletter_daily_digest import digest_row_public, shanghai_calendar_today

    key = shanghai_calendar_today().isoformat()
    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == key))
    active_subs = db.scalar(
        select(func.count())
        .select_from(NewsletterSubscriber)
        .where(
            NewsletterSubscriber.unsubscribed_at.is_(None),
        )
    )
    return ok(
        {
            "digest": digest_row_public(row),
            "digest_date": key,
            "active_subscribers": int(active_subs or 0),
        }
    )


@router.post("/product/newsletter/digest/run")
def post_newsletter_digest_run(
    body: NewsletterDigestRunBody,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    from ..application.newsletter_daily_digest import run_daily_newsletter_digest_job
    from ..newsletter_settings_service import get_newsletter_settings_merged

    settings = get_newsletter_settings_merged(db)
    out = run_daily_newsletter_digest_job(
        db,
        settings=settings,
        digest_date=body.digest_date,
        manual_run=True,
        regenerate=body.regenerate,
        push_only=body.push_only,
    )
    audit(
        db,
        actor=session.username,
        action="product.newsletter.digest.run",
        target=body.digest_date or "today",
        detail=str(out),
    )
    return ok(out)


class RuntimeSettingsPatch(BaseModel):
    cors_origins_csv: str | None = None
    jwt_ttl_seconds: int | None = Field(None, ge=60, le=864000)
    allowed_skew_seconds: int | None = Field(None, ge=30, le=3600)
    require_https: bool | None = None
    allow_insecure_localhost: bool | None = None
    admin_cookie_secure: bool | None = None
    app_env: str | None = Field(None, description="dev | local | staging | production")
    demo_seed_enabled: bool | None = None
    legacy_admin_enabled: bool | None = None
    app_release_label: str | None = None
    hot_llm_model: str | None = None


@router.get("/product/settings/runtime")
def get_runtime_setting(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(get_runtime_settings_public(db))


@router.put("/product/settings/runtime")
def put_runtime_setting(
    payload: RuntimeSettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    patch = payload.model_dump(exclude_unset=True)
    save_runtime_settings_patch(db, patch)
    audit(db, actor=session.username, action="product.settings.runtime", target="runtime", detail=str(patch))
    return ok(get_runtime_settings_public(db))


class AnomalySettingsPatch(BaseModel):
    short_window_days: int | None = None
    baseline_days: int | None = None
    l1_z: float | None = None
    l2_z: float | None = None
    cooldown_hours: float | None = None
    board_k: int | None = None


@router.put("/product/settings/anomaly")
def put_anomaly_setting(
    payload: AnomalySettingsPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    merged = save_anomaly_settings(db, patch)
    audit(db, actor=session.username, action="product.settings.anomaly", target="anomaly", detail=str(patch))
    return ok(merged)


@router.get("/product/hot/snapshots/{snapshot_id}")
def get_hot_snapshot_detail(
    snapshot_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    s = db.get(HotSnapshot, snapshot_id)
    if not s:
        raise HTTPException(404, "not found")
    return ok(
        {
            "id": s.id,
            "industry_id": s.industry_id,
            "generated_at": s.generated_at.isoformat() + "Z",
            "status": s.status,
            "trigger": s.trigger,
            "error_message": s.error_message,
            "payload_json": s.payload_json or {},
        }
    )


def _mask_config_for_response(cfg: dict) -> dict:
    out = dict(cfg or {})
    for k in list(out.keys()):
        lk = k.lower()
        if "key" in lk or "secret" in lk or "token" in lk or "password" in lk:
            if out[k]:
                out[k] = "***"
    return out


@router.get("/product/connectors")
def list_connectors(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(select(ProductConnector).order_by(ProductConnector.id)).all()
    return ok(
        [
            {
                "id": r.id,
                "name": r.name,
                "provider_name": r.provider_name,
                "type": r.type,
                "config_json": _mask_config_for_response(r.config_json or {}),
                "enabled": r.enabled,
                "min_interval_seconds": r.min_interval_seconds,
                "last_sync_at": r.last_sync_at.isoformat() + "Z" if r.last_sync_at else None,
                "last_error": (r.last_error or "")[:500],
                "admin_source_key": (r.admin_source_key or "").strip() or None,
            }
            for r in rows
        ]
    )


class ConnectorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    provider_name: str = ""
    type: str = "api"
    config_json: dict = Field(default_factory=dict)
    enabled: bool = True
    min_interval_seconds: int = 3600
    # 与后台数据源 source 一致（小写），同步时按该数据源的领域/板块写入指标。
    admin_source_key: str | None = None


class ConnectorPatch(BaseModel):
    name: str | None = None
    provider_name: str | None = None
    type: str | None = None
    config_json: dict | None = None
    enabled: bool | None = None
    min_interval_seconds: int | None = None
    admin_source_key: str | None = None


@router.post("/product/connectors")
def create_connector(
    payload: ConnectorCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    ask = (payload.admin_source_key or "").strip().lower() or None
    c = ProductConnector(
        name=payload.name,
        provider_name=payload.provider_name,
        type=payload.type,
        config_json=payload.config_json,
        admin_source_key=ask,
        enabled=payload.enabled,
        min_interval_seconds=payload.min_interval_seconds,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    audit(db, actor=session.username, action="product.connector.create", target=str(c.id))
    return ok({"id": c.id})


@router.patch("/product/connectors/{connector_id}")
def patch_connector(
    connector_id: int,
    payload: ConnectorPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    c = db.get(ProductConnector, connector_id)
    if not c:
        raise HTTPException(404, "not found")
    data = payload.model_dump(exclude_unset=True)
    if "admin_source_key" in data:
        v = data["admin_source_key"]
        data["admin_source_key"] = (v or "").strip().lower() or None
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    audit(db, actor=session.username, action="product.connector.patch", target=str(connector_id))
    return ok({"id": c.id})


def apply_theme_to_connector_url(url: str, theme: str) -> str:
    """单次拉取：可选主题词写入 GET 查询参数 ``q``（仅当尚未配置 q/query/keywords/search_query）。"""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    t = (theme or "").strip()
    u = (url or "").strip()
    if not t or not u:
        return url
    parts = urlsplit(u)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    search_keys = ("q", "query", "keywords", "search_query")
    if any(str(q.get(k) or "").strip() for k in search_keys):
        return url
    q["q"] = t
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, encoding="utf-8"), parts.fragment))


def _snippet_pack_diag(snippet: str) -> str:
    import json

    s = (snippet or "")[:120000]
    n = len(parse_connector_sync_item_snippets(s) or [])
    note = ""
    diag_s = ""
    try:
        obj = json.loads(s[:12000])
        if isinstance(obj, dict):
            note = str(obj.get("note") or "").strip()
            diag = obj.get("diag")
            if isinstance(diag, dict) and diag:
                diag_s = " " + " ".join(f"{k}={v}" for k, v in diag.items())
    except json.JSONDecodeError:
        note = "not_json"
    return f"pack_items={n}" + (f" note={note}" if note else "") + diag_s


def _connector_log_fetch_outcome(
    db: Session | None,
    *,
    code: int,
    text: str,
    connector_id: int | None = None,
    source_key: str | None = None,
) -> None:
    """仅在上游失败或 pack_items=0 时写入 error 诊断。"""
    if db is None:
        return
    out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
    diag = _snippet_pack_diag(out)
    sk = (source_key or "").strip().lower()
    if code and 200 <= code < 300:
        if "pack_items=0" in diag:
            from ..connector_ingest_diagnostics import format_fetch_empty_message

            _connector_req_diag(
                db,
                level="error",
                step="fetch_empty",
                message=f"HTTP {code} {format_fetch_empty_message(diag, source_key=sk)}",
                connector_id=connector_id,
                source_key=sk or None,
            )
        return
    _connector_req_diag(
        db,
        level="error",
        step="heat_done",
        message=f"HTTP {code or '—'} {diag}",
        connector_id=connector_id,
        source_key=sk or None,
    )


def _log_news_fetch_stats(
    db: Session,
    *,
    snippet: str,
    source_key: str,
    connector_id: int,
    http_status: int,
) -> None:
    """NewsAPI / TheNewsAPI：将 pack 内 diag 统计写入同步日志。"""
    import json

    from ..connector_heat_fetch import _news_fetch_diag_message
    from ..sync_diagnostic_log import commit_diagnostics, write as diag_write

    sk = (source_key or "").strip().lower()
    if sk not in ("newsapi", "thenewsapi"):
        return
    note = ""
    stats: dict[str, int] = {}
    try:
        obj = json.loads((snippet or "")[:12000])
        if isinstance(obj, dict):
            note = str(obj.get("note") or "").strip()
            raw_diag = obj.get("diag")
            if isinstance(raw_diag, dict):
                stats = {str(k): int(v) for k, v in raw_diag.items() if isinstance(v, (int, float))}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    packed = int(stats.get("packed") or 0)
    if http_status and 200 <= http_status < 300 and packed > 0:
        return
    msg = f"HTTP {http_status} {_news_fetch_diag_message(sk, note or '—', stats)}"
    if http_status and 200 <= http_status < 300 and not packed:
        preview = (snippet or "").replace("\n", " ")[:200]
        msg += f" body_preview={preview!r}"
    diag_write(
        db,
        level="error",
        step="news_fetch_empty",
        message=msg,
        connector_id=connector_id,
        source_key=sk,
    )
    commit_diagnostics(db)


def _connector_req_diag(
    db: Session | None,
    *,
    level: str,
    step: str,
    message: str,
    connector_id: int | None = None,
    source_key: str | None = None,
) -> None:
    if db is None:
        return
    from ..sync_diagnostic_log import commit_diagnostics, get_current_run_id, should_persist_diagnostic, write

    if not should_persist_diagnostic(level=level, step=step):
        return
    write(
        db,
        run_id=get_current_run_id(),
        level=level,
        step=step,
        message=message[:8000],
        connector_id=connector_id,
        source_key=(source_key or "").strip().lower() or None,
    )
    commit_diagnostics(db)


def _run_connector_request(
    cfg: dict,
    db: Session | None = None,
    *,
    connector_id: int | None = None,
    source_key: str | None = None,
) -> tuple[int, str]:
    url = (cfg or {}).get("url") or "https://httpbin.org/get"
    method = ((cfg or {}).get("method") or "GET").upper()
    source_key = ((cfg or {}).get("source_key") or source_key or "").strip().lower()
    sk = source_key
    auth_mode = ((cfg or {}).get("auth_mode") or "bearer").strip().lower()
    api_key = ((cfg or {}).get("api_key") or "").strip()
    key_param = ((cfg or {}).get("key_param") or "key").strip() or "key"
    from ..admin_source_fetch import normalize_fetch_limit

    fetch_n = normalize_fetch_limit(
        int((cfg or {}).get("fetch_limit") or 0) or None,
        source=sk or None,
    )
    headers = {
        "User-Agent": "AiTrends-ConnectorSync/1.0",
        "Accept": "application/json",
    }
    oauth_secret = str((cfg or {}).get("oauth_client_secret") or "").strip()
    if source_key == "product_hunt":
        from ..product_hunt_oauth import resolve_product_hunt_bearer

        try:
            bearer, _mode = resolve_product_hunt_bearer(api_key=api_key, oauth_client_secret=oauth_secret)
            headers["Authorization"] = f"Bearer {bearer}"
        except (ValueError, RuntimeError) as e:
            msg = str(e)[:800]
            _connector_req_diag(
                db,
                level="error",
                step="ph_auth",
                message=f"Product Hunt 鉴权失败: {msg}",
                connector_id=connector_id,
                source_key=sk,
            )
            return 0, msg
    elif api_key:
        if auth_mode == "private_token":
            headers["PRIVATE-TOKEN"] = api_key
        elif auth_mode == "query_key":
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            parts = urlsplit(url)
            q = dict(parse_qsl(parts.query, keep_blank_values=True))
            q[key_param] = api_key
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))
        else:
            headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            if source_key == "product_hunt":
                code, text = sync_product_hunt_top_details(headers, limit=fetch_n)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "github" and github_trending_is_discovery_url(url):
                code, text = sync_github_trending_top_details(url, headers, limit=fetch_n)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "hacker_news" and hacker_news_algolia_is_search_url(url):
                code, text = sync_hacker_news_top_details(url, headers, limit=fetch_n)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "newsapi" and newsapi_is_v2_url(url):
                code, text = sync_newsapi_top_headlines(url, headers, limit=fetch_n)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "thenewsapi" and thenewsapi_is_news_url(url):
                code, text = sync_thenewsapi_top_news(url, headers, limit=fetch_n)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "arxiv" or arxiv_api_is_query_url(url):
                code, text = sync_arxiv_top_details(url, headers)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "huggingface_spaces" and huggingface_api_spaces_is_list_index(url):
                code, text = sync_huggingface_spaces_top_details(url, headers)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            from ..connector_heat_fetch import (
                acquire_portal_is_list_url,
                sync_acquire_top_details,
                sync_taaft_top_details,
                taaft_list_is_new_tools_url,
            )

            if source_key == "taaft" and taaft_list_is_new_tools_url(url):
                code, text = sync_taaft_top_details(url, headers)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            if source_key == "acquire" and acquire_portal_is_list_url(url):
                code, text = sync_acquire_top_details(url, headers)
                out = (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                _connector_log_fetch_outcome(
                    db, code=code or 0, text=out, connector_id=connector_id, source_key=sk,
                )
                return code, out
            from ..product_connectors_bootstrap import mainstream_heat_fetch_url_ok
            from ..services import BUILTIN_ADMIN_SOURCE_KEYS

            if source_key in BUILTIN_ADMIN_SOURCE_KEYS and not mainstream_heat_fetch_url_ok(source_key, url):
                msg = (
                    f"数据源 {source_key} 的 URL 未匹配热度打包路径，请使用后台预设 api_base 或执行修复。"
                    f" 当前: {url[:240]}"
                )
                _connector_req_diag(
                    db, level="error", step="url_invalid", message=msg,
                    connector_id=connector_id, source_key=sk,
                )
                return 0, msg
            _connector_req_diag(
                db,
                level="error",
                step="http_fallback",
                message=f"未走热度打包，直接 {method} 请求（可能无法入库多段 pack） url={url[:200]}",
                connector_id=connector_id,
                source_key=sk,
            )
            r = client.request(method, url, headers=headers)
        text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
        _connector_log_fetch_outcome(
            db, code=r.status_code, text=text, connector_id=connector_id, source_key=sk,
        )
        return r.status_code, text
    except Exception as e:
        msg = str(e)[:800]
        _connector_req_diag(
            db, level="error", step="http_exception", message=msg,
            connector_id=connector_id, source_key=sk,
        )
        return 0, msg


def run_connector_sync(
    db: Session,
    connector_id: int,
    actor: str = "system",
    *,
    bypass_rate_limit: bool = False,
    theme: str | None = None,
) -> dict:
    from ..sync_diagnostic_log import begin_connector_run, commit_diagnostics, get_current_run_id, write as diag_write

    c = db.get(ProductConnector, connector_id)
    if not c:
        raise HTTPException(404, "not found")
    now = datetime.utcnow()
    ask_preview = (c.admin_source_key or "").strip().lower()
    if not get_current_run_id():
        begin_connector_run(db, actor=actor, connector_id=connector_id, source_key=ask_preview)
    # 定时任务整批同步须绕过「最短间隔」，否则会 429 并被静默吞掉，表现为「从未自动拉取」。
    if not bypass_rate_limit and c.last_sync_at and c.min_interval_seconds:
        delta = (now - c.last_sync_at).total_seconds()
        if delta < c.min_interval_seconds:
            diag_write(
                db,
                level="error",
                step="rate_limit",
                message=f"连接器 #{c.id} {c.name!r} 被最短间隔限制（{c.min_interval_seconds}s）",
                connector_id=c.id,
                source_key=ask_preview or None,
            )
            commit_diagnostics(db)
            raise HTTPException(429, f"rate limited: min_interval_seconds={c.min_interval_seconds}")
    log = ProductConnectorLog(connector_id=c.id, started_at=now, status="running")
    db.add(log)
    db.flush()

    cfg = dict(c.config_json or {})
    ask = (c.admin_source_key or "").strip().lower()
    if ask:
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == ask))
        if src:
            cfg.setdefault("source_key", ask)
            api_base = (src.api_base or "").strip()
            if api_base:
                cfg["url"] = api_base
            # 真实密钥以数据源保存为准：见 DataApiService.upsert_admin_source 写入各绑定连接器的 config_json.api_key。
            if ask == "newsapi":
                cfg.setdefault("auth_mode", "query_key")
                cfg.setdefault("key_param", "apiKey")
            elif ask == "thenewsapi":
                cfg.setdefault("auth_mode", "query_key")
                cfg.setdefault("key_param", "api_token")
            else:
                cfg.setdefault("auth_mode", "bearer")
            if int(src.fetch_limit or 0) > 0:
                cfg["fetch_limit"] = int(src.fetch_limit)

    if ask:
        from ..source_query_auth import (
            load_stored_api_key_for_source,
            query_auth_for_source,
            source_uses_query_key_auth,
        )

        if source_uses_query_key_auth(ask) and not str(cfg.get("api_key") or "").strip():
            stored = load_stored_api_key_for_source(db, ask)
            if stored:
                cfg["api_key"] = stored
        if source_uses_query_key_auth(ask) and not str(cfg.get("api_key") or "").strip():
            _, param = query_auth_for_source(ask)
            err = (
                f"{ask} 未配置 API Key：请在数据源卡片填写密钥并「保存」"
                f"（同步使用 Query 参数 {param}，与「测试连接」相同）"
            )
            c.last_error = err
            log.status = "error"
            log.error_message = err
            log.finished_at = datetime.utcnow()
            diag_write(
                db,
                level="error",
                step="auth_missing",
                message=err,
                connector_id=c.id,
                source_key=ask,
            )
            diag_write(
                db,
                level="error",
                step="connector_done",
                message=f"同步结束 status=error 新建文章=0 错误={err}",
                connector_id=c.id,
                source_key=ask,
            )
            commit_diagnostics(db)
            db.commit()
            return {
                "diagnostic_run_id": get_current_run_id(),
                "connector_id": c.id,
                "http_status": 0,
                "rows_ingested": 0,
                "articles_created": 0,
                "error": err,
            }

    tnorm = (theme or "").strip() or None
    if tnorm:
        u0 = (cfg.get("url") or "").strip()
        if u0:
            cfg["url"] = apply_theme_to_connector_url(u0, tnorm)

    status_code = 0
    snippet = ""
    rows_ingested = 0
    articles_created = 0
    err = None
    try:
        status_code, snippet = _run_connector_request(
            cfg, db, connector_id=c.id, source_key=ask or ask_preview,
        )
        if ask or ask_preview:
            _log_news_fetch_stats(
                db,
                snippet=snippet or "",
                source_key=ask or ask_preview or "",
                connector_id=c.id,
                http_status=status_code or 0,
            )
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:400]}"
        c.last_error = err
        log.status = "error"
        log.error_message = err
        log.finished_at = datetime.utcnow()
        diag_write(
            db,
            level="error",
            step="connector_aborted",
            message=f"同步异常中断：{err}",
            connector_id=c.id,
            source_key=ask or ask_preview or None,
        )
        commit_diagnostics(db)
        db.commit()
        raise

    if status_code and 200 <= status_code < 300:
        base_val = float(status_code % 100) / 10.0 + 0.1
        if ask:
            targets = resolve_admin_source_key_to_segments(db, ask)
            if not targets:
                err = "已绑定数据源但无法解析出行业/板块：请检查数据源「所属领域」是否与 taxonomy 一致"
                diag_write(
                    db,
                    level="error",
                    step="segments",
                    message=err,
                    connector_id=c.id,
                    source_key=ask,
                )
            else:
                articles_created = create_published_articles_for_connector_targets(
                    db,
                    connector_id=c.id,
                    connector_name=c.name,
                    admin_source_key=ask,
                    targets=targets,
                    http_status=status_code or 0,
                    snippet=snippet,
                    now=now,
                    connector_sync_log_id=log.id,
                )
                for i, t in enumerate(targets):
                    m = first_metric_for_segment(db, t["segment_id"])
                    if m:
                        db.add(
                            MetricPoint(
                                metric_id=m.id,
                                segment_id=t["segment_id"],
                                bucket_start=now,
                                value=base_val + i * 0.01,
                                source_ref=f"connector:{c.id}:{t['segment_slug']}",
                            )
                        )
                        rows_ingested += 1
        else:
            m = db.scalar(select(MetricDefinition).where(MetricDefinition.segment_id.isnot(None)).limit(1))
            if m and m.segment_id:
                db.add(
                    MetricPoint(
                        metric_id=m.id,
                        segment_id=m.segment_id,
                        bucket_start=now,
                        value=base_val,
                        source_ref=f"connector:{c.id}",
                    )
                )
                rows_ingested = 1
                seg = db.get(Segment, m.segment_id)
                if seg:
                    articles_created = create_published_articles_for_connector_targets(
                        db,
                        connector_id=c.id,
                        connector_name=c.name,
                        admin_source_key="",
                        targets=[
                            {
                                "industry_id": seg.industry_id,
                                "segment_id": seg.id,
                                "segment_slug": seg.slug,
                                "label": seg.name,
                            }
                        ],
                        http_status=status_code or 0,
                        snippet=snippet,
                        now=now,
                        connector_sync_log_id=log.id,
                    )
        c.last_sync_at = now
        c.last_error = err
        if err:
            log.status = "error"
            log.error_message = err
        else:
            log.status = "ok"
    else:
        err = f"HTTP {status_code or 'error'}"
        c.last_error = err
        log.status = "error"
        log.error_message = err
        diag_write(
            db,
            level="error",
            step="http_fail",
            message=err + (f" 片段预览: {(snippet or '')[:200]}" if snippet else ""),
            connector_id=c.id,
            source_key=ask or None,
        )

    log.finished_at = datetime.utcnow()
    log.rows_ingested = rows_ingested + articles_created
    try:
        if err or articles_created == 0:
            pack_diag = _snippet_pack_diag(snippet or "")
            if err:
                done_msg = (
                    f"同步结束 status={log.status} 新建文章=0 错误={err}"
                )
            elif "pack_items=0" in pack_diag:
                done_msg = (
                    f"同步结束 status={log.status} 新建文章=0（上游无 pack 条目，见 fetch_empty）"
                )
            else:
                done_msg = (
                    f"同步结束 status={log.status} 新建文章=0（pack 有条目但未入库，"
                    f"见本 run skip_* / skip_llm_* / ingest_pack_empty）"
                )
            diag_write(
                db,
                level="error",
                step="connector_done",
                message=done_msg,
                connector_id=c.id,
                source_key=ask or ask_preview or None,
            )
        commit_diagnostics(db)
        db.commit()
    except Exception as e:
        diag_write(
            db,
            level="error",
            step="connector_aborted",
            message=f"同步收尾失败（可能已部分入库）：{type(e).__name__}: {str(e)[:300]}",
            connector_id=c.id,
            source_key=ask or None,
        )
        commit_diagnostics(db)
        raise
    audit(db, actor=actor, action="product.connector.sync", target=str(connector_id))
    run_id = get_current_run_id()
    return {
        "diagnostic_run_id": run_id,
        "connector_id": c.id,
        "http_status": status_code,
        "rows_ingested": rows_ingested,
        "articles_created": articles_created,
        "error": err,
        "log_hint": (
            f"请到「同步日志」选择 run_id={run_id} 后点「复制本批日志」发给运维排查"
            if run_id
            else "请到「同步日志」页复制最近日志"
        ),
    }


def run_theme_fetch_batch(db: Session, *, actor: str, theme: str | None) -> dict:
    """按后台数据源领域标签刷新 taxonomy，并对所有已启用连接器立即同步（不受单连接器最短间隔限制）。"""
    import logging

    from ..llm_service import resolve_llm_http_config
    from ..product_connectors_bootstrap import (
        repair_connector_urls_from_admin_sources,
        repair_mainstream_heat_fetch_admin_sources,
        repair_short_probe_admin_sources,
    )
    from ..sync_diagnostic_log import begin_run, commit_diagnostics, end_run, write as diag_write
    from ..taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

    log = logging.getLogger(__name__)
    repair_short_probe_admin_sources(db)
    n_repair = repair_mainstream_heat_fetch_admin_sources(db)
    n_url = repair_connector_urls_from_admin_sources(db)
    run_id = begin_run(db, actor=actor)
    from ..product_connectors_bootstrap import audit_mainstream_connector_paths

    bad_urls = [r for r in audit_mainstream_connector_paths(db) if not r.get("heat_fetch_url_ok")]
    if bad_urls:
        diag_write(
            db,
            run_id=run_id,
            level="error",
            step="source_url_audit",
            message=(
                f"已修复主流源 api_base {n_repair} 处；连接器 URL 对齐 {n_url} 个。仍异常: "
                + ", ".join(f"{r['source']}({r.get('api_base', '')[:48]})" for r in bad_urls)
            ),
        )
        commit_diagnostics(db)
    tnorm = (theme or "").strip() or None
    details: list[dict] = []
    ok_n = 0
    fail_n = 0
    rows: list[ProductConnector] = []
    try:
        sync_product_taxonomy_from_admin_sources(db, commit=False)
        _llm_base, llm_key, _llm_model = resolve_llm_http_config(db)
        llm_ok = bool((llm_key or "").strip())
        if not llm_ok:
            diag_write(
                db,
                run_id=run_id,
                level="error",
                step="llm_config",
                message="未配置 LLM：拉取成功也不会生成文章，请在「AI 资讯与数据」配置 DeepSeek",
            )
            commit_diagnostics(db)
        rows = db.scalars(
            select(ProductConnector).where(ProductConnector.enabled.is_(True)).order_by(ProductConnector.id)
        ).all()
    except Exception as e:
        log.exception("theme_fetch_batch early phase failed run_id=%s", run_id)
        diag_write(
            db,
            run_id=run_id,
            level="error",
            step="batch_fatal",
            message=f"整批拉取在准备阶段失败：{type(e).__name__}: {str(e)[:600]}",
        )
        end_run(db, run_id=run_id, ok=0, fail=0, total=0)
        commit_diagnostics(db)
        audit(db, actor=actor, action="product.ingest.theme_fetch", detail=f"fatal={type(e).__name__}")
        return {
            "diagnostic_run_id": run_id,
            "taxonomy_synced": False,
            "theme_applied_to_url": bool(tnorm),
            "connectors_total": 0,
            "ok": 0,
            "fail": 0,
            "details": details,
            "batch_error": str(e)[:500],
        }
    for c in rows:
        try:
            out = run_connector_sync(db, c.id, actor=actor, bypass_rate_limit=True, theme=tnorm)
            err = out.get("error")
            if err:
                fail_n += 1
            else:
                ok_n += 1
            details.append(
                {
                    "connector_id": c.id,
                    "name": c.name,
                    "http_status": out.get("http_status"),
                    "articles_created": out.get("articles_created"),
                    "rows_ingested": out.get("rows_ingested"),
                    "error": err,
                }
            )
        except HTTPException as e:
            fail_n += 1
            diag_write(
                db,
                run_id=run_id,
                level="error",
                step="connector_fail",
                message=f"连接器 #{c.id} {c.name!r}: {e.detail}",
                connector_id=c.id,
                source_key=(c.admin_source_key or ""),
            )
            details.append({"connector_id": c.id, "name": c.name, "error": str(e.detail)})
        except Exception as e:
            fail_n += 1
            diag_write(
                db,
                run_id=run_id,
                level="error",
                step="connector_fail",
                message=f"连接器 #{c.id} {c.name!r}: {str(e)[:400]}",
                connector_id=c.id,
                source_key=(c.admin_source_key or ""),
            )
            details.append({"connector_id": c.id, "name": c.name, "error": str(e)[:240]})
    articles_total = sum(int(d.get("articles_created") or 0) for d in details)
    if not articles_total:
        diag_write(
            db,
            run_id=run_id,
            level="error",
            step="batch_articles",
            message="本批新建文章 0 篇：请查看各连接器 connector_done、skip_llm_*、fetch_empty 等错误行。",
        )
    end_run(db, run_id=run_id, ok=ok_n, fail=fail_n, total=len(rows))
    commit_diagnostics(db)
    audit(db, actor=actor, action="product.ingest.theme_fetch", detail=f"theme={tnorm!r}, ok={ok_n}, fail={fail_n}")
    return {
        "diagnostic_run_id": run_id,
        "taxonomy_synced": True,
        "theme_applied_to_url": bool(tnorm),
        "connectors_total": len(rows),
        "ok": ok_n,
        "fail": fail_n,
        "details": details,
        "log_hint": f"请到「同步日志」选择 run_id={run_id}，点「复制本批日志」发给运维排查",
    }


@router.get("/product/resolve-source/{source_key}")
def resolve_source_segments_preview(
    source_key: str,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    """根据后台「数据源」标识预览解析出的行业/板块（与同步入库使用同一逻辑）。"""
    rows = resolve_admin_source_key_to_segments(db, source_key)
    return ok({"source_key": source_key.strip().lower(), "targets": rows})


@router.post("/product/connectors/{connector_id}/test")
def test_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    c = db.get(ProductConnector, connector_id)
    if not c:
        raise HTTPException(404, "not found")
    ask = (c.admin_source_key or "").strip().lower()
    status_code, snippet = _run_connector_request(
        c.config_json or {}, db, connector_id=connector_id, source_key=ask,
    )
    return ok({"http_status": status_code, "snippet": snippet})


@router.post("/product/connectors/{connector_id}/sync")
def sync_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    return ok(run_connector_sync(db, connector_id, actor=session.username))


@router.get("/product/segments")
def list_segments(
    industry_slug: str = Query("ai"),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        raise HTTPException(404, "industry not found")
    rows = db.scalars(select(Segment).where(Segment.industry_id == ind.id).order_by(Segment.sort_order, Segment.id)).all()
    return ok(
        [
            {
                "id": r.id,
                "industry_id": r.industry_id,
                "slug": r.slug,
                "name": r.name,
                "enabled": r.enabled,
                "sort_order": r.sort_order,
                "show_on_public": r.show_on_public,
            }
            for r in rows
        ]
    )


class SegmentCreate(BaseModel):
    slug: str
    name: str
    sort_order: int = 0
    enabled: bool = True
    show_on_public: bool = True


class SegmentPatch(BaseModel):
    name: str | None = None
    slug: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None
    show_on_public: bool | None = None


@router.post("/product/segments")
def create_segment(
    payload: SegmentCreate,
    industry_slug: str = Query("ai"),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        raise HTTPException(404, "industry not found")
    s = Segment(
        industry_id=ind.id,
        slug=payload.slug,
        name=payload.name,
        sort_order=payload.sort_order,
        enabled=payload.enabled,
        show_on_public=payload.show_on_public,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    audit(db, actor=session.username, action="product.segment.create", target=str(s.id))
    return ok({"id": s.id})


@router.patch("/product/segments/{segment_id}")
def patch_segment(
    segment_id: int,
    payload: SegmentPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    s = db.get(Segment, segment_id)
    if not s:
        raise HTTPException(404, "not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    db.commit()
    audit(db, actor=session.username, action="product.segment.patch", target=str(segment_id))
    return ok({"id": s.id})


@router.get("/product/metrics")
def list_metrics(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(select(MetricDefinition).order_by(MetricDefinition.id)).all()
    return ok(
        [
            {
                "id": r.id,
                "key": r.key,
                "name": r.name,
                "unit": r.unit,
                "aggregation": r.aggregation,
                "segment_id": r.segment_id,
                "participates_in_anomaly": r.participates_in_anomaly,
                "value_kind": r.value_kind,
            }
            for r in rows
        ]
    )


class MetricCreate(BaseModel):
    key: str
    name: str
    unit: str = ""
    aggregation: str = "mean"
    segment_id: int | None = None
    participates_in_anomaly: bool = True
    value_kind: str = "absolute"


class MetricPatch(BaseModel):
    name: str | None = None
    unit: str | None = None
    aggregation: str | None = None
    segment_id: int | None = None
    participates_in_anomaly: bool | None = None
    value_kind: str | None = None


@router.post("/product/metrics")
def create_metric(
    payload: MetricCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    m = MetricDefinition(
        key=payload.key,
        name=payload.name,
        unit=payload.unit,
        aggregation=payload.aggregation,
        segment_id=payload.segment_id,
        participates_in_anomaly=payload.participates_in_anomaly,
        value_kind=payload.value_kind,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    audit(db, actor=session.username, action="product.metric.create", target=m.key)
    return ok({"id": m.id})


@router.patch("/product/metrics/{metric_id}")
def patch_metric(
    metric_id: int,
    payload: MetricPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    m = db.get(MetricDefinition, metric_id)
    if not m:
        raise HTTPException(404, "not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    db.commit()
    audit(db, actor=session.username, action="product.metric.patch", target=str(metric_id))
    return ok({"id": m.id})


@router.get("/product/articles")
def list_articles(
    segment_id: int | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    stmt = select(Article)
    if segment_id is not None:
        stmt = stmt.where(Article.segment_id == segment_id)
    if status:
        stmt = stmt.where(Article.status == status)
    stmt = stmt.order_by(desc(Article.updated_at)).limit(limit)
    rows = db.scalars(stmt).all()
    return ok(
        [
            {
                "id": r.id,
                "slug": r.slug,
                "title": r.title,
                "summary": (r.summary or "")[:240],
                "segment_id": r.segment_id,
                "industry_id": r.industry_id,
                "content_type": r.content_type,
                "status": r.status,
                "published_at": r.published_at.isoformat() + "Z" if r.published_at else None,
                "is_featured": r.is_featured,
                "updated_at": r.updated_at.isoformat() + "Z" if r.updated_at else None,
                "heat_score": float(getattr(r, "heat_score", 0.0) or 0.0),
                "connector_sync_log_id": getattr(r, "connector_sync_log_id", None),
                "source_external_id": getattr(r, "source_external_id", None),
            }
            for r in rows
        ]
    )


@router.get("/product/articles/{article_id}")
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    a = db.get(Article, article_id)
    if not a:
        raise HTTPException(404, "not found")
    return ok(
        {
            "id": a.id,
            "slug": a.slug,
            "title": a.title,
            "summary": a.summary,
            "body": a.body,
            "segment_id": a.segment_id,
            "industry_id": a.industry_id,
            "content_type": a.content_type,
            "third_party_source": a.third_party_source,
            "connector_sync_log_id": getattr(a, "connector_sync_log_id", None),
            "source_external_id": getattr(a, "source_external_id", None),
            "status": a.status,
            "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
            "is_featured": a.is_featured,
            "updated_at": a.updated_at.isoformat() + "Z" if a.updated_at else None,
            "heat_score": float(getattr(a, "heat_score", 0.0) or 0.0),
        }
    )


class ArticleCreate(BaseModel):
    title: str
    slug: str | None = None
    summary: str = ""
    body: str = ""
    segment_id: int
    industry_id: int
    content_type: str = "third_party_derived"
    third_party_source: str | None = None
    connector_sync_log_id: int | None = None
    source_external_id: str | None = None
    status: str = "draft"
    is_featured: bool = False
    heat_score: float | None = None


class ArticlePatch(BaseModel):
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    body: str | None = None
    segment_id: int | None = None
    content_type: str | None = None
    third_party_source: str | None = None
    connector_sync_log_id: int | None = None
    source_external_id: str | None = None
    status: str | None = None
    is_featured: bool | None = None
    heat_score: float | None = None


@router.post("/product/articles")
def create_article(
    payload: ArticleCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    if payload.content_type == "application" and not (payload.third_party_source or "").strip():
        raise HTTPException(400, "application-type articles require third_party_source")
    heat_val = payload.heat_score
    if heat_val is None:
        heat_val = unified_editorial_heat(sync_unix=time.time()) if payload.status == "published" else 0.0
    else:
        heat_val = float(heat_val)
    a = Article(
        title=payload.title,
        slug=payload.slug,
        summary=payload.summary,
        body=payload.body,
        segment_id=payload.segment_id,
        industry_id=payload.industry_id,
        content_type=payload.content_type,
        third_party_source=payload.third_party_source,
        connector_sync_log_id=payload.connector_sync_log_id,
        source_external_id=(payload.source_external_id or "").strip() or None,
        status=payload.status,
        is_featured=payload.is_featured,
        heat_score=heat_val,
        published_at=datetime.utcnow() if payload.status == "published" else None,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    audit(db, actor=session.username, action="product.article.create", target=str(a.id))
    return ok({"id": a.id})


@router.patch("/product/articles/{article_id}")
def patch_article(
    article_id: int,
    payload: ArticlePatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    a = db.get(Article, article_id)
    if not a:
        raise HTTPException(404, "not found")
    old_status = a.status
    data = payload.model_dump(exclude_unset=True)
    if "source_external_id" in data:
        v = data.get("source_external_id")
        data["source_external_id"] = (v or "").strip() or None
    for k, v in data.items():
        setattr(a, k, v)
    if data.get("status") == "published" and not a.published_at:
        a.published_at = datetime.utcnow()
    if old_status != "published" and a.status == "published" and "heat_score" not in data:
        if float(getattr(a, "heat_score", 0.0) or 0.0) == 0.0:
            a.heat_score = unified_editorial_heat(sync_unix=time.time())
    a.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="product.article.patch", target=str(article_id))
    return ok({"id": a.id})


@router.get("/product/anomalies")
def list_anomalies(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = list_anomaly_events(db, limit=limit)
    out = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "segment_id": r.segment_id,
                "metric_id": r.metric_id,
                "score": r.score,
                "level": r.level,
                "detail_json": r.detail_json or {},
                "created_at": r.created_at.isoformat() + "Z",
                "read_at": r.read_at.isoformat() + "Z" if r.read_at else None,
            }
        )
    return ok(out)


@router.post("/product/anomalies/{event_id}/read")
def post_anomaly_read(
    event_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    if not mark_anomaly_read(db, event_id):
        raise HTTPException(404, "not found")
    audit(db, actor=session.username, action="product.anomaly.read", target=str(event_id))
    return ok({"id": event_id})


@router.post("/product/anomalies/scan")
def post_anomaly_scan(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    n = compute_anomalies(db)
    audit(db, actor=session.username, action="product.anomaly.scan", detail=str(n))
    return ok({"created": n})


@router.get("/product/inspirations")
def list_inspirations(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(select(Inspiration).order_by(desc(Inspiration.id)).limit(100)).all()
    seg_names = {s.id: s.name for s in db.scalars(select(Segment)).all()}
    return ok(
        [
            {
                "id": r.id,
                "segment_id": r.segment_id,
                "segment_name": seg_names.get(r.segment_id, ""),
                "title": r.title,
                "current_version_id": r.current_version_id,
            }
            for r in rows
        ]
    )


@router.get("/product/inspirations/{inspiration_id}/versions")
def list_inspiration_versions(
    inspiration_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(
        select(InspirationVersion).where(InspirationVersion.inspiration_id == inspiration_id).order_by(InspirationVersion.version_no)
    ).all()
    return ok(
        [
            {
                "id": r.id,
                "version_no": r.version_no,
                "body": r.body,
                "context_snapshot_json": r.context_snapshot_json or {},
                "status": r.status,
                "created_by_username": r.created_by_username,
                "created_at": r.created_at.isoformat() + "Z",
            }
            for r in rows
        ]
    )


class InspirationCreate(BaseModel):
    segment_id: int
    title: str = ""


@router.post("/product/inspirations")
def create_inspiration(
    payload: InspirationCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    insp = Inspiration(segment_id=payload.segment_id, title=payload.title or "未命名灵感")
    db.add(insp)
    db.flush()
    ver = InspirationVersion(
        inspiration_id=insp.id,
        version_no=1,
        body="",
        context_snapshot_json={},
        created_by_username=session.username,
        status="draft",
    )
    db.add(ver)
    db.flush()
    insp.current_version_id = ver.id
    db.commit()
    audit(db, actor=session.username, action="product.inspiration.create", target=str(insp.id))
    return ok({"id": insp.id, "version_id": ver.id})


class InspirationGenerate(BaseModel):
    context_md: str = ""


@router.post("/product/inspirations/{inspiration_id}/generate")
def generate_inspiration(
    inspiration_id: int,
    payload: InspirationGenerate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    insp = db.get(Inspiration, inspiration_id)
    if not insp:
        raise HTTPException(404, "not found")
    max_no = db.scalar(select(func.max(InspirationVersion.version_no)).where(InspirationVersion.inspiration_id == inspiration_id))
    next_no = (max_no or 0) + 1
    body = generate_inspiration_body(
        db,
        context_md=payload.context_md or "",
        username=session.username,
        inspiration_id=inspiration_id,
        version_no=next_no,
        admin_user_id=session.user_id,
    )
    ver = InspirationVersion(
        inspiration_id=inspiration_id,
        version_no=next_no,
        body=body,
        context_snapshot_json={"context_md": (payload.context_md or "")[:8000]},
        created_by_username=session.username,
        status="draft",
    )
    db.add(ver)
    db.flush()
    insp.current_version_id = ver.id
    db.commit()
    audit(db, actor=session.username, action="product.inspiration.generate", target=f"{inspiration_id}:v{next_no}")
    return ok({"version_id": ver.id, "version_no": next_no})


class InspirationVersionPatch(BaseModel):
    body: str | None = None
    status: str | None = None


@router.patch("/product/inspirations/{inspiration_id}/versions/{version_id}")
def patch_inspiration_version(
    inspiration_id: int,
    version_id: int,
    payload: InspirationVersionPatch,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    ver = db.get(InspirationVersion, version_id)
    if not ver or ver.inspiration_id != inspiration_id:
        raise HTTPException(404, "not found")
    if payload.body is not None:
        ver.body = payload.body
    if payload.status is not None:
        ver.status = payload.status
    db.commit()
    audit(db, actor=session.username, action="product.inspiration.version.patch", target=str(version_id))
    return ok({"id": ver.id})


@router.get("/product/llm-usage")
def list_llm_usage(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(select(LlmUsageLog).order_by(desc(LlmUsageLog.created_at)).limit(limit)).all()
    return ok(
        [
            {
                "id": r.id,
                "scenario": r.scenario,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "admin_user_id": r.admin_user_id,
                "ref_type": r.ref_type,
                "ref_id": r.ref_id,
                "success": r.success,
                "error_code": r.error_code,
                "created_at": r.created_at.isoformat() + "Z",
            }
            for r in rows
        ]
    )


@router.get("/product/connectors/{connector_id}/logs")
def list_connector_logs(
    connector_id: int,
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(
        select(ProductConnectorLog)
        .where(ProductConnectorLog.connector_id == connector_id)
        .order_by(desc(ProductConnectorLog.started_at))
        .limit(limit)
    ).all()
    return ok(
        [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() + "Z",
                "finished_at": r.finished_at.isoformat() + "Z" if r.finished_at else None,
                "status": r.status,
                "rows_ingested": r.rows_ingested,
                "error_message": r.error_message,
            }
            for r in rows
        ]
    )


@router.get("/product/software/packages")
def admin_list_software_packages(
    limit: int = Query(80, ge=1, le=200),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return ok(list_packages_admin(db, limit=limit))


@router.post("/product/software/packages")
async def admin_upload_software_package(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
    file: UploadFile = File(...),
    title: str = Form(...),
    summary: str = Form(""),
    platform: str = Form(...),
    category_slug: str = Form("general"),
    category_label: str = Form(""),
    sort_order: int = Form(0),
    store_url: str = Form(""),
):
    body = await file.read()
    try:
        row = create_software_package_with_file(
            db,
            title=title,
            summary=summary,
            platform=platform,
            category_slug=category_slug,
            category_label=category_label or category_slug,
            file_body=body,
            original_filename=file.filename or "package.bin",
            content_type=file.content_type,
            sort_order=sort_order,
            store_url=store_url or None,
            status="published",
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    audit(db, actor=session.username, action="product.software.upload", target=str(row.id), detail=row.title[:120])
    return ok(
        {
            "id": row.id,
            "title": row.title,
            "platform": row.platform,
            "download_path": f"/api/public/v1/software/downloads/{row.id}/file",
        }
    )


@router.delete("/product/software/packages/{package_id}")
def admin_delete_software_package(
    package_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    if not delete_software_package(db, package_id):
        raise HTTPException(404, "not found")
    audit(db, actor=session.username, action="product.software.delete", target=str(package_id))
    return ok({"deleted": package_id})
