"""连接器整批调度：按 Asia/Shanghai 当日 00:00 对齐时段。"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.scheduler_settings_service import (
    CONNECTOR_SCHEDULER_TZ,
    connector_batch_due_now,
    connector_batch_slot_start_local,
)

TZ = CONNECTOR_SCHEDULER_TZ


def _dt(y: int, m: int, d: int, hh: int, mm: int = 0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_slot_start_24h_is_midnight() -> None:
    assert connector_batch_slot_start_local(_dt(2026, 5, 19, 14, 30), interval_hours=24) == _dt(2026, 5, 19, 0)


def test_slot_start_6h_quarters() -> None:
    assert connector_batch_slot_start_local(_dt(2026, 5, 19, 7, 10), interval_hours=6) == _dt(2026, 5, 19, 6)
    assert connector_batch_slot_start_local(_dt(2026, 5, 19, 0, 5), interval_hours=6) == _dt(2026, 5, 19, 0)


def test_due_24h_at_midnight_window() -> None:
    assert connector_batch_due_now(interval_hours=24, last_batch_at=None, now=_dt(2026, 5, 19, 0, 5))
    assert not connector_batch_due_now(
        interval_hours=24,
        last_batch_at=_dt(2026, 5, 19, 0, 1).astimezone(TZ).replace(tzinfo=None),
        now=_dt(2026, 5, 19, 0, 10),
    )


def test_due_24h_not_outside_window() -> None:
    assert not connector_batch_due_now(interval_hours=24, last_batch_at=None, now=_dt(2026, 5, 19, 10, 0))


def test_due_24h_after_restart_same_day() -> None:
    last = datetime(2026, 5, 18, 0, 5, tzinfo=TZ).replace(tzinfo=None)
    assert connector_batch_due_now(interval_hours=24, last_batch_at=last, now=_dt(2026, 5, 19, 0, 8))
    assert not connector_batch_due_now(interval_hours=24, last_batch_at=last, now=_dt(2026, 5, 19, 14, 0))


def test_due_6h_at_six_am() -> None:
    assert connector_batch_due_now(interval_hours=6, last_batch_at=None, now=_dt(2026, 5, 19, 6, 3))
