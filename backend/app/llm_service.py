"""大模型调用：灵感生成、连接器文章润色；未配置 API 时回退模板。"""
from __future__ import annotations

import json
import re

import httpx
from sqlalchemy.orm import Session

from .domain.articles import validate_llm_polish_for_publish
from .llm_settings_service import resolve_llm_http_config
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
    response_json: bool = False,
) -> tuple[str, int, int]:
    """OpenAI 兼容 Chat Completions；优先读库内「AI 资讯」配置，其次环境变量 AISOU_LLM_*。"""
    base, key, model = resolve_llm_http_config(db)
    if not key:
        raise RuntimeError(
            "LLM 未配置：在管理端「AI 资讯配置」填写 DeepSeek API Key，或在环境变量 / backend/.env 中设置 AISOU_LLM_API_KEY"
        )

    url = base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.4,
    }
    if response_json:
        body["response_format"] = {"type": "json_object"}
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


def _extract_json_object(raw: str) -> dict | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


def polish_connector_article(
    db: Session,
    *,
    snippet: str,
    connector_name: str,
    admin_source_key: str,
    segment_label: str,
    rule_title: str,
    rule_summary: str,
    value_score: float,
    ref_id: str,
    feed_kind: str = "news",
) -> dict | None:
    """
    仅在高价值已确认后调用：必须用模型重写全文并分类；输出含多 tab（概要 + 详情 Markdown）。
    feed_kind 为 news（资讯）或 apps（应用），决定文风与 categories 侧重。
    校验失败或未配置 Key 时返回 None；调用方不得再落规则快照稿。
    """
    if not resolve_llm_http_config(db)[1]:
        return None
    fk = (feed_kind or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    snippet_cut = (snippet or "")[:6000]
    if fk == "apps":
        stream_hint = (
            "当前条目归类为 **AI 应用** 泳道：面向产品/可运行应用发布与能力更新；语气偏产品速递与开发者向。"
            "categories 需要 **约 10 个** 中文短标签（**8～12 条**，以 9～11 条为佳）："
            "前 1～2 条可稍长表示主主题，其余为更短的具体角度（产品形态、场景、技术栈、受众等），"
            "彼此少重复；不要只写 2～3 个大词糊弄，也不要超过 12 条刷屏。"
        )
    else:
        stream_hint = (
            "当前条目归类为 **AI 资讯** 泳道：面向行业动态、论文、社区与技术新闻；语气偏信息摘要与要点。"
            "categories 需要 **约 10 个** 中文短标签（**8～12 条**，以 9～11 条为佳）："
            "前 1～2 条可稍长表示主叙事，其余为更短的信息维度（主体、事件类型、领域、影响等），"
            "彼此少重复；不要只写 2～3 个大词糊弄，也不要超过 12 条刷屏。"
        )
    system = (
        "你是 AI 行业「趋势雷达」编辑。只根据用户提供的原始 API 片段与占位标题写稿，禁止编造未出现的名称、数字与链接。"
        f"{stream_hint}"
        "输出一个 JSON 对象，键必须为：title, summary, body_md, categories, feed_kind, tabs。"
        "title 为单行中文标题；summary 为 1～2 句中文总摘要（列表卡片用）；"
        "body_md 为可选 Markdown 总览（可与 tabs 呼应；若无总览可写简短衔接段）；"
        "categories 为字符串数组，**8～12 条（含边界）**，每条 2～10 个汉字为宜、须为中文，"
        "总量以 **9～11 条** 为目标；须与 feed_kind 自洽；"
        'feed_kind 只能为 JSON 字符串 "news" 或 "apps"。'
        "tabs 为数组，至少 2 个、至多 5 个对象；每个对象键 label（2～8 字 tab 标题）、"
        "summary（1～2 句，展示在 tab 行上的概要）、body_md（该 tab 的详细正文，Markdown，可多段列表）。"
        "tabs 应覆盖原文信息要点，结构清晰，禁止空字段。"
    )
    user = (
        f"数据源规则推断的参考泳道 feed_hint={fk}（news=资讯 / apps=应用）。请阅读片段后在输出中给出 feed_kind，"
        f"仅允许 news 或 apps；允许与 feed_hint 不一致，但 title、summary、categories 必须与 feed_kind 自洽。\n"
        f"数据源: {admin_source_key} / 连接器: {connector_name} / 板块: {segment_label}\n"
        f"规则价值分(0-100): {value_score:.0f}\n"
        f"占位标题: {rule_title}\n"
        f"占位摘要: {rule_summary}\n\n"
        f"原始片段:\n```\n{snippet_cut}\n```"
    )
    try:
        try:
            raw, _, _ = chat_completion(
                db,
                system=system,
                user=user,
                scenario="article_ingest_polish",
                ref_type="connector_article",
                ref_id=ref_id[:64],
                response_json=True,
            )
        except Exception:
            raw, _, _ = chat_completion(
                db,
                system=system + " 请只输出一个 JSON 对象，不要其它文字。",
                user=user,
                scenario="article_ingest_polish",
                ref_type="connector_article",
                ref_id=ref_id[:64],
                response_json=False,
            )
        data = _extract_json_object(raw)
        if not data:
            return None
        title = str(data.get("title") or "").strip()
        summary = str(data.get("summary") or "").strip()
        body_md = str(data.get("body_md") or "").strip()
        cats = data.get("categories")
        if not title or not summary:
            return None
        if not isinstance(cats, list):
            cats = []
        else:
            cats = [str(x).strip() for x in cats if str(x).strip()]
        fk_ai = str(data.get("feed_kind") or "").strip().lower()
        out_fk = fk if fk_ai not in ("news", "apps") else fk_ai
        raw_tabs = data.get("tabs")
        norm_tabs: list[dict[str, str]] = []
        if isinstance(raw_tabs, list):
            for t in raw_tabs[:6]:
                if not isinstance(t, dict):
                    continue
                lab = str(t.get("label") or "").strip()
                sm = str(t.get("summary") or "").strip()
                bd = str(t.get("body_md") or "").strip()
                if lab and sm and bd:
                    norm_tabs.append({"label": lab, "summary": sm, "body_md": bd})
        out = {
            "title": title,
            "summary": summary,
            "body_md": body_md or summary,
            "categories": cats,
            "feed_kind": out_fk,
            "tabs": norm_tabs,
        }
        if not validate_llm_polish_for_publish(out):
            return None
        return out
    except Exception:
        return None


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
    if not resolve_llm_http_config(db)[1]:
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
