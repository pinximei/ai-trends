"""首页亮点变现线索列表。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.home_public import list_highlight_monetization_apps
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_list_highlight_monetization_apps_includes_json_tag_when_primary_is_apps() -> None:
    """JSON 含变现案例但展示主类为应用产品时，仍应进入变现线索池。"""
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
                title="Acquire deal one",
                status="published",
                feed_kind="apps",
                third_party_source="acquire / daily",
                ai_categories_json='["应用产品"]',
                heat_score=50.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Acquire deal two",
                status="published",
                feed_kind="apps",
                third_party_source="acquire / weekly",
                ai_categories_json='["应用产品"]',
                heat_score=40.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="PH with monetization tag",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品", "变现案例"]',
                heat_score=30.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Verified revenue",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["已验证变现"]',
                heat_score=20.0,
                published_at=now,
            ),
        ]
    )
    db.commit()
    items = list_highlight_monetization_apps(db, industry_slug="ai", limit=4, published_within_days=30)
    assert len(items) == 4
    titles = {x["title"] for x in items}
    assert "Acquire deal one" in titles
    assert "Acquire deal two" in titles
    assert "PH with monetization tag" in titles
    assert "Verified revenue" in titles


def test_list_highlight_monetization_apps_prefers_case_study_first() -> None:
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
                title="Hot PH with monetization tag",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / x",
                ai_categories_json='["应用产品", "变现案例"]',
                heat_score=999.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Case study",
                status="published",
                feed_kind="apps",
                third_party_source="acquire / y",
                ai_categories_json='["变现案例"]',
                heat_score=10.0,
                published_at=now,
            ),
        ]
    )
    db.commit()
    items = list_highlight_monetization_apps(db, industry_slug="ai", limit=2, published_within_days=30)
    assert len(items) == 2
    assert items[0]["title"] == "Case study"
    assert items[1]["title"] == "Hot PH with monetization tag"
