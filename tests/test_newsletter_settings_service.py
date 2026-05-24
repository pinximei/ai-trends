"""newsletter 配置：渠道开关自动推导定时/生成。"""
from __future__ import annotations

from backend.app.newsletter_settings_service import _sync_push_channel_flags, default_newsletter_json


def test_sync_push_channel_flags_all_off():
    cur = {**default_newsletter_json(), "send_enabled": True, "feishu_enabled": False}
    cur["send_enabled"] = False
    cur["feishu_enabled"] = False
    _sync_push_channel_flags(cur)
    assert cur["cron_enabled"] is False
    assert cur["generate_enabled"] is False
    assert cur["daily_digest_job_enabled"] is False


def test_sync_push_channel_flags_any_on():
    cur = {**default_newsletter_json(), "send_enabled": False, "feishu_enabled": True}
    _sync_push_channel_flags(cur)
    assert cur["cron_enabled"] is True
    assert cur["generate_enabled"] is True
    assert cur["daily_digest_job_enabled"] is True
