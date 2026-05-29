"""内容发布运营统计：各站点/泳道每日发文、分类、维护信息（非连接器同步技术指标）。"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..models import NewsletterDailyDigest
from ..product_models import Article, ProductConnector


SITE_LABELS: dict[str, str] = {
    "ai-trends-news": "站内 · 资讯",
    "ai-trends-apps": "站内 · 应用",
    "douyin": "抖音",
    "xhs": "小红书",
    "toutiao": "今日头条",
    "douban": "豆瓣",
}


def _utc_day(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def _site_key_for_article(a: Article) -> str:
    fk = (getattr(a, "feed_kind", None) or "news").strip().lower()
    return "ai-trends-apps" if fk == "apps" else "ai-trends-news"


def _source_key_from_article(a: Article) -> str:
    tps = (a.third_party_source or "").strip()
    if " / " in tps:
        return tps.split(" / ", 1)[0].strip().lower()
    return tps.lower() or "unknown"


def publishing_ops_overview(db: Session, *, days: int = 30) -> dict[str, Any]:
    """
    Soul 侧可见：站内已发布文章。
    外站视频/短文发布记录在 Pipeline 中间层（本 API 的 external_note 字段说明）。
    """
    days = max(1, min(int(days), 90))
    since = datetime.utcnow() - timedelta(days=days)
    today = datetime.utcnow().date().isoformat()

    published = list(
        db.scalars(
            select(Article).where(
                Article.status == "published",
                Article.published_at.isnot(None),
                Article.published_at >= since,
            )
        ).all()
    )
    all_published = list(db.scalars(select(Article).where(Article.status == "published")).all())
    drafts = len(list(db.scalars(select(Article).where(Article.status == "draft")).all()))

    daily: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"articles": 0, "videos": 0})
    )
    category_counts: dict[str, int] = defaultdict(int)
    category_by_site: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    last_pub_by_site: dict[str, str | None] = {k: None for k in ("ai-trends-news", "ai-trends-apps")}
    last_pub_by_source: dict[str, str | None] = defaultdict(lambda: None)

    for a in published:
        day = _utc_day(a.published_at)
        if not day:
            continue
        site = _site_key_for_article(a)
        daily[day][site]["articles"] += 1
        cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
        for c in cats[:3]:
            if c:
                category_counts[c] += 1
                category_by_site[site][c] += 1
        sk = _source_key_from_article(a)
        ts = a.published_at.isoformat() + "Z" if a.published_at else None
        if ts and (not last_pub_by_source[sk] or ts > last_pub_by_source[sk]):
            last_pub_by_source[sk] = ts

    for a in all_published:
        site = _site_key_for_article(a)
        ts = a.published_at.isoformat() + "Z" if a.published_at else None
        if ts and (not last_pub_by_site[site] or ts > (last_pub_by_site[site] or "")):
            last_pub_by_site[site] = ts

    # 连续日期序列（站内）
    site_keys = ("ai-trends-news", "ai-trends-apps")
    daily_series: list[dict[str, Any]] = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).date().isoformat()
        row: dict[str, Any] = {"date": d, "sites": {}}
        for sk in site_keys:
            cell = daily.get(d, {}).get(sk, {"articles": 0, "videos": 0})
            row["sites"][sk] = {
                "label": SITE_LABELS[sk],
                "articles": cell["articles"],
                "videos": 0,
            }
        daily_series.append(row)

    categories = [
        {"category": k, "count": v}
        for k, v in sorted(category_counts.items(), key=lambda kv: -kv[1])
    ]
    categories_by_site = []
    for sk in site_keys:
        inner = category_by_site.get(sk) or {}
        categories_by_site.append(
            {
                "site_key": sk,
                "site_label": SITE_LABELS[sk],
                "items": [{"category": k, "count": v} for k, v in sorted(inner.items(), key=lambda kv: -kv[1])],
            }
        )

    # 数据源维护：多久没出新稿
    connectors = list(db.scalars(select(ProductConnector)).all())
    source_rows: list[dict[str, Any]] = []
    stale_days = 7
    stale_cutoff = datetime.utcnow() - timedelta(days=stale_days)
    for c in connectors:
        sk = (c.admin_source_key or "").strip().lower() or "unknown"
        last_at = last_pub_by_source.get(sk)
        last_dt = None
        if last_at:
            try:
                last_dt = datetime.fromisoformat(last_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass
        articles_n = sum(1 for a in published if _source_key_from_article(a) == sk)
        source_rows.append(
            {
                "source_key": sk,
                "connector_name": c.name,
                "enabled": c.enabled,
                "articles_in_period": articles_n,
                "last_published_at": last_at,
                "stale": last_dt is None or last_dt < stale_cutoff,
                "last_sync_at": c.last_sync_at.isoformat() + "Z" if c.last_sync_at else None,
                "last_error": (c.last_error or "")[:200] or None,
            }
        )
    source_rows.sort(key=lambda x: (x["stale"], -x["articles_in_period"]))

    today_counts = {"articles": 0, "videos": 0}
    for sk in site_keys:
        today_counts["articles"] += daily.get(today, {}).get(sk, {}).get("articles", 0)

    digest = db.scalars(
        select(NewsletterDailyDigest).order_by(NewsletterDailyDigest.id.desc()).limit(1)
    ).first()
    digest_info = None
    if digest:
        digest_info = {
            "digest_date": getattr(digest, "digest_date", None),
            "status": getattr(digest, "status", None),
            "updated_at": digest.updated_at.isoformat() + "Z" if getattr(digest, "updated_at", None) else None,
        }

    return {
        "days": days,
        "since": since.isoformat() + "Z",
        "scope": "soul_on_site",
        "external_channels_note": "抖音/小红书/头条/豆瓣的发布数请在 Pipeline 中控台查看（标记已发布后统计）。",
        "summary": {
            "published_in_period": len(published),
            "draft_count": drafts,
            "today_articles_on_site": today_counts["articles"],
            "today_videos_on_site": 0,
        },
        "daily": daily_series,
        "categories": categories,
        "categories_by_site": categories_by_site,
        "site_last_published": [
            {"site_key": sk, "site_label": SITE_LABELS[sk], "last_published_at": last_pub_by_site.get(sk)}
            for sk in site_keys
        ],
        "sources_maintenance": source_rows,
        "digest_maintenance": digest_info,
    }
