"""首页亮点高可复刻应用列表。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401 — admin ORM tables for metadata
from backend.app.application.home_public import list_highlight_replicable_apps
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_list_highlight_replicable_apps_orders_s_before_a() -> None:
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
                title="Low tier hot",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="A",
                heat_score=900.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="High tier",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="S",
                heat_score=100.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="News only",
                status="published",
                feed_kind="news",
                replication_tier="S",
                heat_score=999.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Old app",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="S",
                heat_score=500.0,
                published_at=now - timedelta(days=60),
                updated_at=now - timedelta(days=60),
            ),
        ]
    )
    db.commit()
    old = db.query(Article).filter(Article.title == "Old app").one()
    old.updated_at = now - timedelta(days=60)
    db.commit()
    items = list_highlight_replicable_apps(db, industry_slug="ai", limit=4, published_within_days=30)
    assert len(items) == 2
    assert items[0]["title"] == "High tier"
    assert items[0]["replication_tier"] == "S"
    assert items[1]["title"] == "Low tier hot"


def test_list_highlight_replicable_apps_backfills_with_b_tier() -> None:
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
                title="Only S",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                replication_tier="S",
                heat_score=10.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="B one",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / launch",
                ai_categories_json='["应用产品"]',
                replication_tier="B",
                heat_score=90.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="B two",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="B",
                heat_score=80.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="B three",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / extra",
                ai_categories_json='["应用产品"]',
                replication_tier="B",
                heat_score=70.0,
                published_at=now,
            ),
        ]
    )
    db.commit()
    items = list_highlight_replicable_apps(db, industry_slug="ai", limit=4, published_within_days=30)
    assert len(items) == 4
    assert items[0]["title"] == "Only S"
    titles = {x["title"] for x in items}
    assert "B one" in titles and "B two" in titles and "B three" in titles
