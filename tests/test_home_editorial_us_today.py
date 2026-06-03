"""首页今日精选：UTC 当日展示时效（与列表按日分页一致）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.app.application.home_public import (
    _editorial_heat_query_kw,
    _feed_item_freshness_dt,
    _parse_feed_card_iso_dt,
    _select_editorial_picks,
    _utc_today_bounds,
)


def test_editorial_query_uses_utc_latest_day() -> None:
    kw = _editorial_heat_query_kw(industry_slug="ai", limit=3)
    assert kw["published_on_latest_day"] is True
    assert kw["published_on_us_content_day"] is False


def test_utc_today_bounds_aligns_with_freshness_midnight() -> None:
    start, end = _utc_today_bounds()
    assert end - start == timedelta(days=1)
    mid = start + timedelta(hours=12)
    assert start <= mid < end


def test_parse_feed_card_iso_dt_z_suffix() -> None:
    dt = _parse_feed_card_iso_dt("2026-06-03T12:00:00Z")
    assert dt == datetime(2026, 6, 3, 12, 0, 0)


def test_feed_freshness_dt_prefers_display_at() -> None:
    item = {"display_at": "2026-06-03T08:00:00Z", "published_at": "2026-06-01T00:00:00Z"}
    assert _feed_item_freshness_dt(item) == datetime(2026, 6, 3, 8, 0, 0)


def test_select_editorial_picks_allows_low_heat_unassessed() -> None:
    items = [
        {"id": 1, "title": "低热应用甲", "heat_score": 1.0, "summary": "x" * 40},
        {"id": 2, "title": "高热应用乙", "heat_score": 99.0, "summary": "y" * 40},
    ]
    out = _select_editorial_picks(items, 2)
    assert [x["id"] for x in out] == [2, 1]
