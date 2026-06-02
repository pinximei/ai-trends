"""润色 header 回填与可选 Tab 裁剪。"""
from __future__ import annotations

from backend.app.domain import articles as art
from backend.app.domain.replication_analysis import FEED_CARD_TAB_REPLICATION
from backend.app.llm_service import _normalize_polish_payload
from backend.app.polish_publish_compat import fill_polish_header_from_fallbacks

_VALID_DESC_SUMMARY = (
    "描述 tab：用多句话说明事件主体、经过与结论，让读者不看标题也能懂发生了什么；"
    "此处为测试用长摘要，满足列表卡片与发布校验的最低字数门槛要求。。"
)
_VALID_DESC_BODY = "## 描述\n\n" + "事件背景与参与方说明。" * 28


def test_fill_title_from_product_hunt_snippet() -> None:
    snippet = '{"name":"Folk","tagline":"A social app for communities"}'
    raw = {
        "feed_kind": "apps",
        "categories": ["应用产品"],
        "tabs": [
            {
                "label": "描述",
                "summary": _VALID_DESC_SUMMARY,
                "body_md": _VALID_DESC_BODY,
            },
        ],
    }
    filled = fill_polish_header_from_fallbacks(
        raw,
        snippet=snippet,
        admin_source_key="product_hunt",
        rule_title="同步资源 · Folk",
        rule_summary="规则摘要" * 12,
    )
    assert filled["title"] == "Folk"
    assert len(filled["summary"]) >= 36


def test_normalize_accepts_tool_without_title_when_snippet_has_name() -> None:
    snippet = '{"name":"Dune Keypad","tagline":"Mechanical keyboard"}'
    tool_args = {
        "feed_kind": "apps",
        "categories": ["应用产品"],
        "tabs": [
            {
                "label": "描述",
                "summary": _VALID_DESC_SUMMARY,
                "body_md": _VALID_DESC_BODY,
            },
        ],
    }
    out, err = _normalize_polish_payload(
        tool_args,
        default_feed_kind="apps",
        snippet=snippet,
        admin_source_key="product_hunt",
        rule_title="同步资源 · Dune Keypad",
        rule_summary="规则摘要" * 12,
    )
    assert err == ""
    assert out is not None
    assert out["title"] == "Dune Keypad"


def test_ph_kv_field_lines_expand_passes_metadata_check() -> None:
    from backend.app.text_display import (
        body_is_connector_kv_metadata,
        expand_connector_kv_lines_to_narrative,
        prepare_description_tab_body,
    )

    raw = (
        "产品：Databox MCP\n"
        "标语：Analytics in Slack\n"
        "投票：128\n"
        "官网：https://databox.com\n"
    )
    assert body_is_connector_kv_metadata(raw)
    narr = expand_connector_kv_lines_to_narrative(raw)
    assert not body_is_connector_kv_metadata(narr)
    prepared = prepare_description_tab_body(raw, admin_source_key="product_hunt")
    assert not body_is_connector_kv_metadata(prepared)
    assert "Databox" in prepared


def test_prune_drops_weak_optional_replication_tab() -> None:
    data = {
        "title": "某仓库",
        "summary": "面向开发者的开源工具，提供本地优先的工作流与可扩展插件体系，适合独立开发者评估复刻价值。" * 2,
        "body_md": "总览",
        "categories": ["开源客户端(好抄)"],
        "feed_kind": "apps",
        "tabs": [
            {
                "label": "描述",
                "summary": _VALID_DESC_SUMMARY,
                "body_md": _VALID_DESC_BODY,
            },
            {
                "label": FEED_CARD_TAB_REPLICATION,
                "summary": "短",
                "body_md": "太短",
            },
        ],
    }
    pruned = art.prune_substandard_optional_tabs(data, admin_source_key="github")
    labels = [t["label"] for t in pruned["tabs"]]
    assert "描述" in labels
    assert FEED_CARD_TAB_REPLICATION not in labels
    assert art.validate_llm_polish_for_publish(pruned, admin_source_key="github")
