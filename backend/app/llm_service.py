"""大模型调用：灵感生成；未配置 API 时回退模板。"""
from __future__ import annotations

import os

import httpx
from sqlalchemy.orm import Session

from .product_models import LlmUsageLog


def _log_usage(
    db: Session,
    scenario: str,
    model: str,
    input_tok: int,
    output_tok: int,
    success: bool,
    ref_type: str,
    ref_id: str,
    admin_user_id: int | None = None,
    err: str | None = None,
):
    db.add(
        LlmUsageLog(
            scenario=scenario,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            admin_user_id=admin_user_id,
            ref_type=ref_type,
            ref_id=ref_id,
            success=success,
            error_code=err,
        )
    )
    db.commit()


def chat_completion(
    db: Session,
    *,
    system: str,
    user: str,
    scenario: str,
    ref_type: str,
    ref_id: str,
    admin_user_id: int | None = None,
) -> tuple[str, int, int]:
    """OpenAI 兼容接口；AISOU_LLM_BASE_URL + AISOU_LLM_API_KEY + AISOU_LLM_MODEL"""
    base = os.getenv("AISOU_LLM_BASE_URL", "https://api.openai.com/v1")
    key = os.getenv("AISOU_LLM_API_KEY", "")
    model = os.getenv("AISOU_LLM_MODEL", "gpt-4o-mini")
    if not key:
        raise RuntimeError("AISOU_LLM_API_KEY not set")

    url = base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.4,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    it = int(usage.get("prompt_tokens") or 0)
    ot = int(usage.get("completion_tokens") or 0)
    _log_usage(db, scenario, model, it, ot, True, ref_type, ref_id, admin_user_id)
    return text, it, ot


def generate_inspiration_body(
    db: Session,
    *,
    context_md: str,
    username: str,
    inspiration_id: int,
    version_no: int,
    admin_user_id: int | None = None,
) -> str:
    """生成灵感正文；无 API Key 时返回结构化占位。"""
    if not os.getenv("AISOU_LLM_API_KEY"):
        return (
            f"## 灵感草稿（未配置 LLM，规则回退）\n\n"
            f"操作者：{username}\n\n### 上下文摘要\n\n{context_md[:4000]}\n"
        )
    system = "你是产业分析助手，根据给定数据摘要输出简洁的灵感要点（Markdown），不要编造未提供的数据。"
    user = f"请基于以下上下文输出 3～5 条可验证的灵感方向：\n\n{context_md}"
    text, _, _ = chat_completion(
        db,
        system=system,
        user=user,
        scenario="inspiration_generate",
        ref_type="inspiration",
        ref_id=f"{inspiration_id}:{version_no}",
        admin_user_id=admin_user_id,
    )
    return text
