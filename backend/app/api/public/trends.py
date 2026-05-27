from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.trend_momentum_public import get_trend_momentum_dashboard
from ...core.envelope import success
from ...db import get_db

router = APIRouter(tags=["public-trends"])


@router.get("/trends/momentum")
def trends_momentum(
    industry_slug: str = "ai",
    period_days: int = 30,
    limit_per_track: int = 8,
    topic_limit: int = 10,
    db: Session = Depends(get_db),
):
    """持续升温榜：软件 / 开源 / 资讯热点 + 话题赛道聚合。"""
    data = get_trend_momentum_dashboard(
        db,
        industry_slug=industry_slug,
        period_days=period_days,
        limit_per_track=limit_per_track,
        topic_limit=topic_limit,
    )
    return success(data)
