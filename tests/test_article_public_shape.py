"""AI 入库结构与公开 API / 前台 TypeScript 契约一致性（无 DB）。"""
from __future__ import annotations

import json

from backend.app.domain import articles as art


def test_validate_llm_polish_accepts_minimal_valid_payload() -> None:
    data = {
        "title": "测试标题",
        "summary": "这是摘要句子，满足长度。",
        "body_md": "## 总览\n\n正文。",
        "categories": ["大模型", "开源"],
        "feed_kind": "news",
        "tabs": [
            {"label": "要点", "summary": "概要一句足够八字符以上", "body_md": "## A\n\n- 列表项\n- 第二项" * 1},
            {"label": "细节", "summary": "另一概要用于 tab 行展示", "body_md": "## B\n\n正文段落不少于十六字。"},
        ],
    }
    assert art.validate_llm_polish_for_publish(data) is True


def test_validate_llm_polish_rejects_single_tab() -> None:
    data = {
        "title": "t",
        "summary": "摘要摘要摘要摘要。",
        "body_md": "x",
        "categories": ["a", "b"],
        "feed_kind": "news",
        "tabs": [{"label": "唯一", "summary": "概要足够长度用于校验", "body_md": "body_md 必须足够十六字以上。"}],
    }
    assert art.validate_llm_polish_for_publish(data) is False


def test_parse_article_tabs_json_roundtrip_matches_frontend_keys() -> None:
    payload = [
        {"label": "栏一", "summary": "概要文字超过八个字", "body_md": "## 标题\n\nMarkdown **粗体** 正文。"},
        {"label": "栏二", "summary": "第二栏概要同样够长", "body_md": "- 列表项一\n- 列表项二\n\n补充说明凑够十六字。"},
    ]
    s = json.dumps(payload, ensure_ascii=False)
    out = art.parse_article_tabs_json(s)
    assert len(out) == 2
    for row in out:
        assert set(row.keys()) == {"label", "summary", "body_md"}
        assert row["label"]
        assert len(row["summary"]) >= 8
        assert len(row["body_md"]) >= 16


def test_parse_article_tabs_json_malformed_returns_empty() -> None:
    assert art.parse_article_tabs_json("not-json") == []
    assert art.parse_article_tabs_json('{"x":1}') == []


def test_ui_shape_warnings_clean_article() -> None:
    tabs = [
        {"label": "A", "summary": "概要一二三四五六七八", "body_md": "正文正文正文正文正文正文正文正文。"},
        {"label": "B", "summary": "概要二二三四五六七八", "body_md": "正文二正文二正文二正文二正文二正文二正文。"},
    ]
    warns = art.ui_shape_warnings_for_stored_article(
        ai_categories_json=json.dumps(["大模型", "论文"], ensure_ascii=False),
        ai_tabs_json=json.dumps(tabs, ensure_ascii=False),
        body="## 总览",
        summary="正常摘要长度足够。",
    )
    assert warns == []


def test_ui_shape_warnings_bad_tabs_json() -> None:
    warns = art.ui_shape_warnings_for_stored_article(
        ai_categories_json="[]",
        ai_tabs_json='[{"label":"x"}]',
        body="fallback",
        summary="摘要",
    )
    assert any("ai_tabs_json" in w for w in warns)
    assert any("分类" in w for w in warns)
