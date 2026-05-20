"""arXiv Atom 拉取与 snippet 形状（无 DB）。"""
from __future__ import annotations

import json

from backend.app.connector_heat_fetch import (
    arxiv_api_is_query_url,
    parse_arxiv_atom_entries,
    sync_arxiv_top_details,
)
from backend.app.domain import articles as art


def test_arxiv_api_is_query_url() -> None:
    assert arxiv_api_is_query_url(
        "http://export.arxiv.org/api/query?search_query=cat:cs.AI&max_results=10"
    )
    assert not arxiv_api_is_query_url("https://arxiv.org/abs/2401.12345")


def test_extract_external_id_from_arxiv_snippet() -> None:
    payload = {
        "arxiv_id": "2401.00001v1",
        "id": "2401.00001v1",
        "title": "Demo Paper",
        "summary": "Abstract text " * 20,
        "authors": ["A Author"],
        "abs_url": "https://arxiv.org/abs/2401.00001v1",
    }
    sid = art.extract_source_external_id_from_connector_snippet(json.dumps(payload, ensure_ascii=False))
    assert sid == "2401.00001v1"


def test_parse_arxiv_atom_entries_minimal() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Test Paper Title</title>
    <summary>Abstract line one.</summary>
    <published>2024-01-01T00:00:00Z</published>
    <updated>2024-01-02T00:00:00Z</updated>
    <author><name>Alice</name></author>
    <link href="https://arxiv.org/abs/2401.00001v1" rel="alternate"/>
    <link href="https://arxiv.org/pdf/2401.00001v1" type="application/pdf"/>
    <category term="cs.AI"/>
  </entry>
</feed>"""
    rows = parse_arxiv_atom_entries(xml, limit=5)
    assert len(rows) == 1
    assert rows[0]["arxiv_id"] == "2401.00001v1"
    assert "Test Paper" in rows[0]["title"]
    assert rows[0]["authors"] == ["Alice"]


def test_sync_arxiv_top_details_live() -> None:
    """依赖外网；CI 与离线环境可跳过。"""
    import os

    if os.environ.get("CI") == "true" and os.environ.get("RUN_LIVE_ARXIV") != "1":
        return
    code, body = sync_arxiv_top_details(
        "http://export.arxiv.org/api/query?"
        "search_query=cat:cs.AI&sortBy=lastUpdatedDate&sortOrder=descending&max_results=30",
        {"User-Agent": "pytest-arxiv/1.0"},
    )
    if code == 429:
        return
    assert 200 <= code < 300
    pack = json.loads(body)
    items = pack.get("connector_sync_items_v1") or []
    assert len(items) >= 1
    first = json.loads(items[0]["snippet"])
    assert first.get("arxiv_id")
    assert first.get("title")
