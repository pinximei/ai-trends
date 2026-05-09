from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import Select, and_, desc, or_, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..product_models import Article, Industry, Segment
from ..services import PRESET_SOURCE_LABELS
from ..taxonomy_from_sources import MERGED_TAXONOMY_INDUSTRY_SLUG

_MAX_FEED_SEARCH_LEN = 80


def normalize_feed_search(raw: str | None) -> str | None:
    """Strip and cap length; empty after strip → no search filter."""
    s = (raw or "").strip()
    if not s:
        return None
    if len(s) > _MAX_FEED_SEARCH_LEN:
        s = s[:_MAX_FEED_SEARCH_LEN]
    return s


def _article_title_summary_matches(a: Article, needle: str) -> bool:
    """Case-insensitive substring on title + summary (after泳道筛选，避免 SQL 先筛关键词再分页挤掉另一泳道)."""
    n = needle.lower()
    hay = f"{a.title or ''} {a.summary or ''}".lower()
    return n in hay


def _public_industry_ids_for_slug(db: Session, ind: Industry) -> list[int]:
    """前台 industry_slug=ai 时同时收录 taxonomy「domains」下连接器入库文章。"""
    ids = [ind.id]
    if (ind.slug or "").strip().lower() == "ai":
        dom = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
        if dom and dom.id not in ids:
            ids.append(dom.id)
    return ids


def _row_feed_lane(a: Article) -> str:
    """公开列表/详情泳道：一律按数据源 admin_source_key 规则推断。

    曾用 LLM 写入的 product_articles.feed_kind 若与连接器不一致，会导致「AI 资讯 / AI 应用」
    两页拉取到同一批文章；公开站以连接器规则为准（与入库时 feed_lane 一致）。
    """
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
        allowed_ids = set(_public_industry_ids_for_slug(db, ind))
        for s in segs:
            if s.industry_id not in allowed_ids:
                raise ValueError("segment_ids must belong to industry_slug")

    since_pub: datetime | None = None
    utc_day_start: datetime | None = None
    utc_day_end: datetime | None = None
    if published_within_days is not None:
        since_pub = datetime.utcnow() - timedelta(days=published_within_days)
    elif published_on_latest_day:
        # 「最新一日」= 自然日「今天」（UTC），与入库 published_at（naive UTC）一致。
        # 旧实现用 max(日历日) 会变成「库里最新一篇是哪天就筛哪天」，易把 2025-06 等旧稿当成「今日」。
        now = datetime.utcnow()
        utc_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_day_end = utc_day_start + timedelta(days=1)

    article_industry_ids = (
        _public_industry_ids_for_slug(db, ind) if segment_id is None and segment_ids is None else [ind.id]
    )
    q = select(Article).where(
        Article.industry_id.in_(article_industry_ids),
        Article.status == "published",
        Article.published_at.isnot(None),
    )
    if segment_id is not None:
        q = q.where(Article.segment_id == segment_id)
    elif segment_ids is not None:
        q = q.where(Article.segment_id.in_(segment_ids))
    if since_pub is not None:
        q = q.where(Article.published_at >= since_pub)
    elif utc_day_start is not None and utc_day_end is not None:
        q = q.where(Article.published_at >= utc_day_start, Article.published_at < utc_day_end)

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
    search: str | None = None,
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
    n = normalize_feed_search(search)
    rows = db.scalars(q.order_by(desc(Article.published_at), desc(Article.id)).limit(4000)).all()
    ctr: Counter[str] = Counter()
    for a in rows:
        if _row_feed_lane(a) != feed:
            continue
        if n and not _article_title_summary_matches(a, n):
            continue
        primary = art.primary_canonical_from_raw_labels(
            art.parse_category_labels_json(getattr(a, "ai_categories_json", None))
        )
        ctr[primary] += 1
    return [{"label": lab, "count": int(ctr[lab])} for lab in art.FACET_DISPLAY_ORDER if ctr.get(lab, 0) > 0]


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
    search: str | None = None,
) -> dict:
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
    n = normalize_feed_search(search)

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
            cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
            if cat_filter and cats_list and cats_list[0] != cat_filter:
                continue
            if n and not _article_title_summary_matches(a, n):
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            plat = PRESET_SOURCE_LABELS.get(ak, ak.replace("_", " ").title() if ak else "")
            tabs_parsed = art.parse_article_tabs_json(getattr(a, "ai_tabs_json", None))
            tab_summaries = (
                [{"label": x["label"], "summary": (x["summary"] or "")[:280]} for x in tabs_parsed[:6]] if tabs_parsed else []
            )
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
                    "tab_summaries": tab_summaries,
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
    tabs = art.parse_article_tabs_json(getattr(a, "ai_tabs_json", None))
    if not tabs and (a.body or "").strip():
        tabs = [
            {
                "label": "全文",
                "summary": (a.summary or "")[:400] or "正文",
                "body_md": (a.body or "").strip(),
            }
        ]
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
        "categories": art.display_categories_for_article(getattr(a, "ai_categories_json", None)),
        "feed_kind": _row_feed_lane(a),
        "admin_source_key": ak,
        "tabs": tabs,
    }
