"""每日摘要：应用栏变现优先排序。"""
from __future__ import annotations

from backend.app.application.newsletter_daily_digest import _prioritize_digest_apps
from backend.app.product_models import Article


def test_prioritize_digest_apps_monetization_before_heat() -> None:
    rows = [
        Article(
            id=1,
            title="Hot generic",
            feed_kind="apps",
            third_party_source="product_hunt / daily",
            ai_categories_json='["应用产品"]',
            replication_tier="A",
            heat_score=999.0,
        ),
        Article(
            id=2,
            title="Acquire deal",
            feed_kind="news",
            third_party_source="acquire / search",
            ai_categories_json='["变现案例"]',
            replication_tier="B",
            heat_score=10.0,
        ),
        Article(
            id=3,
            title="S tier tool",
            feed_kind="apps",
            third_party_source="taaft / new",
            ai_categories_json='["应用产品"]',
            replication_tier="S",
            heat_score=50.0,
        ),
    ]
    ordered = _prioritize_digest_apps(rows)
    assert [a.id for a in ordered] == [2, 3, 1]
