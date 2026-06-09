"""GitHub Trending 日/周榜快照：入库后落盘 + 公网查询。"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..domain.articles import (
    CONNECTOR_SNIPPET_MAX_CHARS,
    extract_source_external_id_from_connector_snippet,
    parse_connector_sync_item_snippets,
)
from ..product_models import Article, GithubTrendingSnapshot, Industry

SHANGHAI = ZoneInfo("Asia/Shanghai")


def week_ending_sunday(d: date) -> date:
    if d.weekday() == 6:
        return d
    return d + timedelta(days=(6 - d.weekday()))


def period_date_for_since(since: str, when: datetime | None = None) -> date:
    """日榜=上海日历日；周榜=该周周日。"""
    ref = when or datetime.now(SHANGHAI)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=SHANGHAI)
    else:
        ref = ref.astimezone(SHANGHAI)
    local_day = ref.date()
    if since == "weekly":
        return week_ending_sunday(local_day)
    return local_day


def _parse_pack_meta(snippet: str) -> tuple[str, str]:
    safe = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    since = "daily"
    discovery_url = ""
    try:
        root = json.loads(safe)
    except json.JSONDecodeError:
        return since, discovery_url
    if not isinstance(root, dict):
        return since, discovery_url
    note = str(root.get("note") or "")
    if "weekly" in note:
        since = "weekly"
    elif "monthly" in note:
        since = "monthly"
    parts = parse_connector_sync_item_snippets(safe) or []
    if parts:
        try:
            first = json.loads(parts[0])
            if isinstance(first, dict):
                tr = first.get("_aisoul_trending") or {}
                if isinstance(tr, dict):
                    since = str(tr.get("since") or since).strip().lower() or since
                    discovery_url = str(tr.get("discovery_url") or "").strip()
        except json.JSONDecodeError:
            pass
    return since if since in {"daily", "weekly", "monthly"} else "daily", discovery_url


def _ranked_rows_from_pack(snippet: str) -> list[dict[str, Any]]:
    parts = parse_connector_sync_item_snippets(snippet) or []
    rows: list[dict[str, Any]] = []
    for idx, piece in enumerate(parts):
        try:
            obj = json.loads(piece)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        tr = obj.get("_aisoul_trending") if isinstance(obj.get("_aisoul_trending"), dict) else {}
        rank = tr.get("rank")
        try:
            rank_i = int(rank) if rank is not None else idx + 1
        except (TypeError, ValueError):
            rank_i = idx + 1
        full_name = str(obj.get("full_name") or "").strip()
        if not full_name and obj.get("name"):
            full_name = str(obj.get("name") or "").strip()
        stars_today = obj.get("trending_stars_today")
        if stars_today is None and isinstance(tr, dict):
            stars_today = tr.get("stars_today")
        ext_id = extract_source_external_id_from_connector_snippet(piece)
        rows.append(
            {
                "rank": rank_i,
                "full_name": full_name,
                "source_external_id": ext_id,
                "stars_today": stars_today,
                "title": str(obj.get("name") or full_name or "").strip(),
            }
        )
    rows.sort(key=lambda x: int(x.get("rank") or 999))
    return rows


def _lookup_article_id(
    db: Session,
    *,
    industry_id: int,
    source_external_id: str | None,
    full_name: str,
) -> int | None:
    sid = (source_external_id or "").strip()
    if sid:
        row = db.scalar(
            select(Article.id)
            .where(
                Article.industry_id == industry_id,
                Article.status == "published",
                Article.source_external_id == sid[:512],
            )
            .order_by(desc(Article.id))
            .limit(1)
        )
        if row:
            return int(row)
    slug = (full_name or "").strip().lower()
    if not slug:
        return None
    candidates = db.scalars(
        select(Article)
        .where(
            Article.industry_id == industry_id,
            Article.status == "published",
        )
        .order_by(desc(Article.updated_at))
        .limit(400)
    ).all()
    for art_row in candidates:
        url = (getattr(art_row, "source_original_url", None) or "").lower()
        title = (art_row.title or "").lower()
        if slug in url or slug in title:
            return int(art_row.id)
    return None


def save_github_trending_snapshot_from_pack(
    db: Session,
    *,
    snippet: str,
    connector_sync_log_id: int | None,
    industry_slug: str = "ai",
    when: datetime | None = None,
    discovery_url: str = "",
) -> GithubTrendingSnapshot | None:
    ranked = _ranked_rows_from_pack(snippet)
    if not ranked:
        return None
    since, discovered = _parse_pack_meta(snippet)
    if since == "monthly":
        return None
    period = period_date_for_since(since, when=when).isoformat()
    industry = db.scalar(select(Industry).where(Industry.slug == industry_slug).limit(1))
    industry_id = int(industry.id) if industry else None

    items: list[dict[str, Any]] = []
    for row in ranked:
        article_id = None
        if industry_id is not None:
            article_id = _lookup_article_id(
                db,
                industry_id=industry_id,
                source_external_id=row.get("source_external_id"),
                full_name=str(row.get("full_name") or ""),
            )
        items.append(
            {
                "rank": int(row.get("rank") or len(items) + 1),
                "full_name": row.get("full_name"),
                "source_external_id": row.get("source_external_id"),
                "stars_today": row.get("stars_today"),
                "article_id": article_id,
            }
        )

    existing = db.scalar(
        select(GithubTrendingSnapshot)
        .where(
            GithubTrendingSnapshot.industry_slug == industry_slug,
            GithubTrendingSnapshot.since == since,
            GithubTrendingSnapshot.period_date == period,
        )
        .limit(1)
    )
    snap = existing or GithubTrendingSnapshot(
        industry_slug=industry_slug,
        since=since,
        period_date=period,
    )
    snap.connector_sync_log_id = connector_sync_log_id
    snap.discovery_url = (discovery_url or discovered or "")[:512]
    snap.items_json = items
    snap.item_count = len(items)
    snap.created_at = when or datetime.utcnow()
    if not existing:
        db.add(snap)
    db.flush()
    return snap


def get_github_trending_snapshot(
    db: Session,
    *,
    since: str,
    period_date: str | date | None = None,
    industry_slug: str = "ai",
) -> GithubTrendingSnapshot | None:
    since_n = (since or "daily").strip().lower()
    if since_n not in {"daily", "weekly"}:
        raise ValueError("since must be daily or weekly")
    if period_date is None:
        period = period_date_for_since(since_n).isoformat()
    elif isinstance(period_date, date):
        period = period_date.isoformat()
    else:
        period = str(period_date).strip()
    return db.scalar(
        select(GithubTrendingSnapshot)
        .where(
            GithubTrendingSnapshot.industry_slug == industry_slug,
            GithubTrendingSnapshot.since == since_n,
            GithubTrendingSnapshot.period_date == period,
        )
        .order_by(desc(GithubTrendingSnapshot.created_at))
        .limit(1)
    )


def list_snapshot_public_items(
    db: Session,
    snap: GithubTrendingSnapshot,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    from . import article_public as article_app

    label_by_key = article_app._admin_source_label_by_key(db)
    out: list[dict[str, Any]] = []
    for row in (snap.items_json or [])[: max(1, limit)]:
        if not isinstance(row, dict):
            continue
        aid = int(row.get("article_id") or 0)
        article_row = db.get(Article, aid) if aid > 0 else None
        card = None
        if article_row and article_row.status == "published":
            card = article_app._feed_card_from_article(article_row, label_by_key=label_by_key)
        out.append(
            {
                "rank": int(row.get("rank") or len(out) + 1),
                "full_name": row.get("full_name"),
                "stars_today": row.get("stars_today"),
                "article_id": aid or None,
                "article": card,
            }
        )
    return out
