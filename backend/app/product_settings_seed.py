"""一次性把 `backend/.env`（或进程环境）里已有的可后台项迁入 product_settings_kv；迁入后运行时以库为准。

`.env` 文件建议继续保留：其中的 Key 仍可作为备份，并在库内对应项为空时由启动逻辑复用写入库。
"""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy.orm import Session

from .llm_settings_service import DEFAULT_LLM, _merged_stored as _llm_merged
from .newsletter_settings_service import NEWSLETTER_KEY, default_newsletter_json, ensure_newsletter_settings_row
from .product_models import ProductSetting
from .runtime_settings_service import RUNTIME_KEY, _env_defaults as _runtime_env_defaults, _normalize as _norm_runtime, ensure_runtime_settings_row


def _runtime_storable_keys() -> tuple[str, ...]:
    return (
        "cors_origins_csv",
        "jwt_ttl_seconds",
        "allowed_skew_seconds",
        "require_https",
        "allow_insecure_localhost",
        "admin_cookie_secure",
        "app_env",
        "demo_seed_enabled",
        "legacy_admin_enabled",
        "app_release_label",
        "hot_llm_model",
    )


def seed_runtime_from_env_if_empty(db: Session) -> bool:
    """若 runtime 行为空 JSON，则用当前环境变量合成一行写入库（仅一次）。"""
    ensure_runtime_settings_row(db)
    row = db.get(ProductSetting, RUNTIME_KEY)
    if not row:
        return False
    v = row.value_json
    if isinstance(v, dict) and len(v) > 0:
        return False
    merged = _norm_runtime(_runtime_env_defaults())
    row.value_json = {k: merged[k] for k in _runtime_storable_keys()}
    db.commit()
    return True


def seed_llm_from_env_if_empty(db: Session) -> bool:
    """若库内尚无 LLM api_key，且环境变量提供了密钥，则写入库（仅补空）。"""
    m = _llm_merged(db)
    if (m.get("api_key") or "").strip():
        return False
    key = (os.getenv("AITRENDS_LLM_API_KEY") or "").strip()
    if not key:
        return False
    row = db.get(ProductSetting, "llm")
    if not row:
        row = ProductSetting(key="llm", value_json={})
        db.add(row)
    cur = {**DEFAULT_LLM, **((row.value_json if row else {}) or {})}
    cur["api_key"] = key
    ev_base = (os.getenv("AITRENDS_LLM_BASE_URL") or "").strip()
    if ev_base:
        cur["base_url"] = ev_base.rstrip("/")
    ev_model = (os.getenv("AITRENDS_LLM_MODEL") or "").strip()
    if ev_model:
        cur["model"] = ev_model
    row.value_json = cur
    db.commit()
    return True


def seed_newsletter_from_env_if_needed(db: Session) -> bool:
    """补齐 newsletter 行：SMTP 等仍空时从环境变量写入；新增字段仅在旧 JSON 缺键时从环境推断一次。"""
    ensure_newsletter_settings_row(db)
    row = db.get(ProductSetting, NEWSLETTER_KEY)
    raw: dict[str, Any] = dict(row.value_json) if row and isinstance(row.value_json, dict) else {}
    merged: dict[str, Any] = {**default_newsletter_json(), **raw}
    changed = False

    def _blank(x: Any) -> bool:
        return not str(x or "").strip()

    if _blank(merged.get("smtp_host")) and (os.getenv("NEWSLETTER_SMTP_HOST") or "").strip():
        merged["smtp_host"] = (os.getenv("NEWSLETTER_SMTP_HOST") or "").strip()
        changed = True
    if not int(merged.get("smtp_port") or 0):
        merged["smtp_port"] = int(os.getenv("NEWSLETTER_SMTP_PORT", "465") or 465)
        changed = True
    if _blank(merged.get("smtp_user")) and (os.getenv("NEWSLETTER_SMTP_USER") or "").strip():
        merged["smtp_user"] = (os.getenv("NEWSLETTER_SMTP_USER") or "").strip()
        changed = True
    if _blank(merged.get("smtp_password")) and (os.getenv("NEWSLETTER_SMTP_PASSWORD") or "").strip():
        merged["smtp_password"] = (os.getenv("NEWSLETTER_SMTP_PASSWORD") or "").strip()
        changed = True
    if _blank(merged.get("mail_from")):
        mf = (os.getenv("NEWSLETTER_MAIL_FROM") or merged.get("smtp_user") or "").strip()
        if mf:
            merged["mail_from"] = mf
            changed = True
    if _blank(merged.get("public_site_base_url")) and (os.getenv("AITRENDS_PUBLIC_BASE_URL") or "").strip():
        merged["public_site_base_url"] = (os.getenv("AITRENDS_PUBLIC_BASE_URL") or "").strip()
        changed = True

    if "daily_digest_job_enabled" not in raw:
        env_off = (os.getenv("NEWSLETTER_DAILY_ENABLED") or "").strip().lower() in ("0", "false", "no", "off")
        merged["daily_digest_job_enabled"] = not env_off
        changed = True
    if "subscribe_verify_mx" not in raw:
        ev = (os.getenv("NEWSLETTER_VERIFY_MX", "true") or "").strip().lower()
        merged["subscribe_verify_mx"] = ev in ("1", "true", "yes", "on", "")
        changed = True

    if changed:
        row.value_json = merged
        db.commit()
    return changed


def migrate_runtime_demo_seed_from_env(db: Session) -> bool:
    """若库内 runtime 从未写入 demo_seed_enabled，且设置了 AITRENDS_ENABLE_DEMO_SEED，则迁移一次到库。"""
    if os.getenv("AITRENDS_ENABLE_DEMO_SEED") is None:
        return False
    ensure_runtime_settings_row(db)
    row = db.get(ProductSetting, RUNTIME_KEY)
    if not row or not isinstance(row.value_json, dict) or "demo_seed_enabled" in row.value_json:
        return False
    from .runtime_settings_service import _merge_row_into, _normalize, _static_defaults

    merged = _normalize(_merge_row_into(_static_defaults(), row))
    merged["demo_seed_enabled"] = os.getenv("AITRENDS_ENABLE_DEMO_SEED", "").strip().lower() in ("1", "true", "yes", "on")
    row.value_json = {k: merged[k] for k in _runtime_storable_keys()}
    db.commit()
    return True


def seed_product_settings_from_environment(db: Session) -> dict[str, bool]:
    """启动时调用：空库/空行时从环境变量灌入可后台管理的配置各一次。"""
    demo_m = migrate_runtime_demo_seed_from_env(db)
    return {
        "runtime_demo_seed": demo_m,
        "runtime": seed_runtime_from_env_if_empty(db),
        "llm": seed_llm_from_env_if_empty(db),
        "newsletter": seed_newsletter_from_env_if_needed(db),
    }
