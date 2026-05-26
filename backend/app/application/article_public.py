from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import Select, and_, case, desc, func, or_, select
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


def normalize_source_filter(raw: str | None) -> str | None:
    s = (raw or "").strip().lower()
    return s or None


def _tier_filter_from_csv(raw: str | None) -> frozenset[str] | None:
    tiers = art.parse_replication_tiers_csv(raw)
    if not tiers:
        return None
    return frozenset(tiers)


GITHUB_CLONE_APPS_CATEGORY = "开源客户端(好抄)"


def _monetization_counts_as_apps_feed(a: Article) -> bool:
    """变现案例 / 已验证变现类，以及 Acquire、TAAFT 源条目纳入应用泳道展示。"""
    sk = art.admin_source_key(a.third_party_source)
    if sk in art.MONETIZATION_SOURCE_KEYS:
        return True
    cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    return bool(cats and cats[0] in art.MONETIZATION_APPS_CATEGORIES)


def _github_counts_as_apps_feed(a: Article) -> bool:
    """GitHub 客户端 Trending：公开「应用」泳道纳入 S/A 或「开源客户端(好抄)」类条目。"""
    if art.admin_source_key(a.third_party_source) != "github":
        return False
    cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    if cats and cats[0] == GITHUB_CLONE_APPS_CATEGORY:
        return True
    tier = (getattr(a, "replication_tier", None) or "").strip().upper()
    return tier in ("S", "A")


def _article_matches_public_feed(a: Article, feed: str) -> bool:
    """公开 feed=apps/news 泳道：apps 含可抄 GitHub 与变现向条目；news 与之去重。"""
    lane = _row_feed_lane(a)
    if feed == "apps":
        return lane == "apps" or _github_counts_as_apps_feed(a) or _monetization_counts_as_apps_feed(a)
    if feed == "news":
        if _github_counts_as_apps_feed(a) or _monetization_counts_as_apps_feed(a):
            return False
        return lane == "news"
    return lane == feed


def _feed_row_matches_list_filters(
    a: Article,
    *,
    feed: str,
    cat_filter: str | None,
    source_filter: str | None,
    search_n: str | None,
    tier_filter: frozenset[str] | None = None,
) -> bool:
    """与公开列表一致的泳道 / 类别 / 数据源 / 搜索 / 可复刻档位筛选。"""
    if not _article_matches_public_feed(a, feed):
        return False
    if source_filter and art.admin_source_key(a.third_party_source) != source_filter:
        return False
    cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    if cat_filter and cats_list and cats_list[0] != cat_filter:
        return False
    if tier_filter:
        t = (getattr(a, "replication_tier", None) or "").strip().upper()
        if t not in tier_filter:
            return False
    if search_n and not _article_title_summary_matches(a, search_n):
        return False
    return True


def _freshness_expr():
    return art.article_freshness_sql_expr()


def _freshness_at(a: Article) -> datetime:
    return art.article_freshness_for_row(a) or datetime.utcnow()


def _heat_order_by(*, sort_replicable: bool = False, sort_monetization: bool = False):
    fe = _freshness_expr()
    order: list = []
    if sort_monetization:
        order.append(
            case(
                (Article.ai_categories_json.like('%"变现案例"%'), 0),
                (Article.ai_categories_json.like('%"已验证变现"%'), 1),
                else_=2,
            )
        )
    if sort_replicable:
        order.append(
            case(
                (func.upper(Article.replication_tier) == "S", 0),
                (func.upper(Article.replication_tier) == "A", 1),
                (func.upper(Article.replication_tier) == "B", 2),
                else_=3,
            )
        )
    order.extend((desc(Article.heat_score), desc(fe), desc(Article.id)))
    return tuple(order)


