from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import Select, and_, desc, func, or_, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..models import AdminSourceConfig
from ..product_models import Article, Industry, Segment
from ..taxonomy_from_sources import MERGED_TAXONOMY_INDUSTRY_SLUG

_MAX_FEED_SEARCH_LEN = 80
HEAT_FEED_MAX = 100
HEAT_PAGE_DEFAULT = 20
HEAT_PAGE_MAX = 20
DAYS_PER_PAGE_DEFAULT = 3


def _admin_source_label_by_key(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AdminSourceConfig)).all()
    return {
        r.source: ((r.preset_label or "").strip() or r.source.replace("_", " ").title()) for r in rows
    }


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


def _feed_row_matches_list_filters(
    a: Article,
    *,
    feed: str,
    cat_filter: str | None,
    search_n: str | None,
) -> bool:
    """与公开列表一致的泳道 / 类别 / 搜索筛选。"""
    if _row_feed_lane(a) != feed:
        return False
    cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    if cat_filter and cats_list and cats_list[0] != cat_filter:
        return False
    if search_n and not _article_title_summary_matches(a, search_n):
        return False
    return True


def _build_feed_fingerprint_winner_ids(
    db: Session,
    base_q: Select,
    *,
    feed: str,
    cat_filter: str | None,
    search_n: str | None,
    max_scan_rows: int = 48_000,
    batch: int = 500,
) -> frozenset[int]:
    """
    从新到旧扫描 base_q 范围内文章，对每个「标题+摘要」展示指纹只保留 **最新一篇** 的 id。

    解决连接器多日重复拉取、或 LLM 摘要微差导致 ingest 指纹不同而多次入库时，前台「昨天/今天」反复看到同一故事的问题。
    仅影响公开 feed / 分类统计；不删库。
    """
    winner_by_fp: dict[str, int] = {}
    internal: tuple[datetime, int] | None = None
    scanned = 0
    while scanned < max_scan_rows:
        q2 = _apply_published_keyset(base_q, internal).order_by(desc(Article.published_at), desc(Article.id))
        rows = db.scalars(q2.limit(batch)).all()
        if not rows:
            break
        for a in rows:
            scanned += 1
            if scanned > max_scan_rows:
                break
            if not _feed_row_matches_list_filters(a, feed=feed, cat_filter=cat_filter, search_n=search_n):
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp not in winner_by_fp:
                winner_by_fp[fp] = a.id
        last = rows[-1]
        internal = (last.published_at, last.id)
        if len(rows) < batch or scanned >= max_scan_rows:
            break
    return frozenset(winner_by_fp.values())


def _public_industry_ids_for_slug(db: Session, ind: Industry) -> list[int]:
    """前台 industry_slug=ai 时同时收录 taxonomy「domains」下连接器入库文章。"""
    ids = [ind.id]
    if (ind.slug or "").strip().lower() == "ai":
        dom = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
        if dom and dom.id not in ids:
            ids.append(dom.id)
    return ids


def _row_feed_lane(a: Article) -> str:
    """公开列表/详情泳道：可安装应用 vs 资讯（见 ``feed_lane_for_article``）。

    曾用 LLM 写入的 product_articles.feed_kind 若与规则不一致，会导致两页串稿；
    公开站以 connector key + 正文规则为准。
    """
    return art.feed_lane_for_article(
        art.admin_source_key(a.third_party_source),
        title=a.title or "",
        summary=a.summary or "",
        ai_categories_json=getattr(a, "ai_categories_json", None),
        ai_tabs_json=getattr(a, "ai_tabs_json", None),
    )


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


def _feed_day_inner_order_by(feed: str):
    """按 UTC 日分页时，**同一天内**条目的 SQL 排序（不改变按 published_at 收集日历日的扫描逻辑）。"""
    if feed == "apps":
        return (desc(Article.heat_score), desc(Article.updated_at), desc(Article.published_at), desc(Article.id))
    return (desc(Article.published_at), desc(Article.id))


