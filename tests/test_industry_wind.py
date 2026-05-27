"""行业风向：固定赛道 + 环比。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.industry_wind_public import TOPIC_INDUSTRY_TRACK_LABELS, get_industry_wind_overview
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_industry_wind_returns_all_tracks_and_excludes_ops_labels() -> None:
    db = _session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    db.add_all(
        [
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Agent a",
                summary="x" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=95.0,
                ai_categories_json='["Agent"]',
                published_at=now - timedelta(days=3),
                updated_at=now - timedelta(hours=2),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Agent b",
                summary="y" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=88.0,
                ai_categories_json='["Agent"]',
                published_at=now - timedelta(days=5),
                updated_at=now - timedelta(hours=4),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Repl only",
                summary="z" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="apps",
                heat_score=100.0,
                ai_categories_json='["高可复刻"]',
                published_at=now - timedelta(days=2),
                updated_at=now - timedelta(hours=1),
            ),
        ]
    )
    db.commit()
    out = get_industry_wind_overview(db, industry_slug="ai", recent_days=14)
    assert len(out["industries"]) == len(TOPIC_INDUSTRY_TRACK_LABELS)
    labels = {x["label"] for x in out["industries"]}
    assert "高可复刻" not in labels
    agent = next(x for x in out["industries"] if x["label"] == "Agent")
    assert agent["article_count"] == 2
    assert agent["rank"] == 1
    assert agent["top_pick"] is not None