def _build_feed_fingerprint_winner_ids(
    db: Session,
    base_q: Select,
    *,
    feed: str,
    cat_filter: str | None,
    source_filter: str | None,
    search_n: str | None,
    tier_filter: frozenset[str] | None = None,
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
        q2 = _apply_freshness_keyset(base_q, internal).order_by(desc(_freshness_expr()), desc(Article.id))
        rows = db.scalars(q2.limit(batch)).all()
        if not rows:
            break
        for a in rows:
            scanned += 1
            if scanned > max_scan_rows:
                break
            if not _feed_row_matches_list_filters(
                a,
                feed=feed,
                cat_filter=cat_filter,
                source_filter=source_filter,
                search_n=search_n,
                tier_filter=tier_filter,
            ):
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp not in winner_by_fp:
                winner_by_fp[fp] = a.id
        last = rows[-1]
        internal = (_freshness_at(last), last.id)
        if len(rows) < batch or scanned >= max_scan_rows:
            break
    return frozenset(winner_by_fp.values())


def _build_radar_source_fingerprint_winner_ids(
    db: Session,
    base_q: Select,
    *,
    source_key: str,
    max_scan_rows: int = 24_000,
    batch: int = 500,
) -> frozenset[int]:
    """首页雷达：按连接器源聚合，不按 apps/news 泳道规则过滤（GitHub 等默认在 news 泳道仍有稿）。"""
    sk = (source_key or "").strip().lower()
    if not sk:
        return frozenset()
    winner_by_fp: dict[str, int] = {}
    internal: tuple[datetime, int] | None = None
    scanned = 0
    while scanned < max_scan_rows:
        q2 = _apply_freshness_keyset(base_q, internal).order_by(desc(_freshness_expr()), desc(Article.id))
        rows = db.scalars(q2.limit(batch)).all()
        if not rows:
            break
        for a in rows:
            scanned += 1
            if scanned > max_scan_rows:
                break
            if art.admin_source_key(a.third_party_source) != sk:
                continue
            fp = art.display_fingerprint(a.title, a.summary or "")
            if fp not in winner_by_fp:
                winner_by_fp[fp] = a.id
        last = rows[-1]
        internal = (_freshness_at(last), last.id)
        if len(rows) < batch or scanned >= max_scan_rows:
            break
    return frozenset(winner_by_fp.values())


def list_articles_home_radar_source_top(
    db: Session,
    *,
    industry_slug: str,
    source_key: str,
    published_within_days: int,
    published_on_latest_day: bool = False,
    limit: int = 12,
) -> list[dict]:
    """首页六路雷达：该数据源时间窗内热度 Top（与列表泳道规则解耦）。"""
    sk = normalize_source_filter(source_key)
    if not sk:
        return []
    lim = max(1, min(int(limit), 24))
    ind, q = _base_article_query_for_scope(
        db,
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=published_within_days,
        published_on_latest_day=published_on_latest_day,
    )
    if not ind:
        return []
    q = q.where(Article.third_party_source.ilike(f"{sk}%"))
    winner_ids = _build_radar_source_fingerprint_winner_ids(db, q, source_key=sk)
    if not winner_ids:
        return []
    label_by_key = _admin_source_label_by_key(db)
    rows = db.scalars(
        select(Article).where(Article.id.in_(winner_ids)).order_by(*_heat_order_by()).limit(lim)
    ).all()
    return [_feed_card_from_article(a, label_by_key=label_by_key) for a in rows]


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
        # 「最新一日」= 自然日「今天」（UTC），按展示时效（入库/最近同步）而非仅源站发布时间。
        now = datetime.utcnow()
        utc_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_day_end = utc_day_start + timedelta(days=1)

    article_industry_ids = (
        _public_industry_ids_for_slug(db, ind) if segment_id is None and segment_ids is None else [ind.id]
    )
    fe = _freshness_expr()
    q = select(Article).where(
        Article.industry_id.in_(article_industry_ids),
        Article.status == "published",
        fe.isnot(None),
    )
    if segment_id is not None:
        q = q.where(Article.segment_id == segment_id)
    elif segment_ids is not None:
        q = q.where(Article.segment_id.in_(segment_ids))
    if since_pub is not None:
        q = q.where(fe >= since_pub)
    elif utc_day_start is not None and utc_day_end is not None:
        q = q.where(fe >= utc_day_start, fe < utc_day_end)

    return ind, q


def _feed_day_inner_order_by(feed: str):
    """按 UTC 日分页时，**同一天内**条目的 SQL 排序（日历日收集亦按展示时效）。"""
    fe = _freshness_expr()
    if feed == "apps":
        return (desc(Article.heat_score), desc(fe), desc(Article.id))
    return (desc(fe), desc(Article.id))


def _apply_freshness_keyset(stmt: Select, pos: tuple[datetime, int] | None) -> Select:
    if not pos:
        return stmt
    fresh_c, id_c = pos
    fe = _freshness_expr()
    return stmt.where(
        or_(
            fe < fresh_c,
            and_(fe == fresh_c, Article.id < id_c),
        )
    )


def _feed_card_from_article(a: Article, *, label_by_key: dict[str, str]) -> dict:
    ak = art.admin_source_key(a.third_party_source)
    row_lane = _row_feed_lane(a)
    plat = label_by_key.get(ak) or (ak.replace("_", " ").title() if ak else "")
    tabs_parsed = art.parse_article_tabs_json(getattr(a, "ai_tabs_json", None))
    tab_summaries = (
        [{"label": x["label"], "summary": (x["summary"] or "")[:420]} for x in tabs_parsed[:6]] if tabs_parsed else []
    )
    tab_labels = art.required_feed_card_tab_labels(row_lane)
    desc_label = tab_labels[0]
    hi_label = tab_labels[-1]
    from ..text_display import markdown_to_plain_preview

    card_description = markdown_to_plain_preview((a.summary or "")[:960], max_len=960)
    card_highlights = ""
    if tabs_parsed:
        for x in tabs_parsed:
            lab = (x.get("label") or "").strip()
            sm = (x.get("summary") or "").strip()
            body_plain = markdown_to_plain_preview((x.get("body_md") or "")[:400], max_len=200)
            if lab == desc_label and sm:
                card_description = markdown_to_plain_preview(sm, max_len=960) or body_plain
            elif art.feed_card_highlights_tab_label(lab):
                card_highlights = markdown_to_plain_preview(sm, max_len=200) or body_plain
    cats_list = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    fp = art.display_fingerprint(a.title, a.summary or "")
    display_dt = art.article_freshness_for_row(a)
    card: dict = {
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
        "display_at": display_dt.isoformat() + "Z" if display_dt else None,
        "engagement_stars_total": getattr(a, "engagement_stars_total", None),
        "engagement_stars_today": getattr(a, "engagement_stars_today", None),
        "heat_score": float(getattr(a, "heat_score", 0.0) or 0.0),
        "fingerprint": fp,
        "platform_label": plat,
        "admin_source_key": ak,
        "feed_kind": row_lane,
        "categories": cats_list,
        "tab_summaries": tab_summaries,
        "card_description": card_description,
        "card_highlights": card_highlights,
        "cover_image_url": (getattr(a, "cover_image_url", None) or "")[:2048] or None,
        "replication_tier": getattr(a, "replication_tier", None),
    }
    repl = art.parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if repl:
        from ..domain.replication_analysis import replication_analysis_public_view

        card["replication_analysis"] = replication_analysis_public_view(repl)
        card["replication_mvp_hours"] = art.estimated_hours_mvp_label(repl)
    return card


def _collect_ordered_days_for_feed(
    db: Session,
    base_q: Select,
    *,
    feed: str,
    cat_filter: str | None,
    source_filter: str | None,
    search_n: str | None,
    winner_ids: frozenset[int],
    tier_filter: frozenset[str] | None = None,
    max_scan: int = 40000,
    batch: int = 400,
) -> tuple[list[date], bool]:
    """按展示时效从新到旧扫描，收集首次出现的 UTC 日历日（仅统计通过泳道/类别/搜索筛选的文章）。"""
    ordered_days: list[date] = []
    seen: set[date] = set()
    internal: tuple[datetime, int] | None = None
    scanned = 0

    while scanned < max_scan:
        q2 = _apply_freshness_keyset(base_q, internal).order_by(desc(_freshness_expr()), desc(Article.id))
        rows = db.scalars(q2.limit(batch)).all()
        if not rows:
            break
        for a in rows:
            scanned += 1
            if not _feed_row_matches_list_filters(
                a,
                feed=feed,
                cat_filter=cat_filter,
                source_filter=source_filter,
                search_n=search_n,
                tier_filter=tier_filter,
            ):
                continue
            if a.id not in winner_ids:
                continue
            fresh = _freshness_at(a)
            d = fresh.date()
            if d not in seen:
                seen.add(d)
                ordered_days.append(d)
            if scanned >= max_scan:
                break
        last = rows[-1]
        internal = (_freshness_at(last), last.id)
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
    source: str | None = None,
    search: str | None = None,
    days_per_page: int = DAYS_PER_PAGE_DEFAULT,
    replication_tiers: str | None = None,
) -> dict:
    """按 UTC 自然日分页：每页连续 ``days_per_page`` 个有内容的日历日（默认 3），第 1 页为最新一段。"""
    cat_filter = (category or "").strip() or None
    source_filter = normalize_source_filter(source)
    n = normalize_feed_search(search)
    tier_filter = _tier_filter_from_csv(replication_tiers)

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

    winner_ids = _build_feed_fingerprint_winner_ids(
        db,
        q,
        feed=feed,
        cat_filter=cat_filter,
        source_filter=source_filter,
        search_n=n,
        tier_filter=tier_filter,
    )

    ordered_days, truncated = _collect_ordered_days_for_feed(
        db,
        q,
        feed=feed,
        cat_filter=cat_filter,
        source_filter=source_filter,
        search_n=n,
        winner_ids=winner_ids,
        tier_filter=tier_filter,
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

    fe = _freshness_expr()
    q_day = q.where(fe >= day_start, fe < day_end)
    rows = db.scalars(q_day.order_by(*_feed_day_inner_order_by(feed))).all()

    seen_fp: set[str] = set()
    out: list[dict] = []
    for a in rows:
        if not _feed_row_matches_list_filters(
            a,
            feed=feed,
            cat_filter=cat_filter,
            source_filter=source_filter,
            search_n=n,
            tier_filter=tier_filter,
        ):
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
    source: str | None = None,
    search: str | None = None,
    heat_offset: int = 0,
    heat_page_size: int = HEAT_PAGE_DEFAULT,
    heat_max_ranked: int = HEAT_FEED_MAX,
    replication_tiers: str | None = None,
    sort_replicable: bool = False,
    sort_monetization: bool = False,
) -> dict:
    """
    与「按日」相同的时间窗与筛选；在展示指纹胜者集合内排序（可选 S/A 优先），
    先截取至多 ``heat_max_ranked`` 条作为热度池，再分页返回。
    """
    cat_filter = (category or "").strip() or None
    source_filter = normalize_source_filter(source)
    n = normalize_feed_search(search)
    tier_filter = _tier_filter_from_csv(replication_tiers)
    sort_rep = bool(sort_replicable or tier_filter)
    sort_mon = bool(sort_monetization or (cat_filter in art.MONETIZATION_APPS_CATEGORIES))
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
    winner_ids = _build_feed_fingerprint_winner_ids(
        db,
        q,
        feed=feed,
        cat_filter=cat_filter,
        source_filter=source_filter,
        search_n=n,
        tier_filter=tier_filter,
    )
    if not winner_ids:
        return empty

    wc = q.whereclause
    pool_where = and_(wc, Article.id.in_(winner_ids)) if wc is not None else Article.id.in_(winner_ids)
    ranked_pool = (
        select(Article.id.label("rid"))
        .where(pool_where)
        .order_by(*_heat_order_by(sort_replicable=sort_rep, sort_monetization=sort_mon))
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
    source: str | None = None,
    search: str | None = None,
    replication_tiers: str | None = None,
) -> list[dict]:
    """当前时间/板块范围内、指定泳道下，由 AI categories 聚合出的可选筛选项。"""
    tier_filter = _tier_filter_from_csv(replication_tiers)
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
    source_filter = normalize_source_filter(source)
    n = normalize_feed_search(search)
    winner_ids = _build_feed_fingerprint_winner_ids(
        db,
        q,
        feed=feed,
        cat_filter=None,
        source_filter=source_filter,
        search_n=n,
        tier_filter=tier_filter,
    )
    rows = db.scalars(q.order_by(desc(_freshness_expr()), desc(Article.id)).limit(4000)).all()
    ctr: Counter[str] = Counter()
    for a in rows:
        if not _feed_row_matches_list_filters(
            a,
            feed=feed,
            cat_filter=None,
            source_filter=source_filter,
            search_n=n,
            tier_filter=tier_filter,
        ):
            continue
        if a.id not in winner_ids:
            continue
        primary = art.primary_canonical_from_raw_labels(
            art.parse_category_labels_json(getattr(a, "ai_categories_json", None))
        )
        ctr[primary] += 1
    return [{"label": lab, "count": int(ctr[lab])} for lab in art.FACET_DISPLAY_ORDER if ctr.get(lab, 0) > 0]