def _apply_published_keyset(stmt: Select, pos: tuple[datetime, int] | None) -> Select:
    if not pos:
        return stmt
    pub_c, id_c = pos
    return stmt.where(
        or_(
            Article.published_at < pub_c,
            and_(Article.published_at == pub_c, Article.id < id_c),
        )
    )


def _feed_card_from_article(a: Article, *, label_by_key: dict[str, str]) -> dict:
    ak = art.admin_source_key(a.third_party_source)
    row_lane = _row_feed_lane(a)
    plat = label_by_key.get(ak) or (ak.replace("_", " ").title() if ak else "")
    tabs_parsed = art.parse_article_tabs_json(getattr(a, "ai_tabs_json", None))
    tab_summaries = (
        [{"label": x["label"], "summary": (x["summary"] or "")[:280]} for x in tabs_parsed[:6]] if tabs_parsed else []
    )
    cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    fp = art.display_fingerprint(a.title, a.summary or "")
    return {
        "id": a.id,
        "slug": a.slug,
        "title": a.title,
        "summary": a.summary,
        "segment_id": a.segment_id,
        "content_type": a.content_type,
        "third_party_source": a.third_party_source,
        "connector_sync_log_id": getattr(a, "connector_sync_log_id", None),
        "source_external_id": getattr(a, "source_external_id", None),
        "published_at": a.published_at.isoformat() + "Z" if a.published_at else None,
        "updated_at": a.updated_at.isoformat() + "Z" if a.updated_at else None,
        "heat_score": float(getattr(a, "heat_score", 0.0) or 0.0),
        "fingerprint": fp,
        "platform_label": plat,
        "admin_source_key": ak,
        "feed_kind": row_lane,
        "categories": cats_list,
        "tab_summaries": tab_summaries,
    }


def _collect_ordered_days_for_feed(
    db: Session,
    base_q: Select,
    *,
    feed: str,
    cat_filter: str | None,
    search_n: str | None,
    winner_ids: frozenset[int],
    max_scan: int = 40000,
    batch: int = 400,
) -> tuple[list[date], bool]:
    """按 published_at 从新到旧扫描，收集首次出现的 UTC 日历日（仅统计通过泳道/类别/搜索筛选的文章）。"""
    ordered_days: list[date] = []
    seen: set[date] = set()
    internal: tuple[datetime, int] | None = None
    scanned = 0

    while scanned < max_scan:
        q2 = _apply_published_keyset(base_q, internal).order_by(desc(Article.published_at), desc(Article.id))
        rows = db.scalars(q2.limit(batch)).all()
        if not rows:
            break
        for a in rows:
            scanned += 1
            if _row_feed_lane(a) != feed:
                continue
            cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
            if cat_filter and cats_list and cats_list[0] != cat_filter:
                continue
            if search_n and not _article_title_summary_matches(a, search_n):
                continue
            if a.id not in winner_ids:
                continue
            d = a.published_at.date()
            if d not in seen:
                seen.add(d)
                ordered_days.append(d)
            if scanned >= max_scan:
                break
        last = rows[-1]
        internal = (last.published_at, last.id)
        if len(rows) < batch:
            break
        if scanned >= max_scan:
            break

    truncated = scanned >= max_scan
    return ordered_days, truncated


