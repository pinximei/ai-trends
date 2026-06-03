"""首页今日精选：UTC 当日展示时效（与列表按日分页一致）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from unittest.mock import patch

from backend.app.application.home_public import (
    EDITORIAL_FALLBACK_DAYS,
    _editorial_heat_query_kw,
    _editorial_picks_for_home,
    _editorial_recent_query_kw,
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


def test_editorial_recent_query_kw() -> None:
    kw = _editorial_recent_query_kw(industry_slug="ai", limit=3, days=7)
    assert kw["published_within_days"] == 7
    assert kw["published_on_latest_day"] is False


def test_editorial_picks_fallback_when_today_empty() -> None:
    fallback_row = {"id": 99, "title": "fallback", "heat_score": 10}

    class _Db:
        pass

    with patch(
        "backend.app.application.home_public._editorial_from_today_pool",
        return_value=[],
    ), patch(
        "backend.app.application.home_public._editorial_from_recent_pool",
        return_value=[fallback_row],
    ):
        items, used_fb = _editorial_picks_for_home(
            _Db(), feed="news", industry_slug="ai", limit=3
        )
    assert used_fb is True
    assert items[0]["id"] == 99
    assert EDITORIAL_FALLBACK_DAYS == 7
