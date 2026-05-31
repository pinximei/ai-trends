"""列表卡片中文摘要选取。"""
from __future__ import annotations

from backend.app.text_display import pick_feed_card_description


def test_pick_feed_card_prefers_chinese_tab_summary() -> None:
    desc = pick_feed_card_description(
        title="Foo",
        summary="publishedAt source_name description url " * 10,
        tabs=[
            {
                "label": "描述",
                "summary": (
                    "OpenAI 发布新工具，面向开发者提供多模态与代码能力，已在多个地区上线试用；"
                    "本文说明产品定位、适用场景与对行业的影响，便于读者快速把握要点。"
                ),
            }
        ],
        admin_source_key="newsapi",
        snippet='{"title":"Foo","description":"short"}',
        feed_kind="news",
        desc_label="描述",
    )
    assert "OpenAI" in desc or "发布" in desc
    assert "publishedAt" not in desc


def test_pick_feed_card_github_snippet_fallback() -> None:
    snippet = (
        '{"full_name":"org/repo","description":"A cool lib","stargazers_count":1200,'
        '"html_url":"https://github.com/org/repo"}'
    )
    desc = pick_feed_card_description(
        title="org/repo",
        summary="https://github.com/org/repo",
        tabs=[],
        admin_source_key="github",
        snippet=snippet,
        feed_kind="apps",
        desc_label="描述",
    )
    assert "仓库" in desc or "org/repo" in desc
    assert "http" not in desc[:20]
