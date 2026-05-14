"""邮件订阅日报：配置存 product_settings_kv.newsletter；发信参数可脱敏读写。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .product_models import ProductSetting

NEWSLETTER_KEY = "newsletter"


def default_newsletter_json() -> dict[str, Any]:
    return {
        "cron_enabled": False,
        "generate_enabled": False,
        "send_enabled": False,
        "article_limit": 36,
        "daily_hour": 9,
        "daily_minute": 0,
        "public_site_base_url": "",
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "mail_from": "",
        "smtp_use_tls": False,
        "bcc_batch": 40,
        "footer_note": "",
    }


def _merged_stored(db: Session) -> dict[str, Any]:
    row = db.get(ProductSetting, NEWSLETTER_KEY)
    return {**default_newsletter_json(), **((row.value_json if row else {}) or {})}


def _env_fallback_smtp(m: dict[str, Any]) -> dict[str, Any]:
    """库内为空时回退环境变量（兼容旧部署）。"""
    out = dict(m)
    if not str(out.get("smtp_host") or "").strip():
        out["smtp_host"] = (os.environ.get("NEWSLETTER_SMTP_HOST") or "").strip()
    port = int(out.get("smtp_port") or 0)
    if not port:
        out["smtp_port"] = int(os.environ.get("NEWSLETTER_SMTP_PORT", "465") or 465)
    if not str(out.get("smtp_user") or "").strip():
        out["smtp_user"] = (os.environ.get("NEWSLETTER_SMTP_USER") or "").strip()
    if not str(out.get("smtp_password") or "").strip():
        out["smtp_password"] = (os.environ.get("NEWSLETTER_SMTP_PASSWORD") or "").strip()
    if not str(out.get("mail_from") or "").strip():
        out["mail_from"] = (os.environ.get("NEWSLETTER_MAIL_FROM") or out.get("smtp_user") or "").strip()
    if not str(out.get("public_site_base_url") or "").strip():
        out["public_site_base_url"] = (os.environ.get("AITRENDS_PUBLIC_BASE_URL") or "").strip()
    return out


def _normalize_merged(m: dict[str, Any]) -> dict[str, Any]:
    out = dict(m)
    out["cron_enabled"] = bool(out.get("cron_enabled", False))
    out["generate_enabled"] = bool(out.get("generate_enabled", False))
    out["send_enabled"] = bool(out.get("send_enabled", False))
    out["article_limit"] = max(1, min(80, int(out.get("article_limit") or 36)))
    out["daily_hour"] = max(0, min(23, int(out.get("daily_hour") or 9)))
    out["daily_minute"] = max(0, min(59, int(out.get("daily_minute") or 0)))
    out["smtp_port"] = max(1, min(65535, int(out.get("smtp_port") or 465)))
    out["bcc_batch"] = max(1, min(80, int(out.get("bcc_batch") or 40)))
    out["smtp_use_tls"] = bool(out.get("smtp_use_tls", False))
    for k in ("smtp_host", "smtp_user", "smtp_password", "mail_from", "public_site_base_url", "footer_note"):
        out[k] = str(out.get(k) or "").strip()
    return out


def get_newsletter_settings_merged(db: Session) -> dict[str, Any]:
    """运行时使用：含环境变量回退后的 SMTP 等。"""
    return _normalize_merged(_env_fallback_smtp(_merged_stored(db)))


def get_newsletter_settings_public(db: Session) -> dict[str, Any]:
    """管理端展示：密码脱敏。"""
    m = dict(_normalize_merged(_merged_stored(db)))
    pw = str(m.pop("smtp_password", "") or "")
    m["smtp_password_masked"] = "****" if pw else ""
    m["has_smtp_password"] = bool(pw)
    return m


def ensure_newsletter_settings_row(db: Session) -> None:
    if db.get(ProductSetting, NEWSLETTER_KEY):
        return
    db.add(ProductSetting(key=NEWSLETTER_KEY, value_json=default_newsletter_json()))
    db.commit()


def save_newsletter_settings_patch(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    """patch 中空字符串的 smtp_password 表示不修改已存密码。"""
    row = db.get(ProductSetting, NEWSLETTER_KEY)
    cur = _merged_stored(db)
    if not row:
        row = ProductSetting(key=NEWSLETTER_KEY, value_json={})
        db.add(row)
    bool_keys = ("cron_enabled", "generate_enabled", "send_enabled", "smtp_use_tls")
    int_keys = ("article_limit", "daily_hour", "daily_minute", "smtp_port", "bcc_batch")
    str_keys = (
        "public_site_base_url",
        "smtp_host",
        "smtp_user",
        "mail_from",
        "footer_note",
    )
    for k in bool_keys:
        if k in patch:
            cur[k] = bool(patch[k])
    for k in int_keys:
        if k in patch:
            cur[k] = int(patch[k])
    for k in str_keys:
        if k in patch:
            cur[k] = str(patch[k] or "").strip()
    if "smtp_password" in patch and patch["smtp_password"] is not None:
        nk = str(patch["smtp_password"]).strip()
        if nk:
            cur["smtp_password"] = nk
    row.value_json = _normalize_merged(cur)
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_newsletter_settings_public(db)
