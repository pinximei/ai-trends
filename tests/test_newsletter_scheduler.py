"""每日摘要 Cron 调度（美东定点，避免 5 分钟轮询漏跑）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from apscheduler.triggers.cron import CronTrigger

from backend.app.lifespan import _newsletter_digest_cron_trigger
from backend.app.newsletter_settings_service import default_newsletter_json
from backend.app.us_content_calendar import US_CONTENT_TZ


@patch("backend.app.newsletter_settings_service.get_newsletter_settings_merged")
def test_newsletter_digest_cron_trigger_uses_us_timezone(mock_merged) -> None:
    mock_merged.return_value = {**default_newsletter_json(), "daily_hour": 9, "daily_minute": 30}
    db = MagicMock()
    trigger = _newsletter_digest_cron_trigger(db)
    assert isinstance(trigger, CronTrigger)
    assert trigger.timezone == US_CONTENT_TZ
