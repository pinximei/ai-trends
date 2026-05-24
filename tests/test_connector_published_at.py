"""连接器片段解析源站发布时间。"""
from __future__ import annotations

from backend.app.domain.articles import connector_snippet_published_at_utc


def test_connector_snippet_published_at_newsapi() -> None:
    snippet = '{"title":"x","publishedAt":"2026-05-18T08:00:00Z","url":"https://example.com"}'
    dt = connector_snippet_published_at_utc(snippet)
    assert dt is not None
    assert dt.year == 2026 and dt.month == 5 and dt.day == 18
