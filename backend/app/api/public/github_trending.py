from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...application.github_trending_snapshot import (
    get_github_trending_snapshot,
    list_snapshot_public_items,
    period_date_for_since,
    week_ending_sunday,
)
from ...core.envelope import success
from ...db import get_db

router = APIRouter(tags=["public-github-trending"])


@router.get("/github/trending")
def get_github_trending(
    since: str = Query("daily", pattern="^(daily|weekly)$"),
    on_date: str | None = Query(
        None,
        alias="date",
        description="日榜 YYYY-MM-DD；周榜为当周周日 YYYY-MM-DD，缺省为今天/本周",
    ),
    industry_slug: str = Query("ai"),
    limit: int = Query(10, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """返回 GitHub Trending 有序快照（与官方 since=daily|weekly 对齐）。"""
    period: str | date | None = None
    if on_date:
        try:
            period = date.fromisoformat(on_date.strip())
        except ValueError as exc:
            raise HTTPException(400, "invalid date, use YYYY-MM-DD") from exc
        if since == "weekly":
            period = week_ending_sunday(period)
    else:
        period = period_date_for_since(since)

    snap = get_github_trending_snapshot(
        db,
        since=since,
        period_date=period,
        industry_slug=industry_slug,
    )
    if not snap:
        raise HTTPException(
            404,
            f"no github trending snapshot for since={since} period={period}",
        )
    items = list_snapshot_public_items(db, snap, limit=limit)
    return success(
        {
            "since": snap.since,
            "period_date": snap.period_date,
            "discovery_url": snap.discovery_url,
            "connector_sync_log_id": snap.connector_sync_log_id,
            "item_count": snap.item_count,
            "generated_at": snap.created_at.isoformat() + "Z" if snap.created_at else None,
            "items": items,
        }
    )
