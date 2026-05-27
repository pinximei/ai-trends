from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...application import article_public as article_app
from ...core.envelope import success
from ...db import get_db
from ...domain.articles import parse_segment_ids_csv

router = APIRouter(tags=["public-articles"])


@router.get("/articles/categories")
def list_article_categories(
    feed: str = Query(..., pattern="^(news|apps)$"),
    industry_slug: str = Query("ai"),
    segment_id: int | None = None,
    segment_ids: str | None = Query(
        None,
        description="Comma-separated segment ids; mutually exclusive with segment_id.",
    ),
    published_within_days: int | None = Query(None, ge=1, le=3650),
    published_on_latest_day: bool = Query(False),
    source: str | None = Query(
        None,
        description="admin_source_key（如 github、product_hunt）；与 articles/sources 返回的 key 一致。",
    ),
    q: str | None = Query(
        None,
        description="Search title and summary (case-insensitive substring); max 80 chars.",
    ),
    replication_tiers: str | None = Query(
        None,
        description="Comma-separated monetization tiers S,A,B,C (legacy filter).",
    ),
    replication_complete: bool = Query(
        False,
        description="When true, only apps with monetization assessment and worth_score≥7.",
    ),
    replication_high_value: bool = Query(
        False,
        description="When true, only high-value picks (worth≥8, verdict=高价值).",
    ),
    db: Session = Depends(get_db),
):
    """当前时间/板块下、该泳道文章 AI 返回的 categories 聚合（供前台筛选）。"""
    segment_ids_parsed = parse_segment_ids_csv(segment_ids)
    if segment_id is not None and segment_ids_parsed is not None:
        raise HTTPException(400, "segment_id and segment_ids are mutually exclusive")
    try:
        items = article_app.list_article_category_facets(
            db,
            feed=feed,
            industry_slug=industry_slug,
            segment_id=segment_id,
            segment_ids=segment_ids_parsed,
            published_within_days=published_within_days,
            published_on_latest_day=published_on_latest_day,
            source=source,
            search=q,
            replication_tiers=replication_tiers,
            replication_complete=replication_complete,
            replication_high_value=replication_high_value,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return success(items)


@router.get("/articles/sources")
def list_article_sources(
    feed: str = Query(..., pattern="^(news|apps)$"),
    industry_slug: str = Query("ai"),
    segment_id: int | None = None,
    segment_ids: str | None = Query(
        None,
        description="Comma-separated segment ids; mutually exclusive with segment_id.",
    ),
    published_within_days: int | None = Query(None, ge=1, le=3650),
    published_on_latest_day: bool = Query(False),
    category: str | None = Query(
        None,
        description="与 articles/categories 返回的 label 完全一致时筛选；不传表示不限类别。",
    ),
    q: str | None = Query(
        None,
        description="Search title and summary (case-insensitive substring); max 80 chars.",
    ),
    replication_tiers: str | None = Query(
        None,
        description="Comma-separated replication tiers S,A,B,C.",
    ),
    replication_complete: bool = Query(
        False,
        description="When true, only apps with monetization assessment and worth_score≥7.",
    ),
    replication_high_value: bool = Query(
        False,
        description="When true, only high-value picks (worth≥8, verdict=高价值).",
    ),
    db: Session = Depends(get_db),
):
    """当前时间/板块下、该泳道文章按数据源聚合（供前台筛选）。"""
    segment_ids_parsed = parse_segment_ids_csv(segment_ids)
    if segment_id is not None and segment_ids_parsed is not None:
        raise HTTPException(400, "segment_id and segment_ids are mutually exclusive")
    try:
        items = article_app.list_article_source_facets(
            db,
            feed=feed,
            industry_slug=industry_slug,
            segment_id=segment_id,
            segment_ids=segment_ids_parsed,
            published_within_days=published_within_days,
            published_on_latest_day=published_on_latest_day,
            category=category,
            search=q,
            replication_tiers=replication_tiers,
            replication_complete=replication_complete,
            replication_high_value=replication_high_value,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return success(items)


@router.get("/articles/feed")
def list_articles_feed(
    feed: str = Query(..., pattern="^(news|apps)$", description="资讯 news 或 应用 apps"),
    industry_slug: str = Query("ai", description="公共站固定为 ai"),
    segment_id: int | None = None,
    segment_ids: str | None = Query(
        None,
        description="Comma-separated segment ids; mutually exclusive with segment_id.",
    ),
    paginate_by: str = Query(
        "cursor",
        pattern="^(cursor|day|heat)$",
        description="cursor=按条数游标分页；day=按 UTC 日历日整页；heat=当前时间窗内按热度 Top N。",
    ),
    page: int | None = Query(None, ge=1, le=5000, description="paginate_by=day 时页码，从 1 开始（最新一段日历日为第 1 页）。"),
    days_per_page: int = Query(
        article_app.DAYS_PER_PAGE_DEFAULT,
        ge=1,
        le=31,
        description="paginate_by=day 时每页包含的连续 UTC 日历日数（默认 3）。",
    ),
    heat_offset: int = Query(
        0,
        ge=0,
        le=99,
        description="paginate_by=heat 时已跳过条数（与已展示 items 条数对齐，用于触底继续拉取）。",
    ),
    heat_page_size: int = Query(
        20,
        ge=1,
        le=20,
        description="paginate_by=heat 时每页条数，最大 20；热度池最多 heat_max_ranked 条。",
    ),
    heat_max_ranked: int = Query(
        article_app.HEAT_FEED_MAX,
        ge=1,
        le=article_app.HEAT_FEED_MAX,
        description="paginate_by=heat 时参与排序的热度池上限（默认 100）。",
    ),
    page_size: int = Query(18, ge=1, le=48),
    cursor: str | None = Query(None, description="Keyset cursor from previous response (next_cursor)."),
    exclude_fp: str | None = Query(
        None,
        description="Comma-separated content fingerprints (20-char hex) already shown client-side.",
    ),
    published_within_days: int | None = Query(None, ge=1, le=3650),
    published_on_latest_day: bool = Query(False),
    category: str | None = Query(
        None,
        description="与 articles/categories 返回的 label 完全一致时筛选；不传表示不限类别。",
    ),
    source: str | None = Query(
        None,
        description="admin_source_key（如 github、product_hunt）；与 articles/sources 返回的 key 一致。",
    ),
    q: str | None = Query(
        None,
        description="Search title and summary (case-insensitive substring); max 80 chars.",
    ),
    replication_tiers: str | None = Query(
        None,
        description="Comma-separated monetization tiers S,A,B,C (legacy; prefer replication_complete).",
    ),
    replication_complete: bool = Query(
        False,
        description="When true, only apps with monetization assessment and worth_score≥7.",
    ),
    replication_high_value: bool = Query(
        False,
        description="When true, only high-value picks (worth≥8, verdict=高价值).",
    ),
    sort_replicable: bool = Query(
        False,
        description="Deprecated alias: same as sort_by_value (order by worth_score desc).",
    ),
    sort_by_value: bool = Query(
        False,
        description="When true, order heat pool by worth_score (变现价值分 1–10) desc, then heat.",
    ),
    sort_monetization: bool = Query(
        False,
        description="When true, order heat pool by 变现案例→已验证变现 then heat (apps 变现优先).",
    ),
    db: Session = Depends(get_db),
):
    segment_ids_parsed = parse_segment_ids_csv(segment_ids)
    if segment_id is not None and segment_ids_parsed is not None:
        raise HTTPException(400, "segment_id and segment_ids are mutually exclusive")
    try:
        if paginate_by == "day":
            data = article_app.list_articles_feed_by_day_page(
                db,
                feed=feed,
                industry_slug=industry_slug,
                segment_id=segment_id,
                segment_ids=segment_ids_parsed,
                page=page or 1,
                published_within_days=published_within_days,
                published_on_latest_day=published_on_latest_day,
                category=category,
                source=source,
                search=q,
                days_per_page=days_per_page,
                replication_tiers=replication_tiers,
                replication_complete=replication_complete,
                replication_high_value=replication_high_value,
            )
        elif paginate_by == "heat":
            data = article_app.list_articles_feed_by_heat_top(
                db,
                feed=feed,
                industry_slug=industry_slug,
                segment_id=segment_id,
                segment_ids=segment_ids_parsed,
                published_within_days=published_within_days,
                published_on_latest_day=published_on_latest_day,
                category=category,
                source=source,
                search=q,
                heat_offset=heat_offset,
                heat_page_size=heat_page_size,
                heat_max_ranked=heat_max_ranked,
                replication_tiers=replication_tiers,
                replication_complete=replication_complete,
                replication_high_value=replication_high_value,
                sort_replicable=sort_replicable,
                sort_by_value=sort_by_value or sort_replicable,
                sort_monetization=sort_monetization,
            )
        else:
            data = article_app.list_articles_feed(
                db,
                feed=feed,
                industry_slug=industry_slug,
                segment_id=segment_id,
                segment_ids=segment_ids_parsed,
                page_size=page_size,
                cursor=cursor,
                exclude_fp=exclude_fp,
                published_within_days=published_within_days,
                published_on_latest_day=published_on_latest_day,
                category=category,
                source=source,
                search=q,
                replication_tiers=replication_tiers,
                replication_complete=replication_complete,
                replication_high_value=replication_high_value,
            )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return success(data)


@router.get("/articles/{article_id}")
def get_article(article_id: int, db: Session = Depends(get_db)):
    row = article_app.get_published_article(db, article_id)
    if not row:
        raise HTTPException(404, "not found")
    return success(row)
