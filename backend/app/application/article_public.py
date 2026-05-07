from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import Select, and_, desc, func, or_, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..product_models import Article, Industry, Segment
from ..services import PRESET_SOURCE_LABELS


def _row_feed_lane(a: Article) -> str:
    fk = (getattr(a, "feed_kind", None) or "").strip().lower()
    if fk in ("news", "apps"):
        return fk
    return art.feed_lane(art.admin_source_key(a.third_party_source))


def _base_article_query_for_scope(
    db: Session,
    *,
    industry_slug: str,
    segment_id: int | None,
    segment_ids: list[int] | None,
    published_within_days: int | None,
    published_on_latest_day: bool,
) -> tuple[Industry | None, Select]:
    """已发布 + 行业/板块 + 时间窗；不含泳道、类别、游标。"""
    industry_slug = "ai"
    ind: Industry | None
    if segment_id is not None:
        seg = db.get(Segment, segment_id)
        if not seg:
            return None, select(Article).where(False)
        ind = db.get(Industry, seg.industry_id)
        if not ind:
            return None, select(Article).where(False)
    else:
        ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
        if not ind:
            return None, select(Article).where(False)

    if segment_ids is not None:
        segs = db.scalars(select(Segment).where(Segment.id.in_(segment_ids))).all()
        if len(segs) != len(set(segment_ids)):
            raise ValueError("invalid segment_ids")
        for s in segs:
            if s.industry_id != ind.id:
                raise ValueError("segment_ids must belong to industry_slug")

    since_pub: datetime | None = None
    if published_within_days is not None:
        since_pub = datetime.utcnow() - timedelta(days=published_within_days)

    cal_day = art.published_calendar_day(db)
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
        elif segment_ids is not None:
            sub = sub.where(Article.segment_id.in_(segment_ids))
        latest_calendar_day = db.scalar(sub)
        if latest_calendar_day is None:
            return ind, select(Article).where(False)

    q = select(Article).where(
        Article.industry_id == ind.id,
        Article.status == "published",
        Article.published_at.isnot(None),
    )
    if segment_id is not None:
        q = q.where(Article.segment_id == segment_id)
    elif segment_ids is not None:
        q = q.where(Article.segment_id.in_(segment_ids))
    if since_pub is not None:
        q = q.where(Article.published_at >= since_pub)
    elif latest_calendar_day is not None:
        q = q.where(cal_day == latest_calendar_day)

    return ind, q


def list_article_category_facets(
    db: Session,
    *,
    feed: str,
    industry_slug: str,
    segment_id: int | None,
    segment_ids: list[int] | None,
    published_within_days: int | None,
    published_on_latest_day: bool,
) -> list[dict]:
    """当前时间/板块范围内、指定泳道下，由 AI categories 聚合出的可选筛选项。"""
    ind, q = _base_article_query_for_scope(
        db,
        industry_slug=industry_slug,
        segment_id=segment_id,
        segment_ids=segment_ids,
        published_within_days=published_within_days,
        published_on_latest_day=published_on_latest_day,
    )
    if not ind:
        return []
    rows = db.scalars(q.order_by(desc(Article.published_at), desc(Article.id)).limit(4000)).all()
    ctr: Counter[str] = Counter()
    for a in rows:
        if _row_feed_lane(a) != feed:
            continue
        for c in art.parse_category_labels_json(getattr(a, "ai_categories_json", None)):
            if c:
                ctr[c] += 1
    return [{"label": k, "count": int(v)} for k, v in ctr.most_common(80)]


def list_articles_feed(
    db: Session,
    *,
    feed: str,
    industry_slug: str,
    segment_id: int | None,
    segment_ids: list[int] | None,
    page_size: int,
    cursor: str | None,
    exclude_fp: str | None,
    published_within_days: int | None,
    published_on_latest_day: bool,
    category: str | None = None,
) -> dict:
    industry_slug = "ai"
    scan_limit = 280
    cat_filter = (category or "").strip() or None

    ind, q = _base_article_query_for_scope(
        db,
        industry_slug=industry_slug,
        segment_id=segment_id,
        segment_ids=segment_ids,
        published_within_days=published_within_days,
        published_on_latest_day=published_on_latest_day,
    )
    if not ind:
        return {"items": [], "next_cursor": None, "has_more": False, "page_size": page_size}

    exclude = art.parse_exclude_fingerprints(exclude_fp)
    seen_fp: set[str] = set(exclude)
    out: list[dict] = []
    internal = art.decode_feed_cursor(cursor)
    last_scanned: tuple[datetime, int] | None = None
    has_more = False

    def _apply_keyset(stmt, pos: tuple[datetime, int] | None):
        if not pos:
            return stmt
        pub_c, id_c = pos
        return stmt.where(
            or_(
                Article.published_at < pub_c,
                and_(Article.published_at == pub_c, Article.id < id_c),
            )
        )

    while len(out) < page_size:
        q2 = _apply_keyset(q, internal).order_by(desc(Article.published_at), desc(Article.id))
        rows = db.scalars(q2.limit(scan_limit)).all()
        if not rows:
            break
        has_more = len(rows) >= scan_limit
        for a in rows:
            last_scanned = (a.published_at, a.id)
            ak = art.admin_source_key(a.third_party_source)
            row_lane = _row_feed_lane(a)
            if row_lane != feed:
                continue
            cats_list = art.parse_category_labels_json(getattr(a, "ai_categories_json", None))
            if cat_filter and cat_filter not in cats_list:
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            plat = PRESET_SOURCE_LABELS.get(ak, ak.replace("_", " ").title() if ak else "")
            out.append(
                {
                    "id": a.id,
                    "slug": a.slug,
                    "title": a.title,
                    "summary": a.summary,
                    "segment_id": a.segment_id,
                    "content_type": a.content_type,
                    "third_party_source": a.third_party_source,
                    "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
                    "fingerprint": fp,
                    "platform_label": plat,
                    "admin_source_key": ak,
                    "feed_kind": row_lane,
                    "categories": cats_list,
                }
            )
            if len(out) >= page_size:
                break
        internal = last_scanned
        if len(out) >= page_size:
            break
        if len(rows) < scan_limit:
            has_more = False
            break

    next_cursor = art.encode_feed_cursor(last_scanned[0], last_scanned[1]) if last_scanned else None
    return {"items": out, "next_cursor": next_cursor, "has_more": has_more, "page_size": page_size}


def get_published_article(db: Session, article_id: int) -> dict | None:
    a = db.get(Article, article_id)
    if not a or a.status != "published":
        return None
    ak = art.admin_source_key(a.third_party_source)
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "summary": a.summary,
        "body": a.body,
        "segment_id": a.segment_id,
        "content_type": a.content_type,
        "third_party_source": a.third_party_source,
        "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
        "categories": art.parse_category_labels_json(getattr(a, "ai_categories_json", None)),
        "feed_kind": _row_feed_lane(a),
        "admin_source_key": ak,
    }
