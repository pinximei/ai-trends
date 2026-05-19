from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.home_public import get_home_trend_overview
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
