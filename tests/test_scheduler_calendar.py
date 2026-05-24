"""连接器整批调度：美东当日最后一小时（23:00）拉取。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.scheduler_settings_service import connector_batch_due_now
from backend.app.us_content_calendar import US_CONTENT_TZ, us_end_of_day_pull_start_local


def _dt(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=US_CONTENT_TZ)


def test_connector_batch_due_only_in_hour_23() -> None:
    assert connector_batch_due_now(interval_hours=6, last_batch_at=None, now=_dt(2026, 5, 19, 23, 5)) is True
    assert connector_batch_due_now(interval_hours=6, last_batch_at=None, now=_dt(2026, 5, 19, 10, 0)) is False
    assert connector_batch_due_now(interval_hours=6, last_batch_at=None, now=_dt(2026, 5, 19, 0, 0)) is False


def test_connector_batch_due_once_per_us_day() -> None:
    eod = us_end_of_day_pull_start_local(_dt(2026, 5, 19, 23, 10))
    last = (eod + timedelta(minutes=5)).astimezone(timezone.utc).replace(tzinfo=None)
    assert connector_batch_due_now(interval_hours=6, last_batch_at=last, now=_dt(2026, 5, 19, 23, 20)) is False
    assert connector_batch_due_now(interval_hours=6, last_batch_at=last, now=_dt(2026, 5, 20, 23, 5)) is True
