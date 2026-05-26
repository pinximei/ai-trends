"""公开站对外根 URL（sitemap、邮件链接等）。"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

DEFAULT_PUBLIC_SITE_BASE_URL = "https://www.ai-trends.news"


def resolve_public_site_base_url(db: Session | None = None) -> str:
    env = (os.getenv("AITRENDS_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if env:
        return env
    if db is not None:
        from .newsletter_settings_service import _merged_stored

        stored = (_merged_stored(db).get("public_site_base_url") or "").strip().rstrip("/")
        if stored:
            return stored
    return DEFAULT_PUBLIC_SITE_BASE_URL
