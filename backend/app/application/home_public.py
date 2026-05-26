"""首页 AI 趋势概览：基于已发布文章的真实统计（非演示曲线）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..domain.articles import FEED_APPS_KEYS
from ..product_models import Article, Industry

# 首页「亮点应用」：S/A 优先展示；不足时用 B 档补足条数（见 list_highlight_replicable_apps）
HOME_REPLICABLE_TIERS: tuple[str, ...] = ("S", "A")
HOME_REPLICABLE_HIGHLIGHT_DEFAULT = 4
HOME_MONETIZATION_HIGHLIGHT_DEFAULT = 4


def _industry_article_ids(db: Session, *, industry_slug: str) -> list[int]:
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug.strip().lower()))
    if not ind:
        return []
    from .article_public import _public_industry_ids_for_slug

    return _public_industry_ids_for_slug(db, ind)


def _apps_source_clause():
    return or_(*[Article.third_party_source.ilike(f"{k}%") for k in FEED_APPS_KEYS])


def _news_source_clause():
    return or_(Article.third_party_source.is_(None), ~_apps_source_clause())


def _growth_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round((current - previous) / previous * 100.0, 1)


def get_home_trend_overview(
    db: Session,
    *,
    industry_slug: str = "ai",
    sparkline_days: int = 14,
    period_days: int = 30,
) -> dict:
    """
    返回首页趋势图与侧栏统计。

    - ``sparkline``: 近 N 天每日已发布文章数（UTC 自然日，含资讯+应用）
    - ``apps_count`` / ``news_count``: 近 ``period_days`` 天内应用泳道 / 资讯泳道文章数
    - ``*_growth_pct``: 与上一段等长周期对比的周环比式增幅（%），无基期时为 null
    """
    days = max(2, min(int(sparkline_days), 90))
    period = max(1, min(int(period_days), 365))
    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    empty = {
        "sparkline": [{"day": d, "count": 0} for d in _day_range_utc(days)],
        "apps_count": 0,
        "news_count": 0,
        "apps_growth_pct": None,
        "news_growth_pct": None,
    }
    if not industry_ids:
        return empty

    now = datetime.utcnow()
    fe = art.article_freshness_sql_expr()
    base = and_(
        Article.industry_id.in_(industry_ids),
        Article.status == "published",
        fe.isnot(None),
    )

    spark_since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_col = art.published_calendar_day(db)
    rows = db.execute(
        select(day_col.label("d"), func.count(Article.id))
        .where(base, fe >= spark_since)
        .group_by(day_col)
        .order_by(day_col)
    ).all()
    by_day = {str(r.d): int(r[1]) for r in rows if r.d is not None}
    sparkline = [{"day": d, "count": by_day.get(d, 0)} for d in _day_range_utc(days, end=now)]

    cur_since = now - timedelta(days=period)
    prev_since = now - timedelta(days=period * 2)

    def _count(extra) -> int:
        return int(
            db.scalar(select(func.count()).select_from(Article).where(base, extra, fe >= cur_since)) or 0
        )

    def _count_prev(extra) -> int:
        return int(
            db.scalar(
                select(func.count()).select_from(Article).where(
                    base,
                    extra,
                    fe >= prev_since,
                    fe < cur_since,
                )
            )
            or 0
        )

    apps_cur = _count(_apps_source_clause())
    apps_prev = _count_prev(_apps_source_clause())
    news_cur = _count(_news_source_clause())
    news_prev = _count_prev(_news_source_clause())

    return {
        "sparkline": sparkline,
        "apps_count": apps_cur,
        "news_count": news_cur,
        "apps_growth_pct": _growth_pct(apps_cur, apps_prev),
        "news_growth_pct": _growth_pct(news_cur, news_prev),
    }


HOME_PICKS_MIN_TITLE_LEN = 6
HOME_PICKS_MIN_SUMMARY_LEN = 36
HOME_PICKS_MIN_HEAT = 72.0

from ..services import ACTIVE_ADMIN_SOURCE_KEYS

HOME_MAIN_SOURCE_KEYS: tuple[str, ...] = ACTIVE_ADMIN_SOURCE_KEYS

HOME_MAIN_SOURCE_PRESET_LABELS: dict[str, str] = {
    "github": "GitHub（客户端）",
    "product_hunt": "Product Hunt",
    "hacker_news": "Hacker News",
    "newsapi": "NewsAPI",
    "thenewsapi": "TheNewsAPI",
    "acquire": "Acquire（AI 资产）",
}

HOME_RADAR_APPS_KEYS: frozenset[str] = frozenset({"github", "product_hunt", "acquire"})
HOME_RADAR_NEWS_KEYS: frozenset[str] = frozenset({"hacker_news", "newsapi", "thenewsapi"})


def _home_pick_quality_ok(item: dict) -> bool:
    title = str(item.get("title") or "").strip()
    summary = str(item.get("card_description") or item.get("summary") or "").strip()
    heat = float(item.get("heat_score") or 0.0)
    if len(title) < HOME_PICKS_MIN_TITLE_LEN:
        return False
    if len(summary) < HOME_PICKS_MIN_SUMMARY_LEN:
        return False
    if heat < HOME_PICKS_MIN_HEAT:
        return False
    return True


def _home_pick_relaxed_ok(item: dict) -> bool:
    """质量门槛未达标时仍可用于首页展示的最低条件。"""
    title = str(item.get("title") or "").strip()
    if len(title) < 4:
        return False
    summary = str(item.get("card_description") or item.get("summary") or "").strip()
    return bool(summary) or float(item.get("heat_score") or 0.0) > 0


def _article_ids(items: list[dict]) -> set[int]:
    out: set[int] = set()
    for it in items:
        aid = it.get("id")
        if aid is not None:
            out.add(int(aid))
    return out


def _exclude_article_ids(items: list[dict], exclude: set[int]) -> list[dict]:
    if not exclude:
        return list(items)
    return [it for it in items if it.get("id") is not None and int(it["id"]) not in exclude]


def _select_home_picks(items: list[dict], limit: int) -> list[dict]:
    """
    优先高质量条目；不足时用热度榜回填，避免首页整块空白。
    """
    lim = max(1, int(limit))
    picked: list[dict] = []
    seen: set[int] = set()

    def _take(pool: list[dict]) -> None:
        for it in pool:
            if len(picked) >= lim:
                return
            aid = it.get("id")
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            picked.append(it)

    _take([x for x in items if _home_pick_quality_ok(x)])
    if len(picked) < lim:
        _take([x for x in items if _home_pick_relaxed_ok(x)])
    if len(picked) < lim:
        _take(items)
    return picked[:lim]


def get_home_editorial_picks(
    db: Session,
    *,
    industry_slug: str = "ai",
    news_limit: int = 8,
    apps_limit: int = 6,
    published_within_days: int = 30,
) -> dict:
    """
    首页编辑推荐：按统一 heat_score 取资讯/应用热门，而非「最新发布时间」。

    列表页默认仍可按日浏览；首页焦点位应对齐各平台真实热度 + 榜内名次。
    """
    from .article_public import list_articles_feed_by_heat_top

    nl = max(1, min(int(news_limit), 20))
    al = max(1, min(int(apps_limit), 20))
    days = max(1, min(int(published_within_days), 120))

    news_raw = list_articles_feed_by_heat_top(
        db,
        feed="news",
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=days,
        published_on_latest_day=False,
        heat_offset=0,
        heat_page_size=nl * 2,
        heat_max_ranked=min(100, nl * 4),
    )
    apps_raw = list_articles_feed_by_heat_top(
        db,
        feed="apps",
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=days,
        published_on_latest_day=False,
        heat_offset=0,
        heat_page_size=al * 2,
        heat_max_ranked=min(100, al * 4),
    )
    news_items = _select_home_picks(news_raw.get("items") or [], nl)
    apps_items = _select_home_picks(apps_raw.get("items") or [], al)
    return {
        "news": news_items,
        "apps": apps_items,
        "featured_news_id": news_items[0]["id"] if news_items else None,
        "pick_window_days": days,
        "scoring_note": "heat_score: platform engagement + connector rank + recency; weak snippet-length signal",
    }


def _home_radar_lanes_for_feed(
    db: Session,
    *,
    feed: str,
    industry_slug: str,
    published_within_days: int,
    exclude_ids: set[int],
) -> list[dict]:
    """首页六路雷达：按连接器源查热度 Top1（不按 apps/news 泳道规则），避免 GitHub 等仅有 news 泳道稿时显示空。"""
    from .article_public import _admin_source_label_by_key, list_articles_home_radar_source_top

    keys = [k for k in HOME_MAIN_SOURCE_KEYS if k in (HOME_RADAR_NEWS_KEYS if feed == "news" else HOME_RADAR_APPS_KEYS)]
    label_by_key = _admin_source_label_by_key(db)
    skip = exclude_ids or set()
    lanes: list[dict] = []
    for k in keys:
        candidates = list_articles_home_radar_source_top(
            db,
            industry_slug=industry_slug,
            source_key=k,
            published_within_days=published_within_days,
            published_on_latest_day=False,
            limit=16,
        )
        picked: list[dict] = []
        for it in candidates:
            aid = it.get("id")
            if aid is None or int(aid) in skip:
                continue
            picked.append(it)
            break
        # 该源在库内仅有 1 条且已被首页亮点占用时，仍展示于本路雷达，避免「有 PH 稿但 PH 列为空」
        if not picked and candidates:
            first = candidates[0]
            if first.get("id") is not None:
                picked.append(first)
        lanes.append(
            {
                "source_key": k,
                "source_label": label_by_key.get(k) or HOME_MAIN_SOURCE_PRESET_LABELS.get(k, k),
                "items": picked,
            }
        )
    return lanes


def _group_source_lanes(
    items: list[dict],
    *,
    per_source: int = 1,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """从已有 feed 卡片列表按源分桶（测试/兼容）；首页仪表盘请用 ``_home_radar_lanes_for_feed``。"""
    skip = exclude_ids or set()
    buckets: dict[str, list[dict]] = {k: [] for k in HOME_MAIN_SOURCE_KEYS}
    for it in items:
        aid = it.get("id")
        if aid is not None and int(aid) in skip:
            continue
        k = (it.get("admin_source_key") or "").strip().lower()
        if k not in buckets or len(buckets[k]) >= per_source:
            continue
        buckets[k].append(it)
    label_by_key: dict[str, str] = {}
    for it in items:
        k = (it.get("admin_source_key") or "").strip().lower()
        if k in HOME_MAIN_SOURCE_KEYS and k not in label_by_key:
            label_by_key[k] = (it.get("platform_label") or "").strip() or k.replace("_", " ").title()

    lanes: list[dict] = []
    for k in HOME_MAIN_SOURCE_KEYS:
        picked = buckets[k]
        lanes.append(
            {
                "source_key": k,
                "source_label": label_by_key.get(k) or HOME_MAIN_SOURCE_PRESET_LABELS.get(k, k.replace("_", " ").title()),
                "items": picked,
            }
        )
    return lanes


def _merge_source_facets(news_facets: list[dict], apps_facets: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in news_facets:
        k = (row.get("key") or "").strip()
        if not k:
            continue
        merged[k] = {
            "key": k,
            "label": row.get("label") or k,
            "news_count": int(row.get("count") or 0),
            "apps_count": 0,
        }
    for row in apps_facets:
        k = (row.get("key") or "").strip()
        if not k:
            continue
        if k in merged:
            merged[k]["apps_count"] = int(row.get("count") or 0)
        else:
            merged[k] = {
                "key": k,
                "label": row.get("label") or k,
                "news_count": 0,
                "apps_count": int(row.get("count") or 0),
            }
    out = list(merged.values())
    out.sort(key=lambda x: x["news_count"] + x["apps_count"], reverse=True)
    return out


def _pick_highlight_replicable_articles(
    db: Session,
    *,
    industry_ids: list[int],
    since: datetime,
    limit: int,
) -> list[Article]:
    """S → A → B 分档拉取，优先不同数据源，凑满首页可复刻展示条数。"""
    from .article_public import _article_matches_public_feed

    fe = art.article_freshness_sql_expr()
    tier_rank = case(
        (func.upper(Article.replication_tier) == "S", 0),
        (func.upper(Article.replication_tier) == "A", 1),
        (func.upper(Article.replication_tier) == "B", 2),
        else_=3,
    )
    picked: list[Article] = []
    seen_ids: set[int] = set()
    used_sources: set[str] = set()

    for tier_group in (("S",), ("A",), ("B",)):
        if len(picked) >= limit:
            break
        tier_set = {t.upper() for t in tier_group}
        scan_lim = max(limit * 10, 32)
        candidates = list(
            db.scalars(
                select(Article)
                .where(
                    Article.industry_id.in_(industry_ids),
                    Article.status == "published",
                    fe.isnot(None),
                    fe >= since,
                    func.upper(Article.replication_tier).in_(tier_set),
                )
                .order_by(
                    tier_rank,
                    desc(Article.heat_score),
                    desc(fe),
                    desc(Article.id),
                )
                .limit(scan_lim)
            ).all()
        )
        pool = [a for a in candidates if _article_matches_public_feed(a, "apps") and a.id not in seen_ids]
        for pass_diverse in (True, False):
            if len(picked) >= limit:
                break
            for a in pool:
                if len(picked) >= limit:
                    break
                if a.id in seen_ids:
                    continue
                sk = art.admin_source_key(a.third_party_source)
                if pass_diverse and sk and sk in used_sources:
                    continue
                picked.append(a)
                seen_ids.add(a.id)
                if sk:
                    used_sources.add(sk)
    return picked


def list_highlight_replicable_apps(
    db: Session,
    *,
    industry_slug: str = "ai",
    limit: int = HOME_REPLICABLE_HIGHLIGHT_DEFAULT,
    published_within_days: int = 30,
    tiers: tuple[str, ...] | None = None,
) -> list[dict]:
    """首页亮点应用：可复刻 S/A 优先，不足用 B 档补足（默认 4 条，多数据源）。"""
    del tiers  # 保留参数兼容；档位策略见 _pick_highlight_replicable_articles
    from .article_public import _admin_source_label_by_key, _feed_card_from_article

    lim = max(1, min(int(limit), 12))
    days = max(1, min(int(published_within_days), 120))

    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    if not industry_ids:
        return []

    since = datetime.utcnow() - timedelta(days=days)
    rows = _pick_highlight_replicable_articles(db, industry_ids=industry_ids, since=since, limit=lim)
    label_by_key = _admin_source_label_by_key(db)
    return [_feed_card_from_article(a, label_by_key=label_by_key) for a in rows]


def _monetization_highlight_rank(a: Article) -> int:
    """变现线索展示优先级：变现案例 > 已验证变现 > 变现源站 > 其它变现信号。"""
    raw = str(getattr(a, "ai_categories_json", None) or "")
    cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    if cats and cats[0] == "变现案例":
        return 0
    if cats and cats[0] == "已验证变现":
        return 1
    if '"变现案例"' in raw:
        return 1
    if '"已验证变现"' in raw:
        return 2
    if art.admin_source_key(a.third_party_source) in art.MONETIZATION_SOURCE_KEYS:
        return 3
    return 4


def _eligible_monetization_highlight(a: Article) -> bool:
    """首页变现线索入池：应用泳道 + 变现类/源站；JSON 含变现标签但主类为应用产品时也纳入。"""
    from .article_public import _article_matches_public_feed, _monetization_counts_as_apps_feed

    if not _article_matches_public_feed(a, "apps"):
        return False
    if _monetization_counts_as_apps_feed(a):
        return True
    raw = str(getattr(a, "ai_categories_json", None) or "")
    if '"变现案例"' in raw or '"已验证变现"' in raw:
        return True
    return art.admin_source_key(a.third_party_source) in art.MONETIZATION_SOURCE_KEYS


def _pick_highlight_monetization_articles(
    db: Session,
    *,
    industry_ids: list[int],
    since: datetime,
    limit: int,
) -> list[Article]:
    """分档拉取变现线索，优先不同数据源，凑满首页展示条数。"""
    fe = art.article_freshness_sql_expr()
    scan_lim = max(limit * 15, 48)
    candidates = list(
        db.scalars(
            select(Article)
            .where(
                Article.industry_id.in_(industry_ids),
                Article.status == "published",
                fe.isnot(None),
                fe >= since,
                (
                    Article.ai_categories_json.like('%"变现案例"%')
                    | Article.ai_categories_json.like('%"已验证变现"%')
                    | Article.ai_categories_json.like("%变现%")
                    | Article.third_party_source.ilike("acquire%")
                    | Article.third_party_source.ilike("taaft%")
                ),
            )
            .order_by(
                desc(Article.heat_score),
                desc(fe),
                desc(Article.id),
            )
            .limit(scan_lim)
        ).all()
    )
    pool = [a for a in candidates if _eligible_monetization_highlight(a)]
    pool.sort(
        key=lambda a: (
            _monetization_highlight_rank(a),
            -(float(a.heat_score or 0)),
            -(art.article_freshness_for_row(a) or since).timestamp(),
            -int(a.id),
        )
    )

    picked: list[Article] = []
    seen_ids: set[int] = set()
    used_sources: set[str] = set()
    ranks_present = sorted({_monetization_highlight_rank(a) for a in pool})

    for rank in ranks_present:
        if len(picked) >= limit:
            break
        tier_pool = [a for a in pool if _monetization_highlight_rank(a) == rank and a.id not in seen_ids]
        for pass_diverse in (True, False):
            if len(picked) >= limit:
                break
            for a in tier_pool:
                if len(picked) >= limit:
                    break
                if a.id in seen_ids:
                    continue
                sk = art.admin_source_key(a.third_party_source)
                if pass_diverse and sk and sk in used_sources:
                    continue
                picked.append(a)
                seen_ids.add(a.id)
                if sk:
                    used_sources.add(sk)

    if len(picked) < limit:
        for a in pool:
            if len(picked) >= limit:
                break
            if a.id in seen_ids:
                continue
            picked.append(a)
            seen_ids.add(a.id)
    return picked


def list_highlight_monetization_apps(
    db: Session,
    *,
    industry_slug: str = "ai",
    limit: int = HOME_MONETIZATION_HIGHLIGHT_DEFAULT,
    published_within_days: int = 30,
) -> list[dict]:
    """首页变现线索：变现案例优先，不足时按档位与热度补足（默认 4 条，多数据源）。"""
    from .article_public import _admin_source_label_by_key, _feed_card_from_article

    lim = max(1, min(int(limit), 8))
    days = max(1, min(int(published_within_days), 120))
    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    if not industry_ids:
        return []

    since = datetime.utcnow() - timedelta(days=days)
    rows = _pick_highlight_monetization_articles(db, industry_ids=industry_ids, since=since, limit=lim)
    label_by_key = _admin_source_label_by_key(db)
    return [_feed_card_from_article(a, label_by_key=label_by_key) for a in rows]


def get_home_dashboard(
    db: Session,
    *,
    industry_slug: str = "ai",
    news_limit: int = 8,
    apps_limit: int = 10,
    replicable_apps_limit: int = HOME_REPLICABLE_HIGHLIGHT_DEFAULT,
    monetization_apps_limit: int = HOME_MONETIZATION_HIGHLIGHT_DEFAULT,
    published_within_days: int = 30,
) -> dict:
    """
    首页一站式数据：亮点应用、资讯/应用精选、六路雷达、趋势与统计。

    雷达与精选区互斥 article id；每路按源单独查询，避免 NewsAPI/TheNewsAPI 等仅 1 篇且在精选时雷达误显空。
    """
    from .article_public import (
        list_article_category_facets,
        list_article_source_facets,
        list_articles_feed_by_heat_top,
    )

    days = max(1, min(int(published_within_days), 120))
    nl = max(1, min(int(news_limit), 20))
    al = max(1, min(int(apps_limit), 20))

    trend = get_home_trend_overview(
        db, industry_slug=industry_slug, sparkline_days=14, period_days=days
    )

    news_raw = list_articles_feed_by_heat_top(
        db,
        feed="news",
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=days,
        published_on_latest_day=False,
        heat_offset=0,
        heat_page_size=48,
        heat_max_ranked=96,
    )
    apps_raw = list_articles_feed_by_heat_top(
        db,
        feed="apps",
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=days,
        published_on_latest_day=False,
        heat_offset=0,
        heat_page_size=48,
        heat_max_ranked=96,
    )

    news_raw_items = news_raw.get("items") or []
    apps_raw_items = apps_raw.get("items") or []

    highlight_replicable_apps = list_highlight_replicable_apps(
        db,
        industry_slug=industry_slug,
        limit=replicable_apps_limit,
        published_within_days=days,
    )
    highlight_monetization_apps = list_highlight_monetization_apps(
        db,
        industry_slug=industry_slug,
        limit=monetization_apps_limit,
        published_within_days=days,
    )
    highlight_ids = _article_ids(highlight_replicable_apps) | _article_ids(highlight_monetization_apps)

    news_items = _select_home_picks(news_raw_items, nl)
    news_pick_ids = _article_ids(news_items)

    apps_items = _select_home_picks(_exclude_article_ids(apps_raw_items, highlight_ids), al)
    apps_pick_ids = _article_ids(apps_items)
    apps_radar_skip = highlight_ids | apps_pick_ids

    facet_kw = dict(
        industry_slug=industry_slug,
        segment_id=None,
        segment_ids=None,
        published_within_days=days,
        published_on_latest_day=False,
    )
    news_sources = list_article_source_facets(db, feed="news", **facet_kw)
    apps_sources = list_article_source_facets(db, feed="apps", **facet_kw)
    top_categories = list_article_category_facets(db, feed="news", **facet_kw)[:10]

    return {
        "news": news_items,
        "apps": apps_items,
        "highlight_replicable_apps": highlight_replicable_apps,
        "highlight_monetization_apps": highlight_monetization_apps,
        "featured_news_id": news_items[0]["id"] if news_items else None,
        "pick_window_days": days,
        "scoring_note": "heat_score: platform engagement + connector rank + recency; weak snippet-length signal",
        "trend": trend,
        "news_source_lanes": _home_radar_lanes_for_feed(
            db,
            feed="news",
            industry_slug=industry_slug,
            published_within_days=days,
            exclude_ids=news_pick_ids,
        ),
        "apps_source_lanes": _home_radar_lanes_for_feed(
            db,
            feed="apps",
            industry_slug=industry_slug,
            published_within_days=days,
            exclude_ids=apps_radar_skip,
        ),
        "source_facets": _merge_source_facets(news_sources, apps_sources),
        "top_categories": top_categories,
        "active_source_count": len(HOME_MAIN_SOURCE_KEYS),
    }


def _day_range_utc(n_days: int, *, end: datetime | None = None) -> list[str]:
    end_dt = (end or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[str] = []
    for i in range(n_days - 1, -1, -1):
        d = end_dt - timedelta(days=i)
        out.append(d.strftime("%Y-%m-%d"))
    return out
