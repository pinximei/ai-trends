"""入库前「仅链接」正文检测。"""
from __future__ import annotations

from backend.app.domain import articles as art
from tests.test_article_public_shape import (
    _VALID_BODY,
    _VALID_DESC_SUMMARY,
    _VALID_SUMMARY,
    _valid_tabs_apps,
    _valid_tabs_news,
)


def test_polish_substantive_accepts_normal_article() -> None:
    data = {
        "title": "某 AI 产品发布",
        "summary": _VALID_SUMMARY,
        "body_md": _VALID_BODY,
        "tabs": _valid_tabs_news(),
    }
    assert art.polish_payload_has_substantive_content(data) is True


def test_polish_substantive_rejects_link_only() -> None:
    data = {
        "title": "Foo Bar",
        "summary": "https://example.com/a",
        "body_md": "**相关链接**\n\n- [GitHub](https://github.com/o/r)\n- [原文](https://ph.com/p)",
        "tabs": [
            {
                "label": "描述",
                "summary": "见链接",
                "body_md": "[Product Hunt](https://www.producthunt.com/posts/x)",
            },
            {
                "label": "数据支撑",
                "summary": "链接",
                "body_md": "- [仓库](https://github.com/o/r)",
            },
        ],
    }
    assert art.polish_payload_has_substantive_content(data) is False


def test_stored_article_rejects_link_only() -> None:
    assert art.stored_article_has_substantive_content(
        title="XY",
        summary="https://ph.com/x " * 12,
        body="\n".join(f"https://example.com/p/{i}" for i in range(20)),
    ) is False


def test_stored_article_accepts_body_text() -> None:
    assert art.stored_article_has_substantive_content(
        title="产品名",
        summary="这是一段足够长的中文摘要，说明产品做什么、面向谁、为何值得关注。",
        body="## 正文\n\n" + "实现细节与使用场景。" * 20,
    ) is True


def test_news_rejects_english_metadata_without_cjk() -> None:
    """资讯稿：英文字段名凑满 80 字仍须有足够汉字。"""
    filler_en = "publishedAt source_name description title url author " * 8
    data = {
        "title": "AI Policy Update",
        "summary": filler_en,
        "body_md": filler_en,
        "feed_kind": "news",
        "tabs": [
            {"label": "描述", "summary": filler_en, "body_md": filler_en},
            {"label": "数据支撑", "summary": filler_en, "body_md": filler_en},
        ],
    }
    assert art.polish_payload_has_substantive_content(data) is False


def test_connector_upstream_rejects_thin_newsapi() -> None:
    snippet = (
        '{"source":"newsapi","title":"Foo","url":"https://example.com/a",'
        '"description":"","publishedAt":"2026-05-30T00:00:00Z"}'
    )
    ok, msg = art.connector_upstream_has_ingest_material(snippet, "newsapi")
    assert ok is False
    assert "上游素材过薄" in msg


def test_connector_upstream_accepts_newsapi_with_english_description() -> None:
    snippet = (
        '{"source":"newsapi","title":"Foo","url":"https://example.com/a",'
        '"description":"' + "A major AI vendor announced new enterprise APIs and pricing tiers for developers. " * 3 + '"}'
    )
    ok, _ = art.connector_upstream_has_ingest_material(snippet, "newsapi")
    assert ok is True


def test_connector_upstream_github_requires_readme_or_text() -> None:
    thin = '{"full_name":"o/r","description":"short","html_url":"https://github.com/o/r"}'
    ok, msg = art.connector_upstream_has_ingest_material(thin, "github")
    assert ok is False
    assert "GitHub" in msg

    with_readme = (
        '{"full_name":"o/r","description":"x",'
        '"readme_md":"# Demo\\n\\n这是一个面向开发者的开源桌面客户端，支持多平台。"}'
    )
    ok2, _ = art.connector_upstream_has_ingest_material(with_readme, "github")
    assert ok2 is True


def test_connector_upstream_accepts_newsapi_with_chinese_description() -> None:
    snippet = (
        '{"source":"newsapi","title":"Foo","url":"https://example.com/a",'
        '"description":"' + "这是一段足够长的中文资讯摘要，说明事件背景与对 AI 行业的影响，供编辑扩写与发布。" * 3 + '"}'
    )
    ok, _ = art.connector_upstream_has_ingest_material(snippet, "newsapi")
    assert ok is True


def test_validate_llm_polish_rejects_link_only_when_tabs_meet_length() -> None:
    """字数门槛满足但去 URL 后无正文时仍拒绝。"""
    link_blob = "\n".join(f"https://example.com/p/{i}" for i in range(40))
    short_link_summary = "https://ph.com/x " * 12
    data = {
        "title": "XY",
        "summary": short_link_summary,
        "body_md": link_blob,
        "categories": ["应用产品"],
        "feed_kind": "news",
        "tabs": [
            {"label": "描述", "summary": short_link_summary, "body_md": link_blob},
            {"label": "数据支撑", "summary": short_link_summary, "body_md": link_blob},
        ],
    }
    assert art.polish_payload_has_substantive_content(data) is False
    assert art.validate_llm_polish_for_publish(data, admin_source_key="github") is False
