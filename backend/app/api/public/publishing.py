from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...application.publishing_public import publishing_daily_public
from ...core.envelope import success
from ...db import get_db

router = APIRouter(tags=["public-publishing"])


@router.get("/publishing/daily")
def get_publishing_daily(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """站内每日发文与分类（只读，供 Pipeline 合并多渠道看板）。"""
    return success(publishing_daily_public(db, days=days))
