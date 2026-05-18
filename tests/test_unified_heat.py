"""跨平台统一热度：对数归一 + 数据源权重（无 DB）。"""
from __future__ import annotations

import json

from backend.app.domain import articles as art


def test_extract_engagement_github_and_ph() -> None:
    gh = json.dumps({"stargazers_count": 12000, "forks_count": 900, "open_issues_count": 40})
    sig = art.extract_engagement_signals(gh)
    assert sig["stars"] == 12000.0
    assert sig["forks"] == 900.0
    assert sig["issues"] == 40.0

    ph = json.dumps({"votesCount": 800, "commentsCount": 120})
    sig2 = art.extract_engagement_signals(ph)
    assert sig2["votes"] == 800.0
    assert sig2["comments"] == 120.0


def test_extract_engagement_hn_hit() -> None:
    s = json.dumps({"hits": [{"points": 422, "num_comments": 88}]})
    sig = art.extract_engagement_signals(s)
    assert sig["hn_points"] >= 422.0
    assert sig["comments"] >= 88.0


def test_unified_github_more_stars_higher() -> None:
    hi = art.unified_connector_heat(
        admin_source_key="github",
        snippet=json.dumps({"stargazers_count": 50000, "forks_count": 2000}),
        value_score=80.0,
        sync_unix=1.0,
    )
    lo = art.unified_connector_heat(
        admin_source_key="github",
        snippet=json.dumps({"stargazers_count": 5, "forks_count": 1}),
        value_score=80.0,
        sync_unix=1.0,
    )
    assert hi > lo


def test_unified_product_hunt_positive() -> None:
    u = art.unified_connector_heat(
        admin_source_key="product_hunt",
        snippet=json.dumps({"votesCount": 2000, "commentsCount": 400}),
        value_score=70.0,
        sync_unix=10.0,
    )
    assert 80.0 < u < 950.0


def test_unified_huggingface_spaces_likes() -> None:
    u = art.unified_connector_heat(
        admin_source_key="huggingface_spaces",
        snippet=json.dumps({"likes": 12000, "trendingScore": 5000}),
        value_score=60.0,
        sync_unix=10.0,
    )
    assert u > 40.0


def test_unified_value_score_adds_on_top_of_signals() -> None:
    base = art.unified_connector_heat(
        admin_source_key="github",
        snippet=json.dumps({"stargazers_count": 100}),
        value_score=20.0,
        sync_unix=100.0,
    )
    hi_vs = art.unified_connector_heat(
        admin_source_key="github",
        snippet=json.dumps({"stargazers_count": 100}),
        value_score=90.0,
        sync_unix=100.0,
    )
    assert hi_vs > base


def test_unified_editorial_heat_mid_band() -> None:
    u = art.unified_editorial_heat(sync_unix=1_700_000_000.0)
    assert 90.0 < u < 130.0
