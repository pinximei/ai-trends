"""首页亮点变现线索列表（须价值分≥7）。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.home_public import list_highlight_monetization_apps
from backend.app.db import Base
from backend.app.domain.replication_analysis import normalize_replication_analysis
from backend.app.product_models import Article, Industry, Segment
from tests.replication_fixtures import sample_replication_analysis


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _repl_json(worth: int = 8) -> str:
    repl = normalize_replication_analysis(sample_replication_analysis(worth=worth, verdict="高价值"))
    return json.dumps(repl, ensure_ascii=False)


def test_list_highlight_monetization_apps_requires_value_assessment() -> None:
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
                title="Acquire with value",
                status="published",
                feed_kind="apps",
                third_party_source="acquire / daily",
                ai_categories_json='["应用产品"]',
                heat_score=50.0,
                published_at=now,
                replication_analysis_json=_repl_json(8),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Acquire no assessment",
                status="published",
                feed_kind="apps",
                third_party_source="acquire / weekly",
                ai_categories_json='["变现案例"]',
                heat_score=999.0,
                published_at=now,
            ),
        ]
    )
    db.commit()
    items = list_highlight_monetization_apps(db, industry_slug="ai", limit=4, published_within_days=30)
    titles = {x["title"] for x in items}
    assert "Acquire with value" in titles
    assert "Acquire no assessment" not in titles


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
                replication_analysis_json=_repl_json(7),
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
                replication_analysis_json=_repl_json(9),
            ),
        ]
    )
    db.commit()
    items = list_highlight_monetization_apps(db, industry_slug="ai", limit=2, published_within_days=30)
    assert len(items) == 2
    assert items[0]["title"] == "Case study"
    assert items[1]["title"] == "Hot PH with monetization tag"
