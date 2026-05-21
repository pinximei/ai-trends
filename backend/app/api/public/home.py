from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.home_public import get_home_editorial_picks, get_home_trend_overview
from ...core.envelope import success
from ...db import get_db

router = APIRouter(tags=["public-home"])


@router.get("/home/trend-overview")
def home_trend_overview(
    industry_slug: str = "ai",
    sparkline_days: int = 14,
    period_days: int = 30,
    db: Session = Depends(get_db),
):
    data = get_home_trend_overview(
        db,
        industry_slug=industry_slug,
        sparkline_days=sparkline_days,
        period_days=period_days,
    )
    return success(data)


@router.get("/home/editorial-picks")
def home_editorial_picks(
    industry_slug: str = "ai",
    news_limit: int = 8,
    apps_limit: int = 6,
    published_within_days: int = 30,
    db: Session = Depends(get_db),
):
    """首页焦点区：按 heat_score 精选资讯与应用（非按 published_at 最新）。"""
    data = get_home_editorial_picks(
        db,
        industry_slug=industry_slug,
        news_limit=news_limit,
        apps_limit=apps_limit,
        published_within_days=published_within_days,
    )
    return success(data)
