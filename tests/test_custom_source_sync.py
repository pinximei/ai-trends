"""数据源「单独同步」策略与调度。"""
from datetime import datetime, timedelta, timezone

from backend.app.connector_sync_policy import (
    CUSTOM_SYNC_INTERVAL_HOURS_DEFAULT,
    clamp_custom_sync_interval_hours,
    custom_source_batch_due_now,
)
from backend.app.scheduler_settings_service import get_last_custom_source_batch_at


def test_clamp_custom_sync_interval() -> None:
    assert clamp_custom_sync_interval_hours(None) == CUSTOM_SYNC_INTERVAL_HOURS_DEFAULT
    assert clamp_custom_sync_interval_hours(200) == 168
    assert clamp_custom_sync_interval_hours(0) == 1


def test_custom_source_batch_due_never_run() -> None:
    assert custom_source_batch_due_now(interval_hours=2, last_batch_at=None)


def test_custom_source_batch_not_due() -> None:
    now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=1)
    assert not custom_source_batch_due_now(interval_hours=2, last_batch_at=last, now=now)


def test_get_last_custom_source_batch_at() -> None:
    settings = {"last_custom_source_batch_at": {"thenewsapi": "2026-05-24T10:00:00Z"}}
    dt = get_last_custom_source_batch_at(settings, "thenewsapi")
    assert dt is not None
