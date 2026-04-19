from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Date, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..product_models import Article, CmsPage, HotSnapshot, Industry, MetricDefinition, MetricPoint, Segment
from ..taxonomy_from_sources import (
    industry_ids_with_public_content,
    industry_slugs_from_enabled_sources,
    segment_ids_with_public_content_for_industry,
    segment_slugs_from_enabled_sources_for_industry,
)

router = APIRouter(prefix="/api/public/v1", tags=["public-v1"])


def ok(data):
    return {"code": 0, "message": "ok", "data": data}


def _article_published_calendar_day(db: Session):
    """按自然日筛选文章。SQLite 用 strftime，避免 max(cast(date)) 在部分驱动下触发类型处理错误。"""
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", Article.published_at)
    return cast(Article.published_at, Date)


@router.get("/meta/industries")
def list_industries(db: Session = Depends(get_db)):
    """
    行业列表：优先反映「已启用数据源」scope_label 中的行业；
    并与已有指标/已发布文章涉及的行业合并，避免历史内容不可见。
    若无任何启用数据源带 scope，则退回为全部已启用行业。
    """
    src_slugs = industry_slugs_from_enabled_sources(db)
    q = select(Industry).where(Industry.enabled == True)
    if src_slugs:
        legacy_ids = industry_ids_with_public_content(db)
        if legacy_ids:
            q = q.where(or_(Industry.slug.in_(src_slugs), Industry.id.in_(legacy_ids)))
        else:
            q = q.where(Industry.slug.in_(src_slugs))
    rows = db.scalars(q.order_by(Industry.sort_order)).all()
    return ok([{"id": r.id, "slug": r.slug, "name": r.name} for r in rows])


@router.get("/meta/segments")
def list_segments(industry_id: int | None = Query(None), industry_slug: str | None = Query(None), db: Session = Depends(get_db)):
    """
    板块列表：优先反映当前行业下「已启用数据源」scope 中的板块；
    并与已有指标或已发布文章使用的板块合并。
    """
    q = select(Segment).where(Segment.enabled == True)
    if industry_id is not None:
        q = q.where(Segment.industry_id == industry_id)
        ind = db.get(Industry, industry_id)
        if ind:
            src_seg_slugs = segment_slugs_from_enabled_sources_for_industry(db, ind)
            if src_seg_slugs:
                legacy_seg = segment_ids_with_public_content_for_industry(db, industry_id)
                if legacy_seg:
                    q = q.where(or_(Segment.slug.in_(src_seg_slugs), Segment.id.in_(legacy_seg)))
                else:
                    q = q.where(Segment.slug.in_(src_seg_slugs))
    elif industry_slug:
        ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
        if not ind:
            return ok([])
        q = q.where(Segment.industry_id == ind.id)
        src_seg_slugs = segment_slugs_from_enabled_sources_for_industry(db, ind)
        if src_seg_slugs:
            legacy_seg = segment_ids_with_public_content_for_industry(db, ind.id)
            if legacy_seg:
                q = q.where(or_(Segment.slug.in_(src_seg_slugs), Segment.id.in_(legacy_seg)))
            else:
                q = q.where(Segment.slug.in_(src_seg_slugs))
    rows = db.scalars(q.order_by(Segment.sort_order)).all()
    ind_ids = {r.industry_id for r in rows}
    ind_slug: dict[int, str] = {}
    if ind_ids:
        for ir in db.scalars(select(Industry).where(Industry.id.in_(ind_ids))).all():
            ind_slug[ir.id] = ir.slug
    return ok(
        [
            {
                "id": r.id,
                "slug": r.slug,
                "name": r.name,
                "industry_id": r.industry_id,
                "industry_slug": ind_slug.get(r.industry_id, ""),
            }
            for r in rows
        ]
    )


