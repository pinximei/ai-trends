"""公开：站内发布日统计（供 Pipeline 合并展示）。"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..application.content_publish_stats import publishing_ops_overview


def publishing_daily_public(db: Session, *, days: int = 30) -> dict[str, Any]:
    full = publishing_ops_overview(db, days=days)
    return {
        "days": full["days"],
        "daily": full["daily"],
        "categories": full["categories"],
        "categories_by_site": full["categories_by_site"],
        "site_last_published": full["site_last_published"],
    }
