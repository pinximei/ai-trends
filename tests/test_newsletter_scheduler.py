"""每日摘要 Cron 调度（北京时间定点）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from backend.app.lifespan import _newsletter_digest_cron_trigger
from backend.app.newsletter_settings_service import default_newsletter_json


@patch("backend.app.newsletter_settings_service.get_newsletter_settings_merged")
def test_newsletter_digest_cron_trigger_uses_beijing_timezone(mock_merged) -> None:
    mock_merged.return_value = {
        **default_newsletter_json(),
        "digest_send_timezone": "Asia/Shanghai",
        "daily_hour": 9,
        "daily_minute": 0,
    }
    db = MagicMock()
    trigger = _newsletter_digest_cron_trigger(db)
    assert isinstance(trigger, CronTrigger)
    assert trigger.timezone == ZoneInfo("Asia/Shanghai")