def list_articles_feed_by_day_page(
    db: Session,
    *,
    feed: str,
    industry_slug: str,
    segment_id: int | None,
    segment_ids: list[int] | None,
    page: int,
    published_within_days: int | None,
    published_on_latest_day: bool,
    category: str | None = None,
    search: str | None = None,
    days_per_page: int = DAYS_PER_PAGE_DEFAULT,
) -> dict:
    """按 UTC 自然日分页：每页连续 ``days_per_page`` 个有内容的日历日（默认 3），第 1 页为最新一段。"""
    cat_filter = (category or "").strip() or None
    n = normalize_feed_search(search)

    ind, q = _base_article_query_for_scope(
        db,
        industry_slug=industry_slug,
        segment_id=segment_id,
        segment_ids=segment_ids,
        published_within_days=published_within_days,
        published_on_latest_day=published_on_latest_day,
    )
    dpp = max(1, min(int(days_per_page or DAYS_PER_PAGE_DEFAULT), 31))
    empty = {
        "items": [],
        "paginate_by": "day",
        "page": page,
        "total_pages": 0,
        "days_per_page": dpp,
        "day_utc": None,
        "day_utc_end": None,
        "has_prev": False,
        "has_next": False,
        "days_scan_truncated": False,
    }
    if not ind:
        return empty

    label_by_key = _admin_source_label_by_key(db)

    winner_ids = _build_feed_fingerprint_winner_ids(db, q, feed=feed, cat_filter=cat_filter, search_n=n)

    ordered_days, truncated = _collect_ordered_days_for_feed(
        db, q, feed=feed, cat_filter=cat_filter, search_n=n, winner_ids=winner_ids
    )
    n_days = len(ordered_days)
    total_pages = (n_days + dpp - 1) // dpp if n_days else 0
    if total_pages == 0:
        return {**empty, "days_scan_truncated": truncated}

    safe_page = max(1, page)
    if safe_page > total_pages:
        return {
            "items": [],
            "paginate_by": "day",
            "page": safe_page,
            "total_pages": total_pages,
            "days_per_page": dpp,
            "day_utc": None,
            "day_utc_end": None,
            "has_prev": total_pages > 0,
            "has_next": False,
            "days_scan_truncated": truncated,
        }

    start_i = (safe_page - 1) * dpp
    chunk_days = ordered_days[start_i : start_i + dpp]
    newest_day = chunk_days[0]
    oldest_day = chunk_days[-1]
    day_start = datetime.combine(oldest_day, datetime.min.time())
    day_end = datetime.combine(newest_day, datetime.min.time()) + timedelta(days=1)

    q_day = q.where(Article.published_at >= day_start, Article.published_at < day_end)
    rows = db.scalars(q_day.order_by(*_feed_day_inner_order_by(feed))).all()

    seen_fp: set[str] = set()
    out: list[dict] = []
    for a in rows:
        if _row_feed_lane(a) != feed:
            continue
        cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
        if cat_filter and cats_list and cats_list[0] != cat_filter:
            continue
        if n and not _article_title_summary_matches(a, n):
            continue
        if a.id not in winner_ids:
            continue
        fp = art.display_fingerprint(a.title, a.summary or "")
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        out.append(_feed_card_from_article(a, label_by_key=label_by_key))

    return {
        "items": out,
        "paginate_by": "day",
        "page": safe_page,
        "total_pages": total_pages,
        "days_per_page": dpp,
        "day_utc": newest_day.isoformat(),
        "day_utc_end": oldest_day.isoformat(),
        "has_prev": safe_page > 1,
        "has_next": safe_page < total_pages,
        "days_scan_truncated": truncated,
    }


