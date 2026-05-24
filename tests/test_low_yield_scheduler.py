"""TheNewsAPI 等低产出源的微批调度策略。"""
from datetime import datetime, timedelta, timezone

from backend.app.connector_sync_policy import (
    THENEWSAPI_API_MAX_ROWS,
    is_low_yield_micro_batch_source,
    low_yield_batch_due_now,
    min_interval_seconds_for_source,
)
from backend.app.scheduler_settings_service import get_last_low_yield_batch_at


def test_is_low_yield_thenewsapi() -> None:
    assert is_low_yield_micro_batch_source("thenewsapi")
    assert not is_low_yield_micro_batch_source("newsapi")


def test_thenewsapi_min_interval() -> None:
    assert min_interval_seconds_for_source("thenewsapi") == 30 * 60


def test_low_yield_batch_due_when_never_run() -> None:
    assert low_yield_batch_due_now(interval_hours=2, last_batch_at=None)


def test_low_yield_batch_not_due_within_interval() -> None:
    now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=1)
    assert not low_yield_batch_due_now(interval_hours=2, last_batch_at=last, now=now)


def test_low_yield_batch_due_after_interval() -> None:
    now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=3)
    assert low_yield_batch_due_now(interval_hours=2, last_batch_at=last, now=now)


def test_get_last_low_yield_batch_at_from_settings() -> None:
    settings = {"last_low_yield_batch_at": {"thenewsapi": "2026-05-24T10:00:00Z"}}
    dt = get_last_low_yield_batch_at(settings, "thenewsapi")
    assert dt is not None
    assert dt.year == 2026


def test_thenewsapi_api_cap_documented() -> None:
    assert THENEWSAPI_API_MAX_ROWS == 3
