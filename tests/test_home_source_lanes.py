"""首页六路雷达：无文章时仍返回六路占位（池内分桶，兼容测试）。"""
from __future__ import annotations

from backend.app.application.home_public import _group_source_lanes, HOME_MAIN_SOURCE_KEYS


def test_group_source_lanes_always_six_slots() -> None:
    lanes = _group_source_lanes([])
    assert len(lanes) == len(HOME_MAIN_SOURCE_KEYS)
    assert [x["source_key"] for x in lanes] == list(HOME_MAIN_SOURCE_KEYS)
    assert all(x["items"] == [] for x in lanes)


def test_group_source_lanes_with_one_source() -> None:
    lanes = _group_source_lanes(
        [
            {
                "id": 1,
                "admin_source_key": "github",
                "platform_label": "GitHub",
                "title": "Test repo",
            }
        ]
    )
    assert len(lanes) == len(HOME_MAIN_SOURCE_KEYS)
    gh = next(x for x in lanes if x["source_key"] == "github")
    assert len(gh["items"]) == 1
    hn = next(x for x in lanes if x["source_key"] == "hacker_news")
    assert hn["items"] == []
