"""连接器润色：向 LLM 注册固定参数的 function/tool，约束输出结构。"""
from __future__ import annotations

import json
from typing import Any

from .domain.articles import FACET_ALL_LABELS, FACET_DISPLAY_ORDER
from .domain.replication_analysis import FEED_CARD_TAB_REPLICATION

CONNECTOR_POLISH_TOOL_NAME = "submit_connector_polish"

_TAB_LABEL_ENUM = ("描述", "数据支撑", FEED_CARD_TAB_REPLICATION)
_FEED_KIND_ENUM = ("news", "apps")
_TIER_ENUM = ("S", "A", "B", "C")
_VERDICT_ENUM = ("高价值", "观望", "不建议")
_DIFFICULTY_ENUM = ("低", "中", "高")


def _category_enum() -> list[str]:
    return [c for c in FACET_DISPLAY_ORDER if c in FACET_ALL_LABELS]


def connector_polish_tool_parameters_schema() -> dict[str, Any]:
    """OpenAI Chat Completions `tools[].function.parameters` JSON Schema。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {
                "type": "string",
                "description": "简体中文标题，信息密度高，禁止「同步资源·」占位式标题",
            },
            "summary": {
                "type": "string",
                "description": "卡片摘要≥36字；首句为吸引点击的钩子（疑问/反差/数字），禁止据悉/据报道开头",
            },
            "body_md": {
                "type": "string",
                "description": "总览 Markdown，可较短；长文应写在 tabs 的「描述」body_md",
            },
            "card_value_hook": {
                "type": "string",
                "description": "可选，≤28字价值钩子，含疑问或数字",
            },
            "categories": {
                "type": "array",
                "description": "恰好 1 个规范大类",
                "minItems": 1,
                "maxItems": 1,
                "items": {"type": "string", "enum": _category_enum()},
            },
            "feed_kind": {
                "type": "string",
                "enum": list(_FEED_KIND_ENUM),
                "description": "news=资讯稿，apps=应用/仓库稿",
            },
            "replication_tier": {
                "type": "string",
                "enum": list(_TIER_ENUM),
                "description": "复刻价值档位",
            },
            "tabs": {
                "type": "array",
                "description": "至少 1 项；必须含 label=描述 的 tab；其余 tab 可选",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {
                            "type": "string",
                            "enum": list(_TAB_LABEL_ENUM),
                        },
                        "summary": {"type": "string"},
                        "body_md": {"type": "string"},
                    },
                    "required": ["label", "summary", "body_md"],
                },
            },
            "replication_analysis": {
                "type": "object",
                "description": "仅 feed_kind=apps 时可选；与「变现评估」tab 一致",
                "properties": {
                    "verdict": {"type": "string", "enum": list(_VERDICT_ENUM)},
                    "worth_score": {"type": "integer", "minimum": 1, "maximum": 10},
                    "difficulty": {"type": "string", "enum": list(_DIFFICULTY_ENUM)},
                    "tier_rationale": {"type": "string"},
                    "value_summary": {"type": "string"},
                    "tech_stack": {"type": "array", "items": {"type": "string"}},
                    "implementation_plan": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "phases": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "hours_min": {"type": "integer"},
                                "hours_max": {"type": "integer"},
                                "deliverable": {"type": "string"},
                            },
                        },
                    },
                    "estimated_hours": {
                        "type": "object",
                        "properties": {
                            "mvp_min": {"type": "integer"},
                            "mvp_max": {"type": "integer"},
                            "prod_min": {"type": "integer"},
                            "prod_max": {"type": "integer"},
                        },
                    },
                    "market_position": {
                        "type": "object",
                        "properties": {
                            "target_user": {"type": "string"},
                            "monetization_hypothesis": {"type": "string"},
                        },
                    },
                },
            },
        },
        "required": ["title", "summary", "categories", "feed_kind", "tabs"],
    }


def build_connector_polish_tools() -> list[dict[str, Any]]:
    """注册润色函数，供 Chat Completions `tools` 使用。"""
    return [
        {
            "type": "function",
            "function": {
                "name": CONNECTOR_POLISH_TOOL_NAME,
                "description": (
                    "提交连接器文章润色结果。必须根据用户提供的原始 API 片段填写；"
                    "禁止编造片段中未出现的名称、数字、URL；不足处写「原文未提供」。"
                    "全文简体中文：英文素材须先翻译再写稿（专有名词与 URL 可保留英文）。"
                    "禁止输出 API 键值对 JSON 或 ```json 代码块。"
                ),
                "parameters": connector_polish_tool_parameters_schema(),
            },
        }
    ]


def connector_polish_tool_choice() -> dict[str, Any]:
    return {"type": "function", "function": {"name": CONNECTOR_POLISH_TOOL_NAME}}


def parse_connector_polish_tool_arguments(raw: str | dict | None) -> dict[str, Any] | None:
    """从 tool call 的 function.arguments 解析为 dict。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def extract_polish_payload_from_chat_message(message: dict[str, Any] | None) -> dict[str, Any] | None:
    """从 chat completion 的 message 中提取 submit_connector_polish 的参数。"""
    if not isinstance(message, dict):
        return None
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            if str(fn.get("name") or "").strip() != CONNECTOR_POLISH_TOOL_NAME:
                continue
            parsed = parse_connector_polish_tool_arguments(fn.get("arguments"))
            if parsed:
                return parsed
    # 少数兼容端点把参数放在 content
    content = str(message.get("content") or "").strip()
    if content.startswith("{"):
        return parse_connector_polish_tool_arguments(content)
    return None