def list_articles_feed_by_heat_top(
    db: Session,
    *,
    feed: str,
    industry_slug: str,
    segment_id: int | None,
    segment_ids: list[int] | None,
    published_within_days: int | None,
    published_on_latest_day: bool,
    category: str | None = None,
    search: str | None = None,
    heat_offset: int = 0,
    heat_page_size: int = HEAT_PAGE_DEFAULT,
    heat_max_ranked: int = HEAT_FEED_MAX,
) -> dict:
    """
    与「按日」相同的时间窗与筛选；在展示指纹胜者集合内按 ``heat_score`` 排序，
    先截取至多 ``heat_max_ranked`` 条作为热度池，再按 ``heat_offset`` + ``heat_page_size`` 分页返回（供前端触底懒加载）。
    """
    cat_filter = (category or "").strip() or None
    n = normalize_feed_search(search)
    ps = max(1, min(int(heat_page_size or HEAT_PAGE_DEFAULT), HEAT_PAGE_MAX))
    off = max(0, int(heat_offset or 0))
    cap = max(1, min(int(heat_max_ranked or HEAT_FEED_MAX), HEAT_FEED_MAX))

    ind, q = _base_article_query_for_scope(
        db,
        industry_slug=industry_slug,
        segment_id=segment_id,
        segment_ids=segment_ids,
        published_within_days=published_within_days,
        published_on_latest_day=published_on_latest_day,
    )
    empty = {
        "items": [],
        "paginate_by": "heat",
        "offset": off,
        "page_size": ps,
        "heat_max": cap,
        "total": 0,
        "has_more": False,
    }
    if not ind:
        return empty

    label_by_key = _admin_source_label_by_key(db)
    winner_ids = _build_feed_fingerprint_winner_ids(db, q, feed=feed, cat_filter=cat_filter, search_n=n)
    if not winner_ids:
        return empty

    wc = q.whereclause
    pool_where = and_(wc, Article.id.in_(winner_ids)) if wc is not None else Article.id.in_(winner_ids)
    ranked_pool = (
        select(Article.id.label("rid"))
        .where(pool_where)
        .order_by(
            desc(Article.heat_score),
            desc(Article.updated_at),
            desc(Article.published_at),
            desc(Article.id),
        )
        .limit(cap)
        .subquery()
    )
    total_ranked = int(db.scalar(select(func.count()).select_from(ranked_pool)) or 0)
    if total_ranked == 0:
        return empty

    slice_ids = list(
        db.scalars(select(ranked_pool.c.rid).offset(off).limit(ps)).all(),
    )
    if not slice_ids:
        return {
            **empty,
            "total": total_ranked,
            "has_more": off < total_ranked,
        }

    rows = db.scalars(select(Article).where(Article.id.in_(slice_ids))).all()
    pos = {i: p for p, i in enumerate(slice_ids)}
    rows_sorted = sorted(rows, key=lambda a: pos[a.id])
    out = [_feed_card_from_article(a, label_by_key=label_by_key) for a in rows_sorted]
    has_more = off + len(out) < total_ranked
    return {
        "items": out,
        "paginate_by": "heat",
        "offset": off,
        "page_size": ps,
        "heat_max": cap,
        "total": total_ranked,
        "has_more": has_more,
    }


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
    winner_ids = _build_feed_fingerprint_winner_ids(db, q, feed=feed, cat_filter=None, search_n=n)
    rows = db.scalars(q.order_by(desc(Article.published_at), desc(Article.id)).limit(4000)).all()
    ctr: Counter[str] = Counter()
    for a in rows:
        if _row_feed_lane(a) != feed:
            continue
        if n and not _article_title_summary_matches(a, n):
            continue
        if a.id not in winner_ids:
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
    label_by_key = _admin_source_label_by_key(db)

    winner_ids = _build_feed_fingerprint_winner_ids(db, q, feed=feed, cat_filter=cat_filter, search_n=n)

    exclude = art.parse_exclude_fingerprints(exclude_fp)
    seen_fp: set[str] = set(exclude)
    out: list[dict] = []
    internal = art.decode_feed_cursor(cursor)
    last_scanned: tuple[datetime, int] | None = None
    has_more = False

    while len(out) < page_size:
        q2 = _apply_published_keyset(q, internal).order_by(desc(Article.published_at), desc(Article.id))
        rows = db.scalars(q2.limit(scan_limit)).all()
        if not rows:
            break
        has_more = len(rows) >= scan_limit
        for a in rows:
            last_scanned = (a.published_at, a.id)
            row_lane = _row_feed_lane(a)
            if row_lane != feed:
                continue
            cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
            if cat_filter and cats_list and cats_list[0] != cat_filter:
                continue
            if n and not _article_title_summary_matches(a, n):
                continue
            if a.id not in winner_ids:
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            out.append(_feed_card_from_article(a, label_by_key=label_by_key))
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
        "updated_at": a.updated_at.isoformat() + "Z" if a.updated_at else None,
        "heat_score": float(getattr(a, "heat_score", 0.0) or 0.0),
        "connector_sync_log_id": getattr(a, "connector_sync_log_id", None),
        "source_external_id": getattr(a, "source_external_id", None),
        "categories": art.display_categories_for_article(getattr(a, "ai_categories_json", None)),
        "feed_kind": _row_feed_lane(a),
        "admin_source_key": ak,
        "tabs": tabs,
    }
