"""首页 AI 趋势概览：基于已发布文章的真实统计（非演示曲线）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..domain.articles import FEED_APPS_KEYS
from ..product_models import Article, Industry


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
    base = and_(
        Article.industry_id.in_(industry_ids),
        Article.status == "published",
        Article.published_at.isnot(None),
    )

    spark_since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_col = func.date(Article.published_at)
    rows = db.execute(
        select(day_col.label("d"), func.count(Article.id))
        .where(base, Article.published_at >= spark_since)
        .group_by(day_col)
        .order_by(day_col)
    ).all()
    by_day = {str(r.d): int(r[1]) for r in rows if r.d is not None}
    sparkline = [{"day": d, "count": by_day.get(d, 0)} for d in _day_range_utc(days, end=now)]

    cur_since = now - timedelta(days=period)
    prev_since = now - timedelta(days=period * 2)

    def _count(extra) -> int:
        return int(
            db.scalar(select(func.count()).select_from(Article).where(base, extra, Article.published_at >= cur_since))
            or 0
        )

    def _count_prev(extra) -> int:
        return int(
            db.scalar(
                select(func.count()).select_from(Article).where(
                    base,
                    extra,
                    Article.published_at >= prev_since,
                    Article.published_at < cur_since,
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
        published_within_days=days,
        published_on_latest_day=False,
        heat_offset=0,
        heat_page_size=al * 2,
        heat_max_ranked=min(100, al * 4),
    )
    news_items = [x for x in (news_raw.get("items") or []) if _home_pick_quality_ok(x)][:nl]
    apps_items = [x for x in (apps_raw.get("items") or []) if _home_pick_quality_ok(x)][:al]
    return {
        "news": news_items,
        "apps": apps_items,
        "featured_news_id": news_items[0]["id"] if news_items else None,
        "pick_window_days": days,
        "scoring_note": "heat_score: platform engagement + connector rank + recency; weak snippet-length signal",
    }


def _day_range_utc(n_days: int, *, end: datetime | None = None) -> list[str]:
    end_dt = (end or datetime.utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[str] = []
    for i in range(n_days - 1, -1, -1):
        d = end_dt - timedelta(days=i)
        out.append(d.strftime("%Y-%m-%d"))
    return out
