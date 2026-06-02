"""连接器润色 function/tool 契约。"""
from __future__ import annotations

from backend.app.connector_polish_tool import (
    CONNECTOR_POLISH_TOOL_NAME,
    build_connector_polish_tools,
    connector_polish_tool_choice,
    extract_polish_payload_from_chat_message,
    parse_connector_polish_tool_arguments,
)
from backend.app.domain.articles import FEED_CARD_TAB_DESCRIPTION
from backend.app.llm_service import _normalize_polish_payload


def test_polish_tool_registered_with_fixed_parameters() -> None:
    tools = build_connector_polish_tools()
    assert len(tools) == 1
    fn = tools[0]["function"]
    assert fn["name"] == CONNECTOR_POLISH_TOOL_NAME
    params = fn["parameters"]
    assert "title" in params["properties"]
    assert "tabs" in params["properties"]
    assert params["required"] == ["title", "summary", "categories", "feed_kind", "tabs"]
    tab_item = params["properties"]["tabs"]["items"]
    assert FEED_CARD_TAB_DESCRIPTION in tab_item["properties"]["label"]["enum"]


def test_tool_choice_locks_function_name() -> None:
    choice = connector_polish_tool_choice()
    assert choice["type"] == "function"
    assert choice["function"]["name"] == CONNECTOR_POLISH_TOOL_NAME


def test_extract_polish_from_tool_calls_message() -> None:
    args = {
        "title": "测试产品",
        "summary": "首句钩子：某 AI 工具上线，解决独立开发者冷启动难题，值得一看。" * 2,
        "categories": ["应用产品"],
        "feed_kind": "apps",
        "tabs": [
            {
                "label": FEED_CARD_TAB_DESCRIPTION,
                "summary": "描述 tab 用多句话说明产品定位与目标用户，满足测试字数门槛要求。" * 2,
                "body_md": "## 描述\n\n" + "产品说明正文。" * 30,
            },
        ],
    }
    import json

    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": CONNECTOR_POLISH_TOOL_NAME,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        ],
    }
    got = extract_polish_payload_from_chat_message(msg)
    assert got is not None
    assert got["title"] == "测试产品"
    out, err = _normalize_polish_payload(got, default_feed_kind="apps")
    assert err == ""
    assert out is not None
    assert out["tabs"][0]["label"] == FEED_CARD_TAB_DESCRIPTION


def test_parse_tool_arguments_accepts_dict() -> None:
    d = {"title": "x"}
    assert parse_connector_polish_tool_arguments(d) == d
