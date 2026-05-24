"""首页各区块文章 id 互斥。"""
from __future__ import annotations

from backend.app.application.home_public import _article_ids, _exclude_article_ids, _group_source_lanes


def test_exclude_article_ids() -> None:
    items = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}, {"id": 3, "title": "c"}]
    out = _exclude_article_ids(items, {1, 3})
    assert [x["id"] for x in out] == [2]


def test_group_source_lanes_skips_exclude() -> None:
    items = [
        {"id": 10, "admin_source_key": "github", "platform_label": "GitHub", "title": "first"},
        {"id": 11, "admin_source_key": "github", "platform_label": "GitHub", "title": "second"},
    ]
    lanes = _group_source_lanes(items, exclude_ids={10})
    gh = next(x for x in lanes if x["source_key"] == "github")
    assert len(gh["items"]) == 1
    assert gh["items"][0]["id"] == 11


def test_article_ids() -> None:
    assert _article_ids([{"id": 5}, {"id": None}, {}]) == {5}
