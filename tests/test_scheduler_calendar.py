"""连接器整批调度：按配置的间隔小时触发。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.scheduler_settings_service import connector_batch_due_now


def test_connector_batch_due_after_interval() -> None:
    now = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=7)
    assert connector_batch_due_now(interval_hours=6, last_batch_at=last, now=now) is True
    last2 = now - timedelta(hours=5)
    assert connector_batch_due_now(interval_hours=6, last_batch_at=last2, now=now) is False


def test_connector_batch_due_when_never_run() -> None:
    now = datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)
    assert connector_batch_due_now(interval_hours=6, last_batch_at=None, now=now) is True
