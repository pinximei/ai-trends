"""News 快讯二次拉取（HTML / HN Firebase）。"""
from __future__ import annotations

import json

from backend.app.domain import articles as art
from backend.app.news_wire_enrich import (
    enrich_news_wire_items,
    enrich_news_wire_row,
    extract_text_from_html,
    fetch_article_body_from_url,
    fetch_hn_item_text,
)


def test_extract_text_from_html_article_tag() -> None:
    html = """
    <html><body><article>
    <p>这是一段关于人工智能行业的重要新闻正文，包含足够的中文描述与背景。</p>
    <p>第二段继续说明政策影响与产品动态，供读者快速把握要点。</p>
    </article></body></html>
    """
    text = extract_text_from_html(html)
    assert "人工智能" in text
    assert len(text) >= 40


def test_enrich_newsapi_row_from_mock_html() -> None:
    page = """
    <html><body><main>
    <p>""" + ("某科技公司发布新一代大模型，面向企业客户提供 API 与私有化部署选项。" * 3) + """</p>
    </main></body></html>
    """
    row = {
        "source": "newsapi",
        "title": "AI Corp launches model",
        "url": "https://example.com/news/ai-launch",
        "description": "",
    }

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = page

    class FakeClient:
        def get(self, url, **kwargs):
            assert "example.com" in url
            return FakeResp()

    action = enrich_news_wire_row(row, "newsapi", FakeClient())
    assert action == "url_fetch"
    assert row.get("article_body")
    assert art.connector_upstream_has_ingest_material(json.dumps(row), "newsapi")[0] is True


def test_enrich_skips_when_description_already_thick() -> None:
    row = {
        "source": "newsapi",
        "title": "T",
        "url": "https://example.com/x",
        "description": "这是一段足够长的中文资讯摘要，说明事件背景与对 AI 行业的影响，供编辑扩写与发布。" * 3,
    }

    class NoCallClient:
        def get(self, *a, **k):
            raise AssertionError("should not fetch")

    action = enrich_news_wire_row(row, "newsapi", NoCallClient())
    assert action == "skip_ok"


def test_enrich_hn_firebase_mock() -> None:
    row = {
        "source": "hacker_news",
        "objectID": "99",
        "title": "Ask HN",
        "url": "https://news.ycombinator.com/item?id=99",
        "story_text": "",
    }
    payload = {
        "title": "Ask HN: Best practices",
        "text": "我们在讨论 AI 工具链的选型。" + "需要兼顾成本、合规与交付周期。" * 5,
    }

    class FakeResp:
        status_code = 200

        def json(self):
            return payload

    class FakeClient:
        def get(self, url, **kwargs):
            assert "firebaseio.com" in url
            return FakeResp()

    action = enrich_news_wire_row(row, "hacker_news", FakeClient())
    assert action == "hn_firebase"
    assert "工具链" in (row.get("article_body") or "")


def test_enrich_news_wire_items_stats() -> None:
    items = [
        {
            "source": "thenewsapi",
            "title": "A",
            "url": "https://example.com/a",
            "description": "短",
        },
        {
            "source": "thenewsapi",
            "title": "B",
            "url": "https://example.com/b",
            "description": "这是一段足够长的中文资讯摘要，说明事件背景与对 AI 行业的影响，供编辑扩写与发布。" * 3,
        },
    ]

    class FakeResp:
        status_code = 200
        headers = {"content-type": "text/html"}
        text = "<article><p>" + ("正文内容关于机器学习平台升级与商业化路径。" * 4) + "</p></article>"

    class FakeClient:
        def get(self, url, **kwargs):
            return FakeResp()

        def close(self):
            pass

    out, stats = enrich_news_wire_items(items, "thenewsapi", client=FakeClient(), fetch_delay=0)
    assert len(out) == 2
    assert stats["enrich_candidates"] >= 1
    assert stats["enrich_skip_ok"] >= 1
