"""首页七路雷达：按源查询，不依赖精选剔除后的池。"""
from __future__ import annotations

from backend.app.application.home_public import (
    HOME_MAIN_SOURCE_KEYS,
    HOME_RADAR_APPS_KEYS,
    HOME_RADAR_NEWS_KEYS,
    _home_radar_lanes_for_feed,
)


def test_home_radar_key_sets_cover_seven_builtin() -> None:
    assert len(HOME_MAIN_SOURCE_KEYS) == 7
    assert len(HOME_RADAR_NEWS_KEYS) == 3
    assert len(HOME_RADAR_APPS_KEYS) == 4
    assert HOME_RADAR_NEWS_KEYS | HOME_RADAR_APPS_KEYS == frozenset(HOME_MAIN_SOURCE_KEYS)


def test_home_radar_lanes_order_matches_builtin(monkeypatch) -> None:
    """每路单独 list_articles_feed_by_heat_top(source=...)。"""
    from backend.app.application import home_public as hp

    calls: list[tuple[str, str | None]] = []

    def fake_heat(db, *, feed, source=None, **kwargs):
        calls.append((feed, source))
        return {"items": [{"id": 1, "admin_source_key": source, "platform_label": source, "title": f"t-{source}"}]}

    monkeypatch.setattr(
        "backend.app.application.article_public.list_articles_feed_by_heat_top",
        fake_heat,
    )
    monkeypatch.setattr(
        "backend.app.application.article_public._admin_source_label_by_key",
        lambda db: {},
    )

    lanes = hp._home_radar_lanes_for_feed(
        None,  # type: ignore[arg-type]
        feed="news",
        industry_slug="ai",
        published_within_days=30,
        exclude_ids=set(),
    )
    assert [x["source_key"] for x in lanes] == [k for k in HOME_MAIN_SOURCE_KEYS if k in HOME_RADAR_NEWS_KEYS]
    assert calls == [("news", "hacker_news"), ("news", "newsapi"), ("news", "thenewsapi")]
