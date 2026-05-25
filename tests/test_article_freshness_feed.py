"""展示时效：重复同步后应按 updated_at 进入时间窗与排序，而非被源站旧 published_at 挤出。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.application import article_public as ap
from backend.app.domain.articles import article_freshness_datetime
from backend.app.product_models import Article, Base, Industry, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_freshness_prefers_updated_at() -> None:
    old = datetime(2024, 1, 1, 12, 0, 0)
    new = datetime(2026, 5, 20, 8, 0, 0)
    assert article_freshness_datetime(published_at=old, updated_at=new) == new
    assert article_freshness_datetime(published_at=new, updated_at=old) == new


def test_feed_by_heat_includes_resynced_old_published_at() -> None:
    db = _session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    old_pub = now - timedelta(days=90)
    db.add(
        Article(
            industry_id=ind.id,
            segment_id=seg.id,
            title="Resynced trending repo",
            summary="Still on GitHub trending but upstream published long ago.",
            status="published",
            feed_kind="news",
            third_party_source="github / trending",
            replication_tier="B",
            heat_score=120.0,
            published_at=old_pub,
            updated_at=now,
        )
    )
    db.commit()

    out = ap.list_articles_feed_by_heat_top(
        db,
        feed="news",
        industry_slug="ai",
        segment_id=None,
        segment_ids=None,
        published_within_days=30,
        published_on_latest_day=False,
        source="github",
        heat_offset=0,
        heat_page_size=10,
        heat_max_ranked=50,
    )
    assert len(out["items"]) == 1
    assert out["items"][0]["title"] == "Resynced trending repo"
    assert out["items"][0]["display_at"] is not None
    db.close()
