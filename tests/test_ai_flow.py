"""AI 相关链路：无 Key 行为、管理端 LLM/调度/热门、公开文章 feed、简报。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.domain import articles as art
from backend.app.llm_service import chat_completion, generate_inspiration_body, polish_connector_article
from backend.app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _admin_login(c: TestClient) -> None:
    r = c.post("/api/admin/v1/auth/login", json={"username": "admin", "password": "admin123456"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0, body


def test_polish_connector_article_returns_none_without_api_key() -> None:
    db = MagicMock()
    with patch(
        "backend.app.llm_service.resolve_llm_http_config",
        return_value=("https://api.deepseek.com/v1", "", "deepseek-chat"),
    ):
        out = polish_connector_article(
            db,
            snippet="x" * 500,
            connector_name="t",
            admin_source_key="github",
            segment_label="板块",
            rule_title="标题",
            rule_summary="摘要" * 20,
            value_score=50.0,
            ref_id="ref1",
            feed_kind="news",
        )
    assert out is None


def test_chat_completion_raises_when_no_api_key() -> None:
    db = MagicMock()
    with patch("backend.app.llm_service.resolve_llm_http_config", return_value=("https://api.deepseek.com/v1", "", "m")):
        with pytest.raises(RuntimeError, match="LLM"):
            chat_completion(
                db,
                system="s",
                user="u",
                scenario="test",
                ref_type="t",
                ref_id="r",
            )


def test_rule_value_score_accepts_long_json_snippet() -> None:
    snippet = '{"origin": "1.2.3.4", "headers": {"User-Agent": "test"}, "args": {}, ' + '"data": "' + ("y" * 400) + '"}'
    score = art.rule_value_score(snippet=snippet, summary=("摘要" * 30)[:200], http_status=200)
    assert score >= art.VALUE_SCORE_MIN


def test_generate_inspiration_fallback_without_key() -> None:
    db = MagicMock()
    with patch("backend.app.llm_service.resolve_llm_http_config", return_value=("https://api.deepseek.com/v1", "", "m")):
        body = generate_inspiration_body(
            db,
            context_md="ctx",
            username="admin",
            inspiration_id=1,
            version_no=1,
        )
    assert "未配置 LLM" in body or "规则回退" in body


def test_admin_llm_settings_has_pipeline(client: TestClient) -> None:
    _admin_login(client)
    r = client.get("/api/admin/v1/product/settings/llm")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    data = body.get("data") or {}
    assert isinstance(data.get("pipeline"), list)
    assert len(data["pipeline"]) >= 1
    assert "provider" in data


def test_admin_scheduler_settings_get_and_put(client: TestClient) -> None:
    _admin_login(client)
    r = client.get("/api/admin/v1/product/settings/scheduler")
    assert r.status_code == 200
    d = r.json().get("data") or {}
    h = max(1, min(168, int(d.get("connector_sync_interval_hours") or 6)))
    r2 = client.put(
        "/api/admin/v1/product/settings/scheduler",
        json={"connector_scheduler_enabled": True, "connector_sync_interval_hours": h},
    )
    assert r2.status_code == 200
    assert r2.json().get("code") == 0


def test_admin_hot_settings_get(client: TestClient) -> None:
    _admin_login(client)
    r = client.get("/api/admin/v1/product/settings/hot")
    assert r.status_code == 200
    assert r.json().get("code") == 0
    data = r.json().get("data") or {}
    assert "top_n_trends" in data or "llm_model" in data


def test_public_articles_feed_news_and_apps_shape(client: TestClient) -> None:
    for feed in ("news", "apps"):
        r = client.get(
            "/api/public/v1/articles/feed",
            params={"feed": feed, "industry_slug": "ai", "page_size": "6"},
        )
        assert r.status_code == 200
        j = r.json()
        assert j.get("code") == 0
        data = j.get("data") or {}
        assert "items" in data and isinstance(data["items"], list)
        assert "next_cursor" in data
        for item in data["items"][:2]:
            assert "id" in item and "title" in item


def test_content_briefing_envelope(client: TestClient) -> None:
    r = client.get("/api/v1/content/briefing", params={"period": "week"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    data = body.get("data") or {}
    assert "title" in data or "sections" in data or "facts" in data