@router.get("/meta/metrics")
def list_metrics(
    segment_id: int | None = None,
    industry_slug: str | None = None,
    db: Session = Depends(get_db),
):
    q = select(MetricDefinition)
    if segment_id is not None:
        q = q.where(MetricDefinition.segment_id == segment_id)
    elif industry_slug:
        ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
        if not ind:
            return ok([])
        seg_ids = db.scalars(select(Segment.id).where(Segment.industry_id == ind.id)).all()
        if not seg_ids:
            return ok([])
        q = q.where(MetricDefinition.segment_id.in_(seg_ids))
    rows = db.scalars(q).all()
    return ok(
        [
            {
                "id": r.id,
                "key": r.key,
                "name": r.name,
                "unit": r.unit,
                "aggregation": r.aggregation,
                "segment_id": r.segment_id,
            }
            for r in rows
        ]
    )


@router.get("/hot/current")
def hot_current(industry_slug: str = Query("ai"), db: Session = Depends(get_db)):
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        return ok({"trend_items": [], "article_ids": [], "generated_at": None, "payload": {}, "status": "no_industry"})
    snap = db.scalar(select(HotSnapshot).where(HotSnapshot.industry_id == ind.id).order_by(desc(HotSnapshot.generated_at)).limit(1))
    if not snap:
        return ok({"trend_items": [], "article_ids": [], "generated_at": None, "payload": {}})
    return ok(
        {
            "generated_at": snap.generated_at.isoformat() + "Z",
            "status": snap.status,
            "payload": snap.payload_json,
        }
    )


