"""公开应用列表：可复刻档位筛选与 S→A 热度排序。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application import article_public as ap
from backend.app.application.article_public import _article_matches_public_feed, _github_counts_as_apps_feed
from backend.app.application.home_public import list_highlight_replicable_apps
from backend.app.db import Base
from backend.app.domain import articles as art
from backend.app.product_models import Article, Industry, Segment


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_parse_replication_tiers_csv() -> None:
    assert art.parse_replication_tiers_csv("S,A") == ["S", "A"]
    assert art.parse_replication_tiers_csv("s, x, B") == ["S", "B"]
    assert art.parse_replication_tiers_csv("") is None
    assert art.parse_replication_tiers_csv("invalid") is None


def test_feed_row_matches_tier_filter() -> None:
    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        feed_kind="apps",
        third_party_source="product_hunt / daily",
        ai_categories_json='["应用产品"]',
        replication_tier="B",
    )
    assert ap._feed_row_matches_list_filters(a, feed="apps", cat_filter=None, source_filter=None, search_n=None) is True
    assert (
        ap._feed_row_matches_list_filters(
            a, feed="apps", cat_filter=None, source_filter=None, search_n=None, tier_filter=frozenset({"S", "A"})
        )
        is False
    )
    a.replication_tier = "S"
    assert (
        ap._feed_row_matches_list_filters(
            a, feed="apps", cat_filter=None, source_filter=None, search_n=None, tier_filter=frozenset({"S"})
        )
        is True
    )


def test_github_s_tier_counts_as_apps_feed() -> None:
    a = Article(
        industry_id=1,
        segment_id=1,
        title="Client repo",
        status="published",
        feed_kind="news",
        third_party_source="github / trending",
        replication_tier="S",
    )
    assert _github_counts_as_apps_feed(a) is True
    assert _article_matches_public_feed(a, "apps") is True
    assert _article_matches_public_feed(a, "news") is False


def test_list_articles_feed_by_heat_top_filters_sa_and_orders_s_first() -> None:
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
                title="Tier A hot",
                summary="alpha",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="A",
                heat_score=999.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Tier S cold",
                summary="sigma",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="S",
                heat_score=1.0,
                published_at=now,
            ),
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title="Tier B excluded",
                summary="beta",
                status="published",
                feed_kind="apps",
                third_party_source="product_hunt / daily",
                ai_categories_json='["应用产品"]',
                replication_tier="B",
                heat_score=5000.0,
                published_at=now,
            ),
        ]
    )
    db.commit()

    out = ap.list_articles_feed_by_heat_top(
        db,
        feed="apps",
        industry_slug="ai",
        segment_id=None,
        segment_ids=None,
        published_within_days=30,
        published_on_latest_day=False,
        replication_tiers="S,A",
        sort_replicable=True,
        heat_offset=0,
        heat_page_size=10,
        heat_max_ranked=50,
    )
    titles = [x["title"] for x in out["items"]]
    assert titles == ["Tier S cold", "Tier A hot"]
    assert out["total"] == 2

    db.add(
        Article(
            industry_id=ind.id,
            segment_id=seg.id,
            title="GitHub client S",
            summary="electron app",
            status="published",
            feed_kind="news",
            third_party_source="github / trending",
            ai_categories_json='["开源客户端(好抄)"]',
            replication_tier="S",
            heat_score=50.0,
            published_at=now,
        )
    )
    db.commit()
    out2 = ap.list_articles_feed_by_heat_top(
        db,
        feed="apps",
        industry_slug="ai",
        segment_id=None,
        segment_ids=None,
        published_within_days=30,
        published_on_latest_day=False,
        replication_tiers="S,A",
        sort_replicable=True,
        heat_offset=0,
        heat_page_size=10,
        heat_max_ranked=50,
    )
    gh_titles = [x["title"] for x in out2["items"] if "GitHub" in x["title"]]
    assert "GitHub client S" in gh_titles


def test_list_highlight_replicable_apps_includes_github_news_lane() -> None:
    db = _session()
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
            title="GH highlight",
            summary="tauri",
            status="published",
            feed_kind="news",
            third_party_source="github / trending",
            replication_tier="S",
            heat_score=10.0,
            published_at=now,
        )
    )
    db.commit()
    items = list_highlight_replicable_apps(db, industry_slug="ai", limit=6, published_within_days=30)
    assert any(x["title"] == "GH highlight" for x in items)
