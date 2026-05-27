"""每日摘要：应用栏变现价值优先排序。"""
from __future__ import annotations

import json

from backend.app.application.newsletter_daily_digest import _prioritize_digest_apps
from backend.app.domain.replication_analysis import normalize_replication_analysis
from backend.app.product_models import Article
from tests.replication_fixtures import sample_replication_analysis


def test_prioritize_digest_apps_value_before_heat() -> None:
    repl_high = normalize_replication_analysis(sample_replication_analysis(worth=9, verdict="高价值"))
    repl_mid = normalize_replication_analysis(sample_replication_analysis(worth=8, verdict="高价值"))
    repl_low = normalize_replication_analysis(sample_replication_analysis(worth=5, verdict="观望"))

    rows = [
        Article(
            id=1,
            title="Hot generic",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
            ai_categories_json='["应用产品"]',
            replication_tier="A",
            heat_score=999.0,
            replication_analysis_json=json.dumps(repl_low, ensure_ascii=False),
        ),
        Article(
            id=2,
            title="Acquire deal",
            feed_kind="news",
            third_party_source="acquire / search",
            ai_categories_json='["变现案例"]',
            replication_tier="B",
            heat_score=10.0,
            replication_analysis_json=json.dumps(repl_high, ensure_ascii=False),
        ),
        Article(
            id=3,
            title="Mid worth app",
            feed_kind="apps",
            third_party_source="taaft / new",
            ai_categories_json='["应用产品"]',
            replication_tier="S",
            heat_score=50.0,
            replication_analysis_json=json.dumps(repl_mid, ensure_ascii=False),
        ),
    ]
    ordered = _prioritize_digest_apps(rows)
    assert [a.id for a in ordered] == [2, 3, 1]
