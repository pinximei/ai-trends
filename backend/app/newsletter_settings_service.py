"""邮件订阅日报：配置存 product_settings_kv.newsletter；发信参数可脱敏读写（运行以库为准）。`backend/.env` 中的 NEWSLETTER_* / AITRENDS_PUBLIC_BASE_URL 可继续保留作备份，库内为空时启动会一次性迁入。"""
from __future__ import annotations

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
        "feishu_enabled": False,
        "article_limit": 36,
        "apps_limit": 12,
        "news_limit": 12,
        "llm_apps_limit": 3,
        "llm_news_limit": 3,
        "daily_hour": 23,
        "daily_minute": 50,
        "public_site_base_url": "",
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "mail_from": "",
        "smtp_use_tls": False,
        "feishu_webhook_url": "",
        "bcc_batch": 40,
        "footer_note": "",
        # 定时任务与订阅校验：可在后台「邮件订阅」页修改
        "daily_digest_job_enabled": True,
        "subscribe_verify_mx": True,
    }


def _merged_stored(db: Session) -> dict[str, Any]:
    row = db.get(ProductSetting, NEWSLETTER_KEY)
    return {**default_newsletter_json(), **((row.value_json if row else {}) or {})}


def _normalize_merged(m: dict[str, Any]) -> dict[str, Any]:
    out = dict(m)
    out["cron_enabled"] = bool(out.get("cron_enabled", False))
    out["generate_enabled"] = bool(out.get("generate_enabled", False))
    out["send_enabled"] = bool(out.get("send_enabled", False))
    out["feishu_enabled"] = bool(out.get("feishu_enabled", False))
    out["daily_digest_job_enabled"] = bool(out.get("daily_digest_job_enabled", True))
    out["subscribe_verify_mx"] = bool(out.get("subscribe_verify_mx", True))
    out["article_limit"] = max(1, min(80, int(out.get("article_limit") or 36)))
    out["apps_limit"] = max(1, min(40, int(out.get("apps_limit") or min(12, out["article_limit"] // 2 or 12))))
    out["news_limit"] = max(1, min(40, int(out.get("news_limit") or min(12, out["article_limit"] // 2 or 12))))
    out["llm_apps_limit"] = max(0, min(8, int(out.get("llm_apps_limit", 3))))
    out["llm_news_limit"] = max(0, min(8, int(out.get("llm_news_limit", 3))))
    out["daily_hour"] = max(0, min(23, int(out.get("daily_hour") or 9)))
    out["daily_minute"] = max(0, min(59, int(out.get("daily_minute") or 0)))
    out["smtp_port"] = max(1, min(65535, int(out.get("smtp_port") or 465)))
    out["bcc_batch"] = max(1, min(80, int(out.get("bcc_batch") or 40)))
    out["smtp_use_tls"] = bool(out.get("smtp_use_tls", False))
    for k in ("smtp_host", "smtp_user", "smtp_password", "mail_from", "public_site_base_url", "footer_note"):
        out[k] = str(out.get(k) or "").strip()
    return out


def get_newsletter_settings_merged(db: Session) -> dict[str, Any]:
    """运行时使用：仅数据库配置。"""
    return _normalize_merged(_merged_stored(db))


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return f"{v[:4]}...{v[-4:]}"


def get_newsletter_settings_public(db: Session) -> dict[str, Any]:
    """管理端展示：密码 / Webhook 脱敏。"""
    m = dict(_normalize_merged(_merged_stored(db)))
    pw = str(m.pop("smtp_password", "") or "")
    m["smtp_password_masked"] = "****" if pw else ""
    m["has_smtp_password"] = bool(pw)
    wh = str(m.pop("feishu_webhook_url", "") or "")
    m["feishu_webhook_masked"] = _mask_secret(wh)
    m["has_feishu_webhook"] = bool(wh)
    return m


def ensure_newsletter_settings_row(db: Session) -> None:
    if db.get(ProductSetting, NEWSLETTER_KEY):
        return
    db.add(ProductSetting(key=NEWSLETTER_KEY, value_json=default_newsletter_json()))
    db.commit()


def _sync_push_channel_flags(cur: dict[str, Any]) -> None:
    """任一推送渠道开启时自动打开生成与定时；全关则关闭（运营端只需勾选邮件/飞书）。"""
    email_on = bool(cur.get("send_enabled"))
    feishu_on = bool(cur.get("feishu_enabled"))
    any_on = email_on or feishu_on
    cur["cron_enabled"] = any_on
    cur["generate_enabled"] = any_on
    cur["daily_digest_job_enabled"] = any_on


def save_newsletter_settings_patch(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    """patch 中空字符串的 smtp_password 表示不修改已存密码。"""
    row = db.get(ProductSetting, NEWSLETTER_KEY)
    cur = _merged_stored(db)
    if not row:
        row = ProductSetting(key=NEWSLETTER_KEY, value_json={})
        db.add(row)
    bool_keys = (
        "cron_enabled",
        "generate_enabled",
        "send_enabled",
        "feishu_enabled",
        "smtp_use_tls",
        "daily_digest_job_enabled",
        "subscribe_verify_mx",
    )
    int_keys = (
        "article_limit",
        "apps_limit",
        "news_limit",
        "llm_apps_limit",
        "llm_news_limit",
        "daily_hour",
        "daily_minute",
        "smtp_port",
        "bcc_batch",
    )
    str_keys = (
        "public_site_base_url",
        "smtp_host",
        "smtp_user",
        "mail_from",
        "footer_note",
        "feishu_webhook_url",
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
    if "feishu_webhook_url" in patch and patch["feishu_webhook_url"] is not None:
        nw = str(patch["feishu_webhook_url"]).strip()
        if nw:
            cur["feishu_webhook_url"] = nw
    if "send_enabled" in patch or "feishu_enabled" in patch:
        _sync_push_channel_flags(cur)
    if "smtp_port" in patch and "smtp_use_tls" not in patch:
        cur["smtp_use_tls"] = int(cur.get("smtp_port") or 465) != 465
    row.value_json = _normalize_merged(cur)
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_newsletter_settings_public(db)
