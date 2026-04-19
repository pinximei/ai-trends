"""产品管理扩展 API：板块/指标/文章/连接器/配置/异动/灵感/用量。"""
from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..admin_auth import audit, require_role
from ..anomaly_service import compute_anomalies, get_anomaly_settings, list_anomaly_events, mark_anomaly_read, save_anomaly_settings
from ..db import get_db
from ..hot_service import get_hot_settings, save_hot_settings
from ..llm_service import generate_inspiration_body
from ..models import AdminSession
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
from ..article_ingest import create_published_articles_for_connector_targets
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


def _run_connector_request(cfg: dict) -> tuple[int, str]:
    url = (cfg or {}).get("url") or "https://httpbin.org/get"
    method = ((cfg or {}).get("method") or "GET").upper()
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.request(method, url)
        text = (r.text or "")[:800]
        return r.status_code, text
    except Exception as e:
        return 0, str(e)[:800]


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
    status_code, snippet = _run_connector_request(c.config_json or {})
    return ok({"http_status": status_code, "snippet": snippet})


@router.post("/product/connectors/{connector_id}/sync")
def sync_connector(
    connector_id: int,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    c = db.get(ProductConnector, connector_id)
    if not c:
        raise HTTPException(404, "not found")
    now = datetime.utcnow()
    if c.last_sync_at and c.min_interval_seconds:
        delta = (now - c.last_sync_at).total_seconds()
        if delta < c.min_interval_seconds:
            raise HTTPException(429, f"rate limited: min_interval_seconds={c.min_interval_seconds}")
    log = ProductConnectorLog(connector_id=c.id, started_at=now, status="running")
    db.add(log)
    db.flush()

    status_code, snippet = _run_connector_request(c.config_json or {})
    rows_ingested = 0
    articles_created = 0
    err = None
    if status_code and 200 <= status_code < 300:
        base_val = float(status_code % 100) / 10.0 + 0.1
        ask = (c.admin_source_key or "").strip().lower()
        if ask:
            targets = resolve_admin_source_key_to_segments(db, ask)
            if not targets:
                err = "已绑定数据源但无法解析出行业/板块：请检查数据源「所属领域」是否与 taxonomy 一致"
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

    log.finished_at = datetime.utcnow()
    log.rows_ingested = rows_ingested + articles_created
    db.commit()
    audit(db, actor=session.username, action="product.connector.sync", target=str(connector_id))
    return ok(
        {
            "connector_id": c.id,
            "http_status": status_code,
            "rows_ingested": rows_ingested,
            "articles_created": articles_created,
            "error": err,
        }
    )


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
            "status": a.status,
            "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
            "is_featured": a.is_featured,
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
    status: str = "draft"
    is_featured: bool = False


class ArticlePatch(BaseModel):
    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    body: str | None = None
    segment_id: int | None = None
    content_type: str | None = None
    third_party_source: str | None = None
    status: str | None = None
    is_featured: bool | None = None


@router.post("/product/articles")
def create_article(
    payload: ArticleCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    if payload.content_type == "application" and not (payload.third_party_source or "").strip():
        raise HTTPException(400, "application-type articles require third_party_source")
    a = Article(
        title=payload.title,
        slug=payload.slug,
        summary=payload.summary,
        body=payload.body,
        segment_id=payload.segment_id,
        industry_id=payload.industry_id,
        content_type=payload.content_type,
        third_party_source=payload.third_party_source,
        status=payload.status,
        is_featured=payload.is_featured,
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
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(a, k, v)
    if data.get("status") == "published" and not a.published_at:
        a.published_at = datetime.utcnow()
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
