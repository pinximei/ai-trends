"""newsletter 配置：渠道开关自动推导定时/生成。"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.newsletter_settings_service import (
    _apply_newsletter_env_and_defaults,
    _sync_push_channel_flags,
    default_newsletter_json,
    get_newsletter_settings_merged,
    save_newsletter_settings_patch,
)
from backend.app.product_models import ProductSetting
from backend.app.public_site import DEFAULT_PUBLIC_SITE_BASE_URL


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


def test_apply_defaults_public_site_when_empty():
    m = _apply_newsletter_env_and_defaults({**default_newsletter_json(), "public_site_base_url": ""})
    assert m["public_site_base_url"] == DEFAULT_PUBLIC_SITE_BASE_URL


def test_apply_env_public_site_over_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITRENDS_PUBLIC_BASE_URL", "https://custom.example")
    m = _apply_newsletter_env_and_defaults({**default_newsletter_json(), "public_site_base_url": ""})
    assert m["public_site_base_url"] == "https://custom.example"


@pytest.fixture()
def nl_settings_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProductSetting.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_save_patch_empty_string_does_not_clear_stored(nl_settings_db) -> None:
    save_newsletter_settings_patch(
        nl_settings_db,
        {"public_site_base_url": "https://stored.example", "smtp_host": "smtp.test"},
    )
    save_newsletter_settings_patch(nl_settings_db, {"public_site_base_url": "", "smtp_host": ""})
    merged = get_newsletter_settings_merged(nl_settings_db)
    assert merged["public_site_base_url"] == "https://stored.example"
    assert merged["smtp_host"] == "smtp.test"
