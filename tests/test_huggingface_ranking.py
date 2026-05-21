"""HF Spaces 排序：trendingScore 优先于历史 likes（无 DB）。"""
from __future__ import annotations


def _hf_rank_key(it: dict) -> tuple[int, int]:
    """与 connector_heat_fetch.sync_huggingface_spaces_top_details 一致。"""
    try:
        ts = int(it.get("trendingScore") or 0)
    except (TypeError, ValueError):
        ts = 0
    try:
        likes = int(it.get("likes") or 0)
    except (TypeError, ValueError):
        likes = 0
    return (ts, likes)


def test_hf_rank_prefers_trending_score_over_total_likes() -> None:
    items = [
        {"id": "legacy/huge-likes", "likes": 11_000, "trendingScore": 8},
        {"id": "hot/this-week", "likes": 210, "trendingScore": 125},
        {"id": "mid/both", "likes": 1_300, "trendingScore": 98},
    ]
    ranked = sorted(items, key=_hf_rank_key, reverse=True)
    assert [x["id"] for x in ranked] == ["hot/this-week", "mid/both", "legacy/huge-likes"]
