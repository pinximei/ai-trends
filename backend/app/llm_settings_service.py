"""后台可配的 LLM（默认 DeepSeek OpenAI 兼容端点）；密钥仅存库内 JSON，接口只回显脱敏。"""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy.orm import Session

from .product_models import ProductSetting

DEFAULT_LLM: dict = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
}


def _mask_key(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if len(s) <= 10:
        return "****"
    return f"{s[:4]}…{s[-4:]}"


def _merged_stored(db: Session) -> dict:
    row = db.get(ProductSetting, "llm")
    m = {**DEFAULT_LLM, **((row.value_json if row else {}) or {})}
    for k in ("provider", "base_url", "model"):
        if not str(m.get(k) or "").strip():
            m[k] = DEFAULT_LLM[k]
    m["api_key"] = str(m.get("api_key") or "").strip()
    return m


def get_llm_settings_public(db: Session) -> dict:
    """供管理端展示；不含明文 api_key。"""
    m = _merged_stored(db)
    key = (m.get("api_key") or "").strip()
    return {
        "provider": str(m.get("provider") or DEFAULT_LLM["provider"]),
        "base_url": str(m.get("base_url") or DEFAULT_LLM["base_url"]),
        "model": str(m.get("model") or DEFAULT_LLM["model"]),
        "api_key_masked": _mask_key(key),
        "has_api_key": bool(key),
        "env_fallback": bool(os.getenv("AISOU_LLM_API_KEY", "").strip()),
    }


def resolve_llm_http_config(db: Session) -> tuple[str, str, str]:
    """
    返回 (base_url, api_key, model)。
    优先级：库内 product_settings_kv.llm → 环境变量 AISOU_LLM_*。
    """
    m = _merged_stored(db)
    base = (m.get("base_url") or "").strip() or os.getenv("AISOU_LLM_BASE_URL", "https://api.openai.com/v1").strip()
    key = (m.get("api_key") or "").strip() or os.getenv("AISOU_LLM_API_KEY", "").strip()
    model = (m.get("model") or "").strip() or os.getenv("AISOU_LLM_MODEL", "gpt-4o-mini").strip()
    return base.rstrip("/"), key, model


def save_llm_settings_patch(db: Session, patch: dict) -> dict:
    """patch 可含 provider, base_url, model, api_key；api_key 空串表示不修改已存密钥。"""
    row = db.get(ProductSetting, "llm")
    cur = _merged_stored(db)
    if not row:
        row = ProductSetting(key="llm", value_json={})
        db.add(row)
    for k in ("provider", "base_url", "model"):
        if k in patch and patch[k] is not None:
            v = str(patch[k]).strip()
            if v:
                cur[k] = v
    if "api_key" in patch and patch["api_key"] is not None:
        nk = str(patch["api_key"]).strip()
        if nk:
            cur["api_key"] = nk
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_llm_settings_public(db)
