"""Product Hunt 日榜拉取查询构建。"""
from __future__ import annotations

from backend.app.connector_heat_fetch import _ph_day_start_utc_iso, _ph_posts_list_query


def test_ph_posts_list_query_uses_votes_featured_and_posted_after() -> None:
    q = _ph_posts_list_query(
        n=10,
        posted_after="2026-05-18T07:00:00Z",
        posted_before="2026-05-19T07:00:00Z",
    )
    assert "order: VOTES" in q
    assert "featured: true" in q
    assert 'postedAfter: "2026-05-18T07:00:00Z"' in q
    assert 'postedBefore: "2026-05-19T07:00:00Z"' in q
    assert "order: RANKING" not in q


def test_ph_day_start_utc_iso_is_midnight_pt() -> None:
    iso = _ph_day_start_utc_iso(days_ago=0)
    assert iso.endswith("Z")
    assert "T" in iso
