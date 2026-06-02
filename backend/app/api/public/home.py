from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application.home_public import get_home_dashboard, get_home_editorial_picks, get_home_trend_overview
from ...application.industry_wind_public import get_industry_wind_overview
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


@router.get("/home/industry-wind")
def home_industry_wind(
    industry_slug: str = "ai",
    db: Session = Depends(get_db),
):
    """行业风向：只读缓存/快速聚类，不在用户请求时调用 LLM（每日定时任务生成）。"""
    data = get_industry_wind_overview(db, industry_slug=industry_slug, allow_llm=False)
    return success(data)


@router.get("/home/dashboard")
def home_dashboard(
    industry_slug: str = "ai",
    news_limit: int = 8,
    apps_limit: int = 10,
    replicable_apps_limit: int = 4,
    monetization_apps_limit: int = 4,
    published_within_days: int = 30,
    db: Session = Depends(get_db),
):
    """首页仪表盘：热度精选 + 亮点高可复刻应用 + 趋势 + 多路数据源雷达（单次请求）。"""
    data = get_home_dashboard(
        db,
        industry_slug=industry_slug,
        news_limit=news_limit,
        apps_limit=apps_limit,
        replicable_apps_limit=replicable_apps_limit,
        monetization_apps_limit=monetization_apps_limit,
        published_within_days=published_within_days,
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
    """首页今日精选：美东内容日当日，资讯按热度、应用按变现价值分。"""
    data = get_home_editorial_picks(
        db,
        industry_slug=industry_slug,
        news_limit=news_limit,
        apps_limit=apps_limit,
        published_within_days=published_within_days,
    )
    return success(data)
