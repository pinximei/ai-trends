"""DeepSeek 模型名：Pro/旧别名 → Flash。"""
from __future__ import annotations

from backend.app.llm_settings_service import normalize_deepseek_model_name


def test_normalize_pro_to_flash() -> None:
    assert normalize_deepseek_model_name("deepseek-v4-pro") == "deepseek-v4-flash"
    assert normalize_deepseek_model_name("deepseek-reasoner") == "deepseek-v4-flash"
    assert normalize_deepseek_model_name("deepseek-chat") == "deepseek-v4-flash"


def test_normalize_keeps_flash() -> None:
    assert normalize_deepseek_model_name("deepseek-v4-flash") == "deepseek-v4-flash"
