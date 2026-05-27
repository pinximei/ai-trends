"""首页亮点高可复刻应用列表。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401 — admin ORM tables for metadata
from backend.app.application.home_public import list_highlight_replicable_apps
from backend.app.db import Base
from backend.app.domain.replication_analysis import normalize_replication_analysis
from backend.app.product_models import Article, Industry, Segment


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _deep_replication_json(*, worth: int = 8) -> str:
    repl = normalize_replication_analysis(
        {
            "verdict": "值得复刻",
            "worth_score": worth,
            "difficulty": "中",
            "tier_rationale": "x" * 24,
            "value_summary": "y" * 20,
            "tech_stack": ["Next.js"],
            "implementation_plan": ["step"],
            "estimated_hours": {"mvp_min": 40, "mvp_max": 80, "prod_min": 120, "prod_max": 200},
            "open_source": {"has_support": False, "projects": [], "gaps": ""},
            "risks": [],
        }
    )
    return json.dumps(repl, ensure_ascii=False)


def test_list_highlight_replicable_apps_orders_s_before_a() -> None:
    db = _session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    repl = _deep_replication_json()
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
                replication_analysis_json=repl,
                heat_score=900.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="High tier",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / launch",
                ai_categories_json='["应用产品"]',
                replication_tier="S",
                replication_analysis_json=repl,
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
                replication_analysis_json=repl,
                heat_score=999.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Tier only no analysis",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / extra",
                ai_categories_json='["应用产品"]',
                replication_tier="S",
                heat_score=800.0,
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
                replication_analysis_json=repl,
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
    assert items[1]["replication_tier"] == "A"


def test_list_highlight_replicable_apps_excludes_incomplete_and_low_worth() -> None:
    db = _session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    repl_ok = _deep_replication_json(worth=8)
    repl_low = _deep_replication_json(worth=5)
    db.add_all(
        [
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Good S",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                replication_tier="S",
                replication_analysis_json=repl_ok,
                heat_score=10.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Low worth",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / launch",
                replication_tier="S",
                replication_analysis_json=repl_low,
                heat_score=90.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="B tier complete",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / extra",
                ai_categories_json='["应用产品"]',
                replication_tier="B",
                replication_analysis_json=repl_ok,
                heat_score=80.0,
                published_at=now,
            ),
        ]
    )
    db.commit()
    items = list_highlight_replicable_apps(db, industry_slug="ai", limit=4, published_within_days=30)
    assert len(items) == 1
    assert items[0]["title"] == "Good S"
