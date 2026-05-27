"""AI 相关链路：无 Key 行为、管理端 LLM/调度/热门、公开文章 feed、简报。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.domain import articles as art
from backend.app.llm_service import chat_completion, polish_connector_article
from backend.app.polish_publish_compat import coerce_polish_output
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


def test_coerce_polish_output_maps_category_and_tab_labels() -> None:
    out = {
        "title": "OpenAI 发布新功能",
        "summary": "x" * 40,
        "body_md": "y" * 130,
        "categories": ["科技新闻"],
        "feed_kind": "news",
        "tabs": [
            {"label": "描述", "summary": "a" * 80, "body_md": "b" * 130},
            {"label": "数据支撑", "summary": "c" * 20, "body_md": "d" * 80},
        ],
    }
    fixed = coerce_polish_output(out)
    assert fixed["categories"][0] in art.FACET_ALL_LABELS
    assert [t["label"] for t in fixed["tabs"]] == ["描述", "数据支撑"]


def test_polish_connector_article_returns_none_without_api_key() -> None:
    db = MagicMock()
    with patch(
        "backend.app.llm_service.resolve_llm_http_config",
        return_value=("https://api.deepseek.com/v1", "", "deepseek-chat"),
    ):
        out, err = polish_connector_article(
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
    assert err == "no_llm_key"


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


def test_admin_theme_fetch_requires_admin(client: TestClient) -> None:
    r = client.post("/api/admin/v1/product/ingest/theme-fetch", json={})
    assert r.status_code in (401, 403)


def test_admin_theme_fetch_ok_for_admin(client: TestClient) -> None:
    _admin_login(client)
    r = client.post("/api/admin/v1/product/ingest/theme-fetch", json={})
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0
    data = body.get("data") or {}
    assert data.get("taxonomy_synced") is True
    assert "connectors_total" in data
    assert "ok" in data and "fail" in data
    assert isinstance(data.get("details"), list)


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
        assert "has_more" in data
        for item in data["items"][:2]:
            assert "id" in item and "title" in item


def test_public_articles_feed_day_pagination_shape(client: TestClient) -> None:
    r = client.get(
        "/api/public/v1/articles/feed",
        params={"feed": "news", "industry_slug": "ai", "paginate_by": "day", "page": "1"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("code") == 0
    data = j.get("data") or {}
    assert data.get("paginate_by") == "day"
    assert "items" in data and isinstance(data["items"], list)
    assert "page" in data and "total_pages" in data
    assert "has_prev" in data and "has_next" in data
    assert "days_scan_truncated" in data


def test_public_articles_feed_search_q_filters_news(client: TestClient) -> None:
    r = client.get(
        "/api/public/v1/articles/feed",
        params={"feed": "news", "industry_slug": "ai", "page_size": "12", "q": "大模型"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("code") == 0
    items = (j.get("data") or {}).get("items") or []
    if not items:
        pytest.skip("No published news articles matched q=大模型 in this database; seed or widen fixtures.")
    assert len(items) >= 1
    blob = " ".join(str(x.get("title", "")) + " " + str(x.get("summary", "")) for x in items).lower()
    assert "大模型" in blob


def test_public_articles_feed_search_q_filters_apps(client: TestClient) -> None:
    base = client.get(
        "/api/public/v1/articles/feed",
        params={"feed": "apps", "industry_slug": "ai", "page_size": "24"},
    )
    assert base.status_code == 200
    base_items = (base.json().get("data") or {}).get("items") or []
    if not base_items:
        pytest.skip("No published apps articles in this database; cannot assert search on apps lane.")
    first = base_items[0]
    needle = (str(first.get("title") or "app").strip() or "app")[:40]

    r = client.get(
        "/api/public/v1/articles/feed",
        params={"feed": "apps", "industry_slug": "ai", "page_size": "12", "q": needle},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("code") == 0
    items = (j.get("data") or {}).get("items") or []
    assert len(items) >= 1
    nlow = needle.lower()
    assert any(nlow in f"{x.get('title', '')} {x.get('summary', '')}".lower() for x in items)


def test_public_articles_categories_accepts_search_q(client: TestClient) -> None:
    r = client.get(
        "/api/public/v1/articles/categories",
        params={"feed": "news", "industry_slug": "ai", "published_within_days": "3650", "q": "大模型"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("code") == 0
    rows = j.get("data") or []
    assert isinstance(rows, list)


def test_public_articles_sources_shape(client: TestClient) -> None:
    r = client.get(
        "/api/public/v1/articles/sources",
        params={"feed": "news", "industry_slug": "ai", "published_within_days": "3650"},
    )
    assert r.status_code == 200
    j = r.json()
    assert j.get("code") == 0
    rows = j.get("data") or []
    assert isinstance(rows, list)
    for row in rows[:3]:
        assert "key" in row and "label" in row and "count" in row


def test_public_articles_feed_source_param(client: TestClient) -> None:
    src_r = client.get(
        "/api/public/v1/articles/sources",
        params={"feed": "news", "industry_slug": "ai", "published_within_days": "3650"},
    )
    assert src_r.status_code == 200
    sources = (src_r.json().get("data") or [])
    if not sources:
        pytest.skip("No news sources in database for source filter test.")
    key = sources[0]["key"]
    r = client.get(
        "/api/public/v1/articles/feed",
        params={
            "feed": "news",
            "industry_slug": "ai",
            "paginate_by": "day",
            "page": "1",
            "published_within_days": "3650",
            "source": key,
        },
    )
    assert r.status_code == 200
    items = (r.json().get("data") or {}).get("items") or []
    for item in items[:5]:
        assert (item.get("admin_source_key") or "") == key


def test_clear_product_ingest_clears_domains_taxonomy(client: TestClient) -> None:
    from sqlalchemy import select

    from backend.app.db import SessionLocal
    from backend.app.product_models import Industry
    from backend.app.taxonomy_from_sources import MERGED_TAXONOMY_INDUSTRY_SLUG

    _admin_login(client)
    client.post("/api/admin/v1/product/ingest/theme-fetch", json={})
    with SessionLocal() as db:
        dom = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
        if dom is None:
            pytest.skip("domains industry not created; depends on admin sources / DB")

    r = client.post("/api/admin/v1/product/ingest-data/clear")
    assert r.status_code == 200
    body = r.json()
    assert body.get("code") == 0, body
    data = body.get("data") or {}
    assert data.get("product_domains_industry_removed") == 1

    with SessionLocal() as db:
        dom_after = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
        assert dom_after is None

