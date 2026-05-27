"""首页趋势概览公开 API。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_home_dashboard_shape(client: TestClient) -> None:
    r = client.get("/api/public/v1/home/dashboard?news_limit=4&apps_limit=4&published_within_days=30")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    data = body["data"]
    assert "news" in data and "apps" in data
    assert "trend" in data and len(data["trend"]["sparkline"]) >= 2
    assert isinstance(data["news_source_lanes"], list)
    assert isinstance(data["source_facets"], list)
    assert isinstance(data["top_categories"], list)
    assert isinstance(data.get("editorial_news"), list)
    assert isinstance(data.get("editorial_apps"), list)


def test_format_logs_for_export_multiline() -> None:
    from backend.app.sync_diagnostic_log import format_logs_for_export

    items = [
        {
            "created_at": "2026-01-01T00:00:00Z",
            "level": "error",
            "step": "http_fail",
            "message": "HTTP 0",
            "connector_id": 3,
            "source_key": "arxiv",
        }
    ]
    text = format_logs_for_export(items, run_id="abc123")
    assert "abc123" in text
    assert "数据源=arxiv" in text or "[arxiv]" in text
    assert "HTTP 请求失败" in text or "http_fail" in text
    assert "原因: HTTP 0" in text


def test_select_home_picks_backfills_when_quality_filter_empty() -> None:
    from backend.app.application.home_public import _select_home_picks

    raw = [
        {"id": 1, "title": "Lo", "card_description": "short", "heat_score": 10.0},
        {"id": 2, "title": "Valid title here", "card_description": "x" * 40, "heat_score": 80.0},
    ]
    picked = _select_home_picks(raw, 2)
    assert len(picked) == 2
    assert picked[0]["id"] == 2


def test_home_trend_overview_shape(client: TestClient) -> None:
    r = client.get("/api/public/v1/home/trend-overview?sparkline_days=10&period_days=7")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    data = body["data"]
    assert len(data["sparkline"]) == 10
    assert all("day" in p and "count" in p for p in data["sparkline"])
    assert isinstance(data["apps_count"], int)
    assert isinstance(data["news_count"], int)
    assert data["apps_growth_pct"] is None or isinstance(data["apps_growth_pct"], (int, float))
    assert data["news_growth_pct"] is None or isinstance(data["news_growth_pct"], (int, float))
