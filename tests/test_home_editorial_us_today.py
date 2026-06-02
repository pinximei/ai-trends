"""首页今日精选：仅美东内容日当日。"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.application.home_public import (
    _filter_feed_items_us_content_today,
    _parse_feed_card_iso_dt,
)
from backend.app.us_content_calendar import utc_naive_bounds_for_us_date, us_calendar_today


def test_filter_feed_items_us_content_today() -> None:
    start, end = utc_naive_bounds_for_us_date(us_calendar_today())
    mid = start + (end - start) / 2
    mid_iso = mid.isoformat() + "Z"
    old = (start.replace(year=start.year - 1)).isoformat() + "Z"
    items = [
        {"id": 1, "display_at": mid_iso, "title": "today"},
        {"id": 2, "display_at": old, "title": "old"},
        {"id": 3, "title": "no date"},
    ]
    out = _filter_feed_items_us_content_today(items)
    assert [x["id"] for x in out] == [1]


def test_parse_feed_card_iso_dt_z_suffix() -> None:
    dt = _parse_feed_card_iso_dt("2026-06-01T12:00:00Z")
    assert dt == datetime(2026, 6, 1, 12, 0, 0)
