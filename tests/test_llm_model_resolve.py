"""LLM 模型名：全站固定 deepseek-v4-flash。"""
from __future__ import annotations

from backend.app.llm_settings_service import DEFAULT_LLM_MODEL, resolve_llm_model_name


def test_resolve_always_flash() -> None:
    assert resolve_llm_model_name("") == DEFAULT_LLM_MODEL
    assert resolve_llm_model_name("deepseek-v4-pro") == DEFAULT_LLM_MODEL
    assert resolve_llm_model_name("deepseek-v4-flash") == DEFAULT_LLM_MODEL