def list_article_source_facets(
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
    replication_tiers: str | None = None,
) -> list[dict]:
    """当前时间/板块范围内、指定泳道下，按 admin_source_key 聚合的数据源筛选项。"""
    tier_filter = _tier_filter_from_csv(replication_tiers)
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
    cat_filter = (category or "").strip() or None
    n = normalize_feed_search(search)
    label_by_key = _admin_source_label_by_key(db)
    winner_ids = _build_feed_fingerprint_winner_ids(
        db,
        q,
        feed=feed,
        cat_filter=cat_filter,
        source_filter=None,
        search_n=n,
        tier_filter=tier_filter,
    )
    rows = db.scalars(q.order_by(desc(_freshness_expr()), desc(Article.id)).limit(4000)).all()
    ctr: Counter[str] = Counter()
    for a in rows:
        if not _feed_row_matches_list_filters(
            a,
            feed=feed,
            cat_filter=cat_filter,
            source_filter=None,
            search_n=n,
            tier_filter=tier_filter,
        ):
            continue
        if a.id not in winner_ids:
            continue
        ak = art.admin_source_key(a.third_party_source)
        if not ak or ak == "未绑定数据源":
            continue
        ctr[ak] += 1
    out: list[dict] = []
    for key, count in ctr.most_common():
        label = label_by_key.get(key) or key.replace("_", " ").title()
        out.append({"key": key, "label": label, "count": int(count)})
    return out


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
    source: str | None = None,
    search: str | None = None,
    replication_tiers: str | None = None,
) -> dict:
    scan_limit = 280
    cat_filter = (category or "").strip() or None
    source_filter = normalize_source_filter(source)
    tier_filter = _tier_filter_from_csv(replication_tiers)

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

    winner_ids = _build_feed_fingerprint_winner_ids(
        db,
        q,
        feed=feed,
        cat_filter=cat_filter,
        source_filter=source_filter,
        search_n=n,
        tier_filter=tier_filter,
    )

    exclude = art.parse_exclude_fingerprints(exclude_fp)
    seen_fp: set[str] = set(exclude)
    out: list[dict] = []
    internal = art.decode_feed_cursor(cursor)
    last_scanned: tuple[datetime, int] | None = None
    has_more = False

    while len(out) < page_size:
        q2 = _apply_freshness_keyset(q, internal).order_by(desc(_freshness_expr()), desc(Article.id))
        rows = db.scalars(q2.limit(scan_limit)).all()
        if not rows:
            break
        has_more = len(rows) >= scan_limit
        for a in rows:
            last_scanned = (_freshness_at(a), a.id)
            if not _feed_row_matches_list_filters(
                a,
                feed=feed,
                cat_filter=cat_filter,
                source_filter=source_filter,
                search_n=n,
                tier_filter=tier_filter,
            ):
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
    lane = _row_feed_lane(a)
    label_by_key = _admin_source_label_by_key(db)
    plat = label_by_key.get(ak) or (ak.replace("_", " ").title() if ak else "")
    tabs = art.parse_article_tabs_json(getattr(a, "ai_tabs_json", None))
    src_url = (getattr(a, "source_original_url", None) or "")[:2048] or None
    if tabs and src_url:
        tabs = art.enrich_published_tabs_with_source_url(
            tabs,
            source_original_url=src_url,
            admin_source_key=ak,
        )
    if not tabs and (a.body or "").strip():
        tabs = [
            {
                "label": "全文",
                "summary": (a.summary or "")[:400] or "正文",
                "body_md": (a.body or "").strip(),
            }
        ]
    out: dict = {
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
        "display_at": (lambda _d: _d.isoformat() + "Z" if _d else None)(art.article_freshness_for_row(a)),
        "engagement_stars_total": getattr(a, "engagement_stars_total", None),
        "engagement_stars_today": getattr(a, "engagement_stars_today", None),
        "heat_score": float(getattr(a, "heat_score", 0.0) or 0.0),
        "connector_sync_log_id": getattr(a, "connector_sync_log_id", None),
        "source_external_id": getattr(a, "source_external_id", None),
        "source_original_url": src_url,
        "categories": art.display_categories_for_article(getattr(a, "ai_categories_json", None)),
        "feed_kind": lane,
        "admin_source_key": ak,
        "platform_label": plat,
        "detail_profile": art.article_detail_profile(ak, lane),
        "cover_image_url": (getattr(a, "cover_image_url", None) or "")[:2048] or None,
        "tabs": tabs,
        "replication_tier": getattr(a, "replication_tier", None),
    }
    repl = art.parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if repl:
        from ..domain.replication_analysis import replication_analysis_public_view

        out["replication_analysis"] = replication_analysis_public_view(repl)
    return out