@router.get("/trends/summary")
def trends_summary(
    industry_slug: str = Query("ai"),
    segment_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow() - timedelta(days=days)
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        return ok(
            {
                "industry": industry_slug,
                "since": since.isoformat() + "Z",
                "metrics": [],
            }
        )
    q = (
        select(MetricDefinition.id, MetricDefinition.key, MetricDefinition.name, func.avg(MetricPoint.value).label("avg_v"))
        .join(MetricPoint, MetricPoint.metric_id == MetricDefinition.id)
        .join(Segment, Segment.id == MetricPoint.segment_id)
        .where(Segment.industry_id == ind.id, MetricPoint.bucket_start >= since)
    )
    if segment_id is not None:
        q = q.where(MetricPoint.segment_id == segment_id)
    rows = db.execute(q.group_by(MetricDefinition.id, MetricDefinition.key, MetricDefinition.name)).all()
    return ok(
        {
            "industry": industry_slug,
            "since": since.isoformat() + "Z",
            "metrics": [{"key": r.key, "name": r.name, "avg": float(r.avg_v) if r.avg_v is not None else None} for r in rows],
        }
    )


@router.get("/trends/series")
def trends_series(
    metric_key: str = Query(...),
    industry_slug: str = Query("ai"),
    segment_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        return ok({"metric_key": metric_key, "points": []})
    m = db.scalar(
        select(MetricDefinition)
        .join(Segment, Segment.id == MetricDefinition.segment_id)
        .where(MetricDefinition.key == metric_key, Segment.industry_id == ind.id)
    )
    if not m:
        return ok({"metric_key": metric_key, "points": []})
    since = datetime.utcnow() - timedelta(days=days)
    q = select(MetricPoint).where(MetricPoint.metric_id == m.id, MetricPoint.bucket_start >= since)
    if segment_id is not None:
        q = q.where(MetricPoint.segment_id == segment_id)
    pts = db.scalars(q.order_by(MetricPoint.bucket_start)).all()
    return ok(
        {
            "metric_key": metric_key,
            "points": [{"t": p.bucket_start.isoformat() + "Z", "value": p.value} for p in pts],
        }
    )


def _parse_segment_ids_csv(raw: str | None) -> list[int] | None:
    if not raw or not str(raw).strip():
        return None
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out or None


@router.get("/articles")
def list_articles(
    industry_slug: str = Query("ai"),
    segment_id: int | None = None,
    segment_ids: str | None = Query(
        None,
        description="Comma-separated segment ids (same industry as industry_slug); for「其他」overflow. Mutually exclusive with segment_id.",
    ),
    sort: str = Query("hot", pattern="^(hot|latest)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    published_within_days: int | None = Query(None, ge=1, le=3650),
    published_on_latest_day: bool = Query(False),
    db: Session = Depends(get_db),
):
    segment_ids_parsed = _parse_segment_ids_csv(segment_ids)
    if segment_id is not None and segment_ids_parsed is not None:
        raise HTTPException(400, "segment_id and segment_ids are mutually exclusive")

    ind: Industry | None
    if segment_id is not None:
        seg = db.get(Segment, segment_id)
        if not seg:
            return ok({"items": [], "total": 0, "page": page, "page_size": page_size})
        ind = db.get(Industry, seg.industry_id)
        if not ind:
            return ok({"items": [], "total": 0, "page": page, "page_size": page_size})
    else:
        ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
        if not ind:
            return ok({"items": [], "total": 0, "page": page, "page_size": page_size})

    if segment_ids_parsed is not None:
        segs = db.scalars(select(Segment).where(Segment.id.in_(segment_ids_parsed))).all()
        if len(segs) != len(set(segment_ids_parsed)):
            raise HTTPException(400, "invalid segment_ids")
        for s in segs:
            if s.industry_id != ind.id:
                raise HTTPException(400, "segment_ids must belong to industry_slug")

    since_pub: datetime | None = None
    if published_within_days is not None:
        since_pub = datetime.utcnow() - timedelta(days=published_within_days)

    cal_day = _article_published_calendar_day(db)
    latest_calendar_day = None
    if published_within_days is None and published_on_latest_day:
        sub = (
            select(func.max(cal_day))
            .where(
                Article.industry_id == ind.id,
                Article.status == "published",
                Article.published_at.isnot(None),
            )
            .select_from(Article)
        )
        if segment_id is not None:
            sub = sub.where(Article.segment_id == segment_id)
        elif segment_ids_parsed is not None:
            sub = sub.where(Article.segment_id.in_(segment_ids_parsed))
        latest_calendar_day = db.scalar(sub)
        if latest_calendar_day is None:
            return ok({"items": [], "total": 0, "page": page, "page_size": page_size})

    q = select(Article).where(Article.industry_id == ind.id, Article.status == "published")
    if segment_id is not None:
        q = q.where(Article.segment_id == segment_id)
    elif segment_ids_parsed is not None:
        q = q.where(Article.segment_id.in_(segment_ids_parsed))
    if since_pub is not None:
        q = q.where(Article.published_at.isnot(None), Article.published_at >= since_pub)
    elif latest_calendar_day is not None:
        q = q.where(Article.published_at.isnot(None), cal_day == latest_calendar_day)

    qc = select(func.count()).select_from(Article).where(Article.industry_id == ind.id, Article.status == "published")
    if segment_id is not None:
        qc = qc.where(Article.segment_id == segment_id)
    elif segment_ids_parsed is not None:
        qc = qc.where(Article.segment_id.in_(segment_ids_parsed))
    if since_pub is not None:
        qc = qc.where(Article.published_at.isnot(None), Article.published_at >= since_pub)
    elif latest_calendar_day is not None:
        qc = qc.where(Article.published_at.isnot(None), cal_day == latest_calendar_day)
    total = db.scalar(qc) or 0

    if sort == "latest":
        q = q.order_by(desc(Article.published_at))
        rows = db.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()
    else:
        snap = db.scalar(select(HotSnapshot).where(HotSnapshot.industry_id == ind.id).order_by(desc(HotSnapshot.generated_at)).limit(1))
        order_ids = (snap.payload_json or {}).get("article_ids") if snap else []
        if order_ids:
            # preserve hot order for first page
            id_order = {aid: i for i, aid in enumerate(order_ids)}
            all_rows = db.scalars(q).all()
            all_rows.sort(key=lambda a: id_order.get(a.id, 9999))
            start = (page - 1) * page_size
            rows = all_rows[start : start + page_size]
        else:
            rows = db.scalars(q.order_by(desc(Article.published_at)).offset((page - 1) * page_size).limit(page_size)).all()

    items = [
        {
            "id": a.id,
            "slug": a.slug,
            "title": a.title,
            "summary": a.summary,
            "segment_id": a.segment_id,
            "content_type": a.content_type,
            "third_party_source": a.third_party_source,
            "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
        }
        for a in rows
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    a = db.get(Article, article_id)
    if not a or a.status != "published":
        raise HTTPException(404, "not found")
    return ok(
        {
            "id": a.id,
            "slug": a.slug,
            "title": a.title,
            "summary": a.summary,
            "body": a.body,
            "segment_id": a.segment_id,
            "content_type": a.content_type,
            "third_party_source": a.third_party_source,
            "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
        }
    )


def _rank_heat_score(rank: int, n: int) -> float:
    """名次热度：第 1 名 100，末名约 10（n=1 时为 100）。"""
    if n <= 0:
        return 0.0
    if n == 1:
        return 100.0
    return round(100.0 - (rank - 1) * (90.0 / max(n - 1, 1)), 1)


def _activity_index(a: Article) -> float:
    """无单条用量埋点时，用发布时间新鲜度 + 精选标记作为「活跃/使用」代理指标。"""
    base = 50.0
    if a.published_at:
        days = (datetime.utcnow() - a.published_at).days
        base = max(10.0, 100.0 - float(min(days, 90)))
    if a.is_featured:
        base = min(100.0, base + 5.0)
    return round(base, 1)


@router.get("/segments/{segment_id}/top-products")
def segment_top_products(
    segment_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """板块内代表「产品/内容」的条目 TOP N：优先热门快照顺序，不足则按发布时间补齐。"""
    seg = db.get(Segment, segment_id)
    if not seg or not seg.enabled:
        raise HTTPException(404, "segment not found")
    ind = db.get(Industry, seg.industry_id)
    if not ind:
        raise HTTPException(404, "industry not found")

    rows = db.scalars(
        select(Article).where(
            Article.industry_id == ind.id,
            Article.status == "published",
            Article.segment_id == segment_id,
        )
    ).all()
    id_to_article = {a.id: a for a in rows}

    snap = db.scalar(
        select(HotSnapshot).where(HotSnapshot.industry_id == ind.id).order_by(desc(HotSnapshot.generated_at)).limit(1)
    )
    order_ids = (snap.payload_json or {}).get("article_ids") if snap else []

    picked: list[Article] = []
    seen: set[int] = set()
    for aid in order_ids:
        if aid in id_to_article and len(picked) < limit:
            picked.append(id_to_article[aid])
            seen.add(aid)

    rest = sorted(
        [a for a in rows if a.id not in seen],
        key=lambda x: x.published_at or datetime.min,
        reverse=True,
    )
    for a in rest:
        if len(picked) >= limit:
            break
        picked.append(a)

    n = len(picked)
    items = []
    for i, a in enumerate(picked):
        rank = i + 1
        items.append(
            {
                "rank": rank,
                "id": a.id,
                "slug": a.slug,
                "title": a.title,
                "summary": (a.summary or "")[:400],
                "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
                "heat_score": _rank_heat_score(rank, n),
                "activity_index": _activity_index(a),
                "source": a.third_party_source,
            }
        )

    return ok({"segment_id": segment_id, "segment_name": seg.name, "limit": limit, "items": items})


@router.get("/pages/{slug}")
def get_page(slug: str, db: Session = Depends(get_db)):
    p = db.get(CmsPage, slug)
    if not p or p.status != "published":
        raise HTTPException(404, "not found")
    return ok({"slug": p.slug, "title": p.title, "body_md": p.body_md, "updated_at": p.updated_at.isoformat() + "Z"})


@router.get("/health")
def health_public():
    return ok({"status": "ok"})
