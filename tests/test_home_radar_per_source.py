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
    """每路单独 list_articles_home_radar_source_top(source_key=...)。"""
    from backend.app.application import home_public as hp

    calls: list[str] = []

    def fake_radar(db, *, source_key, **kwargs):
        calls.append(source_key)
        return [{"id": 1, "admin_source_key": source_key, "platform_label": source_key, "title": f"t-{source_key}"}]

    monkeypatch.setattr(
        "backend.app.application.article_public.list_articles_home_radar_source_top",
        fake_radar,
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
    assert calls == ["hacker_news", "newsapi", "thenewsapi"]


def test_home_radar_github_includes_news_lane_without_sa_tier() -> None:
    """GitHub 默认 news 泳道、非 S/A 档时，apps 雷达仍应能取到稿。"""
    from datetime import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.application import article_public as ap
    from backend.app.application.home_public import _home_radar_lanes_for_feed
    from backend.app.product_models import Article, Base, Industry, Segment

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    db.add(
        Article(
            industry_id=ind.id,
            segment_id=seg.id,
            title="Trending client app",
            summary="A desktop open-source client with many stars on GitHub trending.",
            status="published",
            feed_kind="news",
            third_party_source="github / trending",
            replication_tier="B",
            heat_score=88.0,
            published_at=now,
        )
    )
    db.commit()

    assert (
        ap.list_articles_feed_by_heat_top(
            db,
            feed="apps",
            industry_slug="ai",
            segment_id=None,
            segment_ids=None,
            published_within_days=30,
            published_on_latest_day=False,
            source="github",
            heat_offset=0,
            heat_page_size=5,
            heat_max_ranked=20,
        )["items"]
        == []
    )
    radar_items = ap.list_articles_home_radar_source_top(
        db,
        industry_slug="ai",
        source_key="github",
        published_within_days=30,
        limit=5,
    )
    assert len(radar_items) == 1
    assert radar_items[0]["title"] == "Trending client app"

    lanes = _home_radar_lanes_for_feed(
        db,
        feed="apps",
        industry_slug="ai",
        published_within_days=30,
        exclude_ids=set(),
    )
    gh = next(x for x in lanes if x["source_key"] == "github")
    assert len(gh["items"]) == 1
    db.close()
