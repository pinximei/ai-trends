"""首页趋势概览公开 API。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


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
