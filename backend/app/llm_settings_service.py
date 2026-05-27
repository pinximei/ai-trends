"""后台可配的 LLM（默认 DeepSeek OpenAI 兼容端点）；密钥存库内 JSON，接口只回显脱敏。`.env` 中的 AITRENDS_LLM_* 可在库为空时由启动迁移写入库，文件可继续保留作备份。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .product_models import ProductSetting

FLASH_MODEL = "deepseek-v4-flash"

DEFAULT_LLM: dict = {
    "provider": "deepseek",
    "base_url": "https://api.deepseek.com/v1",
    "model": FLASH_MODEL,
    "api_key": "",
}

# 历史别名 / Pro·推理档 → Flash（非思考，更省、更快）
_LEGACY_DEEPSEEK_MODELS_TO_FLASH: frozenset[str] = frozenset(
    {
        "deepseek-chat",
        "deepseek-reasoner",
        "deepseek-v4-pro",
        "deepseek-pro",
    }
)


def normalize_deepseek_model_name(model: str) -> str:
    """将 DeepSeek Pro/旧别名统一为 ``deepseek-v4-flash``；非 deepseek 模型原样返回。"""
    m = (model or "").strip()
    if not m:
        return FLASH_MODEL
    ml = m.lower()
    if "flash" in ml:
        return m
    if not ml.startswith("deepseek"):
        return m
    if ml in _LEGACY_DEEPSEEK_MODELS_TO_FLASH or "pro" in ml or "reasoner" in ml:
        return FLASH_MODEL
    return m


def repair_llm_model_to_flash(db: Session) -> bool:
    """若库内仍为 Pro/旧别名，一次性改为 Flash（返回是否写入）。"""
    row = db.get(ProductSetting, "llm")
    if not row or not isinstance(row.value_json, dict):
        return False
    cur = dict(row.value_json)
    before = str(cur.get("model") or "").strip()
    after = normalize_deepseek_model_name(before)
    if not before or before == after:
        return False
    cur["model"] = after
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
        "model": normalize_deepseek_model_name(str(m.get("model") or DEFAULT_LLM["model"])),
        "api_key_masked": _mask_key(key),
        "has_api_key": bool(key),
    }


def resolve_llm_http_config(db: Session) -> tuple[str, str, str]:
    """
    返回 (base_url, api_key, model)。
    仅使用库内 product_settings_kv.llm；请在后台「LLM」页配置。
    """
    m = _merged_stored(db)
    base = (m.get("base_url") or "").strip() or DEFAULT_LLM["base_url"].strip()
    key = (m.get("api_key") or "").strip()
    model = normalize_deepseek_model_name((m.get("model") or "").strip() or DEFAULT_LLM["model"].strip())
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
                cur[k] = normalize_deepseek_model_name(v) if k == "model" else v
    if "api_key" in patch and patch["api_key"] is not None:
        nk = str(patch["api_key"]).strip()
        if nk:
            cur["api_key"] = nk
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_llm_settings_public(db)
