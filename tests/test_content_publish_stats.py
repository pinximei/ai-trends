"""内容发布运营统计。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.content_publish_stats import publishing_ops_overview
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="apps", name="Apps")
    db.add(seg)
    db.flush()
    return db, ind.id, seg.id


def test_publishing_ops_overview_counts_by_day_and_category() -> None:
    db, industry_id, segment_id = _session()
    now = datetime.utcnow()
    db.add(
        Article(
            title="A",
            summary="s",
            body="b",
            industry_id=industry_id,
            segment_id=segment_id,
            status="published",
            published_at=now,
            feed_kind="apps",
            ai_categories_json='["应用产品"]',
            third_party_source="product_hunt / daily",
        )
    )
    db.commit()
    out = publishing_ops_overview(db, days=7)
    assert out["summary"]["published_in_period"] == 1
    assert out["summary"]["today_articles_on_site"] >= 1
    assert any(c["category"] == "应用产品" for c in out["categories"])
    assert len(out["daily"]) == 7
    assert out["daily"][-1]["sites"]["ai-trends-apps"]["articles"] >= 1
