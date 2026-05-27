"""持续升温趋势榜。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.trend_momentum_public import compute_article_momentum, get_trend_momentum_dashboard
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_compute_momentum_github_stars_boost() -> None:
    now = datetime.utcnow()
    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        heat_score=90.0,
        engagement_stars_today=200,
        published_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=1),
    )
    score, tags = compute_article_momentum(a, now=now)
    assert score > 90
    assert "今日飙星" in tags or "持续升温" in tags


def test_dashboard_splits_tracks() -> None:
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
                title="OSS repo",
                summary="x" * 40,
                status="published",
                third_party_source="github / trending",
                feed_kind="news",
                heat_score=120.0,
                engagement_stars_today=100,
                ai_categories_json='["开源客户端(好抄)"]',
                published_at=now - timedelta(days=8),
                updated_at=now - timedelta(hours=6),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="PH app",
                summary="y" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="apps",
                heat_score=110.0,
                ai_categories_json='["应用产品"]',
                published_at=now - timedelta(days=2),
                updated_at=now - timedelta(hours=2),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="HN thread",
                summary="z" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=95.0,
                ai_categories_json='["Agent"]',
                published_at=now - timedelta(days=5),
                updated_at=now - timedelta(hours=4),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Agent tool 2",
                summary="w" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=88.0,
                ai_categories_json='["Agent"]',
                published_at=now - timedelta(days=3),
                updated_at=now - timedelta(hours=8),
            ),
        ]
    )
    db.commit()
    out = get_trend_momentum_dashboard(db, industry_slug="ai", period_days=30, limit_per_track=5)
    assert len(out["oss"]) >= 1
    assert len(out["software"]) >= 1
    assert len(out["hotspots"]) >= 1
    assert any(t["label"] == "Agent" for t in out["topics"])
    topic_labels = {t["label"] for t in out["topics"]}
    assert "高可复刻" not in topic_labels
    assert "变现案例" not in topic_labels


def test_topics_exclude_replication_and_monetization_facets() -> None:
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
                title="Repl 1",
                summary="a" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="apps",
                heat_score=100.0,
                ai_categories_json='["高可复刻"]',
                published_at=now - timedelta(days=2),
                updated_at=now - timedelta(hours=2),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Repl 2",
                summary="b" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="apps",
                heat_score=98.0,
                ai_categories_json='["高可复刻"]',
                published_at=now - timedelta(days=3),
                updated_at=now - timedelta(hours=3),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Mon 1",
                summary="c" * 40,
                status="published",
                third_party_source="acquire / feed",
                feed_kind="apps",
                heat_score=96.0,
                ai_categories_json='["变现案例"]',
                published_at=now - timedelta(days=2),
                updated_at=now - timedelta(hours=4),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Mon 2",
                summary="d" * 40,
                status="published",
                third_party_source="acquire / feed",
                feed_kind="apps",
                heat_score=94.0,
                ai_categories_json='["变现案例"]',
                published_at=now - timedelta(days=4),
                updated_at=now - timedelta(hours=5),
            ),
        ]
    )
    db.commit()
    out = get_trend_momentum_dashboard(db, industry_slug="ai", period_days=30)
    topic_labels = {t["label"] for t in out["topics"]}
    assert "高可复刻" not in topic_labels
    assert "变现案例" not in topic_labels
    assert "已验证变现" not in topic_labels
