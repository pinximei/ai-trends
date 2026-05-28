"""后台可配的 LLM（默认 DeepSeek OpenAI 兼容端点）；密钥存库内 JSON，接口只回显脱敏。`.env` 中的 AITRENDS_LLM_* 可在库为空时由启动迁移写入库，文件可继续保留作备份。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .product_models import ProductSetting

# 全站固定 Flash，不读后台/环境变量中的其它模型名
DEFAULT_LLM_MODEL = "deepseek-v4-flash"
FLASH_MODEL = DEFAULT_LLM_MODEL

DEFAULT_LLM: dict = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": DEFAULT_LLM_MODEL,
    "api_key": "",
}


def resolve_llm_model_name(_model: str = "") -> str:
    """固定 Flash；参数仅保留以兼容旧调用。"""
    return DEFAULT_LLM_MODEL


def repair_llm_model_locked_flash(db: Session) -> bool:
    """库内若存了其它模型名，启动时改回 Flash。"""
    row = db.get(ProductSetting, "llm")
    if not row or not isinstance(row.value_json, dict):
        return False
    cur = dict(row.value_json)
    before = str(cur.get("model") or "").strip()
    if before == DEFAULT_LLM_MODEL:
        return False
    cur["model"] = DEFAULT_LLM_MODEL
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    return True


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
        if not str(m.get(k) or "").strip() and k != "model":
            m[k] = DEFAULT_LLM[k]
    m["model"] = DEFAULT_LLM_MODEL
    m["api_key"] = str(m.get("api_key") or "").strip()
    return m


def get_llm_settings_public(db: Session) -> dict:
    """供管理端展示；不含明文 api_key。"""
    m = _merged_stored(db)
    key = (m.get("api_key") or "").strip()
    return {
        "provider": str(m.get("provider") or DEFAULT_LLM["provider"]),
        "base_url": str(m.get("base_url") or DEFAULT_LLM["base_url"]),
        "model": DEFAULT_LLM_MODEL,
        "api_key_masked": _mask_key(key),
        "has_api_key": bool(key),
    }


def resolve_llm_http_config(db: Session) -> tuple[str, str, str]:
    """
    返回 (base_url, api_key, model)。
    model 恒为 ``deepseek-v4-flash``；仅 base_url / api_key 来自库配置。
    """
    m = _merged_stored(db)
    base = (m.get("base_url") or "").strip() or DEFAULT_LLM["base_url"].strip()
    key = (m.get("api_key") or "").strip()
    return base.rstrip("/"), key, DEFAULT_LLM_MODEL


def save_llm_settings_patch(db: Session, patch: dict) -> dict:
    """patch 可含 provider, base_url, api_key；model 忽略，恒为 Flash。"""
    row = db.get(ProductSetting, "llm")
    cur = _merged_stored(db)
    if not row:
        row = ProductSetting(key="llm", value_json={})
        db.add(row)
    for k in ("provider", "base_url"):
        if k in patch and patch[k] is not None:
            v = str(patch[k]).strip()
            if v:
                cur[k] = v
    cur["model"] = DEFAULT_LLM_MODEL
    if "api_key" in patch and patch["api_key"] is not None:
        nk = str(patch["api_key"]).strip()
        if nk:
            cur["api_key"] = nk
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_llm_settings_public(db)
