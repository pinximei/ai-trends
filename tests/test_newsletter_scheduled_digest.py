"""定时摘要：北京时间 9:00、每日强制重发。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from backend.app.application.newsletter_daily_digest import run_daily_newsletter_digest_job
from backend.app.models import NewsletterDailyDigest


@patch("backend.app.application.newsletter_daily_digest.fetch_articles_for_shanghai_day_split")
@patch("backend.app.application.newsletter_daily_digest.generate_digest_content")
@patch("backend.app.application.newsletter_daily_digest.send_digest_to_feishu")
@patch("backend.app.application.newsletter_daily_digest.get_newsletter_settings_merged")
def test_scheduled_run_does_not_skip_when_feishu_already_sent(
    mock_settings,
    mock_feishu,
    mock_generate,
    mock_fetch,
) -> None:
    mock_settings.return_value = {
        "cron_enabled": True,
        "daily_digest_job_enabled": True,
        "generate_enabled": True,
        "send_enabled": False,
        "feishu_enabled": True,
        "feishu_webhook_url": "https://example.com/hook",
        "feishu_push_cadence": "daily",
        "apps_limit": 4,
        "news_limit": 4,
    }
    mock_fetch.return_value = ([], [])

    ready_row = NewsletterDailyDigest(
        digest_date="2026-05-27",
        status="ready",
        subject="new",
        body_md="x" * 500,
        feishu_sent_at=None,
    )

    db = MagicMock()
    calls = {"n": 0}

    def _scalar(_stmt):
        calls["n"] += 1
        return ready_row if calls["n"] >= 2 else NewsletterDailyDigest(
            digest_date="2026-05-27",
            status="ready",
            subject="old",
            body_md="x" * 500,
            feishu_sent_at=datetime(2026, 5, 27, 6, 0, 0),
        )

    db.scalar.side_effect = _scalar
    db.commit = MagicMock()
    db.expire_all = MagicMock()

    out = run_daily_newsletter_digest_job(
        db=db,
        settings=mock_settings.return_value,
        digest_date="2026-05-27",
        scheduled_run=True,
    )

    assert out.get("skipped") is not True
    assert out.get("reason") != "already_delivered"
    assert mock_generate.called
    assert mock_feishu.called
