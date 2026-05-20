"""Hacker News Algolia 拉取与 snippet 形状（无 DB）。"""
from __future__ import annotations

import json

from backend.app.connector_heat_fetch import (
    hacker_news_algolia_is_search_url,
    sync_hacker_news_top_details,
)
from backend.app.domain import articles as art


def test_hacker_news_algolia_is_search_url() -> None:
    assert hacker_news_algolia_is_search_url("https://hn.algolia.com/api/v1/search?tags=front_page")
    assert not hacker_news_algolia_is_search_url("https://hacker-news.firebaseio.com/v0/topstories.json")


def test_extract_external_id_from_hn_hit_snippet() -> None:
    payload = {
        "objectID": "42424242",
        "title": "Show HN: Demo",
        "url": "https://example.com",
        "points": 120,
    }
    sid = art.extract_source_external_id_from_connector_snippet(json.dumps(payload, ensure_ascii=False))
    assert sid == "42424242"


def test_sync_hacker_news_top_details_live() -> None:
    """依赖外网；CI 与离线环境可跳过。"""
    import os

    if os.environ.get("CI") == "true" and os.environ.get("RUN_LIVE_HN") != "1":
        return
    code, body = sync_hacker_news_top_details(
        "https://hn.algolia.com/api/v1/search?tags=front_page",
        {"User-Agent": "pytest-hn/1.0"},
    )
    assert 200 <= code < 300
    pack = json.loads(body)
    items = pack.get("connector_sync_items_v1") or []
    assert len(items) >= 1
    first = json.loads(items[0]["snippet"])
    assert first.get("objectID")
    assert first.get("title")
