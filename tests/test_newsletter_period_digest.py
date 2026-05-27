"""飞书按周/按月推送周期窗口。"""
from __future__ import annotations

from datetime import date

from backend.app.application.newsletter_period_digest import (
    manual_period_window,
    normalize_feishu_cadence,
    scheduled_period_window,
    should_skip_period_feishu,
)


def test_normalize_feishu_cadence() -> None:
    assert normalize_feishu_cadence("weekly") == "weekly"
    assert normalize_feishu_cadence("bogus") == "daily"


def test_scheduled_weekly_monday_previous_week() -> None:
    # 2026-05-25 is Monday
    today = date(2026, 5, 25)
    w = scheduled_period_window("weekly", today, weekly_weekday=0)
    assert w is not None
    start, end, key = w
    assert start == date(2026, 5, 18)
    assert end == date(2026, 5, 24)
    assert key == "2026-W21"


def test_scheduled_weekly_skips_non_send_day() -> None:
    today = date(2026, 5, 26)  # Tuesday
    assert scheduled_period_window("weekly", today, weekly_weekday=0) is None


def test_scheduled_monthly_first_day() -> None:
    today = date(2026, 6, 1)
    w = scheduled_period_window("monthly", today, weekly_weekday=0)
    assert w is not None
    start, end, key = w
    assert start == date(2026, 5, 1)
    assert end == date(2026, 5, 31)
    assert key == "2026-05"


def test_scheduled_monthly_skips_mid_month() -> None:
    assert scheduled_period_window("monthly", date(2026, 5, 15), weekly_weekday=0) is None


def test_manual_trailing_windows() -> None:
    today = date(2026, 5, 24)
    s, e, _k = manual_period_window("weekly", today)
    assert s == date(2026, 5, 18)
    assert e == today
    s2, e2, _k2 = manual_period_window("monthly", today)
    assert s2 == date(2026, 5, 1)
    assert e2 == today


def test_should_skip_period_feishu() -> None:
    assert should_skip_period_feishu(period_key="2026-W21", last_sent="2026-W21", manual_run=False)
    assert not should_skip_period_feishu(period_key="2026-W21", last_sent="2026-W21", manual_run=True)
