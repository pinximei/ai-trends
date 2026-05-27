"""行业风向：AI/回退动态热点，非固定赛道。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.industry_wind_public import (
    _fallback_trends,
    _headline_from_cluster,
    _parse_llm_trends,
    get_industry_wind_overview,
)
from backend.app.db import Base
from backend.app.product_models import Article, Industry, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_parse_llm_trends_rejects_abstract_labels() -> None:
    raw = """{
      "trends": [
        {"headline": "政策市场", "summary": "x", "article_ids": [1]},
        {"headline": "Cursor 类 AI 编程工具升温", "summary": "多篇上榜", "article_ids": [1, 2]}
      ]
    }"""
    out = _parse_llm_trends(raw, {1, 2})
    assert out is not None
    assert len(out) == 1
    assert "Cursor" in out[0]["headline"]


def test_fallback_clusters_by_title_overlap() -> None:
    now = datetime.utcnow()
    arts = [
        (
            Article(
                id=1,
                industry_id=1,
                segment_id=1,
                title="Cursor adds new agent mode for coding",
                summary="x" * 40,
                status="published",
                third_party_source="hn",
                feed_kind="news",
                heat_score=90.0,
                ai_categories_json='["应用产品"]',
                published_at=now,
            ),
            80.0,
            now,
        ),
        (
            Article(
                id=2,
                industry_id=1,
                segment_id=1,
                title="Cursor 2.0 launches with faster completions",
                summary="y" * 40,
                status="published",
                third_party_source="hn",
                feed_kind="news",
                heat_score=85.0,
                ai_categories_json='["应用产品"]',
                published_at=now,
            ),
            75.0,
            now,
        ),
    ]
    trends = _fallback_trends(arts)
    assert trends
    assert len(trends[0]["article_ids"]) >= 2
    assert "cursor" in _headline_from_cluster([arts[0][0], arts[1][0]]).lower() or "Cursor" in trends[0]["headline"]


def test_industry_wind_dynamic_not_fixed_tracks() -> None:
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
                title="Windsurf IDE ships pair programming agent",
                summary="x" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=95.0,
                ai_categories_json='["应用产品"]',
                published_at=now - timedelta(days=3),
                updated_at=now - timedelta(hours=2),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Windsurf raises funding for AI coding assistant",
                summary="y" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=88.0,
                ai_categories_json='["应用产品"]',
                published_at=now - timedelta(days=5),
                updated_at=now - timedelta(hours=4),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Midjourney v7 video preview goes viral",
                summary="z" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="news",
                heat_score=92.0,
                ai_categories_json='["多模态"]',
                published_at=now - timedelta(days=2),
                updated_at=now - timedelta(hours=1),
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Midjourney adds character consistency for creators",
                summary="w" * 40,
                status="published",
                third_party_source="product_hunt / daily",
                feed_kind="news",
                heat_score=86.0,
                ai_categories_json='["多模态"]',
                published_at=now - timedelta(days=4),
                updated_at=now - timedelta(hours=3),
            ),
        ]
    )
    db.commit()
    out = get_industry_wind_overview(db, industry_slug="ai", recent_days=14)
    labels = {x.get("headline") or x.get("label") for x in out["industries"]}
    assert "政策市场" not in labels
    assert "安全合规" not in labels
    assert len(out["industries"]) >= 1
    first = out["industries"][0]
    assert first.get("summary")
    assert first.get("top_pick") is not None or first.get("article_count", 0) >= 1
