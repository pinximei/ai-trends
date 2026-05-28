"""公开应用列表：可复刻档位筛选与 S→A 热度排序。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application import article_public as ap
from backend.app.application.article_public import (
    _article_matches_public_feed,
    _github_counts_as_apps_feed,
    _monetization_counts_as_apps_feed,
)
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


def test_feed_row_matches_replication_complete() -> None:
    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    repl = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        feed_kind="apps",
        third_party_source="product_hunt / daily",
        ai_categories_json='["应用产品"]',
        replication_tier="S",
        replication_analysis_json='{"verdict":"观望"}',
    )
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            replication_complete=True,
        )
        is False
    )
    import json

    a.replication_analysis_json = json.dumps(repl, ensure_ascii=False)
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            replication_complete=True,
        )
        is True
    )
    repl["worth_score"] = 5
    a.replication_analysis_json = json.dumps(repl, ensure_ascii=False)
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            replication_complete=True,
        )
        is False
    )


def test_github_trending_apps_fails_product_gate_without_value_assessment() -> None:
    from backend.app.application.article_public import _article_listing_product_gate

    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        feed_kind="apps",
        third_party_source="github / trending",
        ai_categories_json='["应用产品"]',
        replication_tier="A",
    )
    assert _article_listing_product_gate(a, None) is False


def test_feed_row_matches_replication_high_value() -> None:
    import json

    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    repl_ok = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
    repl_watch = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="观望"))
    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        feed_kind="apps",
        third_party_source="product_hunt / daily",
        ai_categories_json='["应用产品"]',
        replication_tier="S",
    )
    a.replication_analysis_json = json.dumps(repl_ok, ensure_ascii=False)
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            replication_high_value=True,
        )
        is True
    )
    a.replication_analysis_json = json.dumps(repl_watch, ensure_ascii=False)
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            replication_high_value=True,
        )
        is False
    )


def test_feed_row_matches_tier_filter() -> None:
    import json

    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    repl = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
    a = Article(
        industry_id=1,
        segment_id=1,
        title="t",
        status="published",
        feed_kind="apps",
        third_party_source="product_hunt / daily",
        ai_categories_json='["应用产品"]',
        replication_tier="B",
        replication_analysis_json=json.dumps(repl, ensure_ascii=False),
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


def test_monetization_category_counts_as_apps_feed() -> None:
    a = Article(
        industry_id=1,
        segment_id=1,
        title="SaaS sold",
        status="published",
        feed_kind="news",
        ai_categories_json='["变现案例"]',
        replication_tier="A",
    )
    assert _monetization_counts_as_apps_feed(a) is True
    assert _article_matches_public_feed(a, "apps") is True
    assert _article_matches_public_feed(a, "news") is False


def test_github_s_tier_alone_not_apps_feed_without_client_category() -> None:
    a = Article(
        industry_id=1,
        segment_id=1,
        title="Generic repo",
        status="published",
        feed_kind="news",
        third_party_source="github / trending",
        replication_tier="S",
        ai_categories_json='["应用产品"]',
    )
    assert _github_counts_as_apps_feed(a) is False
    assert _article_matches_public_feed(a, "apps") is False


def test_github_client_category_counts_as_apps_feed() -> None:
    a = Article(
        industry_id=1,
        segment_id=1,
        title="Client repo",
        status="published",
        feed_kind="news",
        third_party_source="github / trending",
        ai_categories_json='["开源客户端(好抄)"]',
    )
    assert _github_counts_as_apps_feed(a) is True
    assert _article_matches_public_feed(a, "apps") is True
    assert _article_matches_public_feed(a, "news") is False


def test_list_articles_feed_by_heat_top_filters_sa_and_orders_by_worth() -> None:
    db = _session()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    def _repl_json(worth: int) -> str:
        repl = normalize_replication_analysis(sample_replication_analysis(worth=worth, verdict="高价值"))
        return json.dumps(repl, ensure_ascii=False)

    def _repl_json_no_boost(worth: int) -> str:
        """避免定价关键词把低分抬到 ≥7。"""
        repl = normalize_replication_analysis(
            {
                **sample_replication_analysis(worth=worth, verdict="高价值"),
                "value_summary": "面向独立开发者的小众垂直工具，适合作为副业方向跟踪",
                "market_position": {
                    "target_user": "独立开发者验证小众工具付费意愿",
                    "vertical_niche": "笔记同步细分场景",
                    "market_saturation": "竞争适中",
                    "competitors": [{"name": "竞品A", "note": "功能接近"}],
                    "differentiation": "更轻量的本地优先工作流",
                    "monetization_hypothesis": "按年一次性授权，先卖终身版验证需求",
                },
            }
        )
        assert int(repl.get("worth_score") or 0) < 7
        return json.dumps(repl, ensure_ascii=False)

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
                replication_analysis_json=_repl_json(9),
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
                replication_analysis_json=_repl_json_no_boost(6),
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
        replication_complete=True,
        sort_by_value=True,
        heat_offset=0,
        heat_page_size=10,
        heat_max_ranked=50,
    )
    titles = [x["title"] for x in out["items"]]
    assert titles == ["Tier A hot"]
    assert out["total"] == 1

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
            replication_analysis_json=_repl_json(8),
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
        sort_by_value=True,
        heat_offset=0,
        heat_page_size=10,
        heat_max_ranked=50,
    )
    gh_titles = [x["title"] for x in out2["items"] if "GitHub" in x["title"]]
    assert gh_titles == ["GitHub client S"]


def test_list_highlight_replicable_apps_includes_github_news_lane() -> None:
    import json

    from backend.app.domain.replication_analysis import normalize_replication_analysis
    from tests.replication_fixtures import sample_replication_analysis

    repl = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
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
            ai_categories_json='["开源客户端(好抄)"]',
            replication_tier="S",
            replication_analysis_json=json.dumps(repl, ensure_ascii=False),
            heat_score=10.0,
            published_at=now,
        )
    )
    db.commit()
    items = list_highlight_replicable_apps(db, industry_slug="ai", limit=6, published_within_days=30)
    assert any(x["title"] == "GH highlight" for x in items)
