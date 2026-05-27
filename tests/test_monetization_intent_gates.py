"""变现价值优先：意图门禁回归（审核清单自动化）。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application import article_public as ap
from backend.app.application.newsletter_daily_digest import _prioritize_digest_apps
from backend.app.db import Base
from backend.app.domain.replication_analysis import normalize_replication_analysis
from backend.app.newsletter_digest_format import _why_follow
from backend.app.product_models import Article, Industry, Segment
from tests.replication_fixtures import sample_replication_analysis


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_apps_feed_rejects_tier_only_without_value_assessment() -> None:
    """Criterion 4/6: replication_tiers 不能绕过 worth≥7。"""
    a = Article(
        industry_id=1,
        segment_id=1,
        title="S tier no repl",
        status="published",
        feed_kind="apps",
        replication_tier="S",
        heat_score=100.0,
    )
    assert (
        ap._feed_row_matches_list_filters(
            a,
            feed="apps",
            cat_filter=None,
            source_filter=None,
            search_n=None,
            tier_filter=frozenset({"S"}),
            replication_complete=False,
        )
        is False
    )


def test_digest_why_follow_no_tier_only_fallback() -> None:
    a = Article(
        id=1,
        title="x",
        feed_kind="apps",
        replication_tier="S",
    )
    text = _why_follow(a, feed_kind="apps")
    assert "仅有档位" not in text
    assert "热度" not in text or "未达" in text


def test_digest_prioritize_puts_high_value_before_monetization_source() -> None:
    repl_hi = normalize_replication_analysis(sample_replication_analysis(worth=9, verdict="高价值"))
    repl_lo = normalize_replication_analysis(sample_replication_analysis(worth=7, verdict="观望"))
    rows = [
        Article(
            id=1,
            title="Acquire low",
            feed_kind="apps",
            third_party_source="acquire / x",
            ai_categories_json='["变现案例"]',
            heat_score=999.0,
            replication_analysis_json=json.dumps(repl_lo, ensure_ascii=False),
        ),
        Article(
            id=2,
            title="PH high value",
            feed_kind="apps",
            third_party_source="product_hunt / x",
            ai_categories_json='["应用产品"]',
            heat_score=1.0,
            replication_analysis_json=json.dumps(repl_hi, ensure_ascii=False),
        ),
    ]
    ordered = _prioritize_digest_apps(rows)
    assert [x.id for x in ordered] == [2, 1]
