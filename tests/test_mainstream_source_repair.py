"""主流数据源 URL / scope_label 修复（HN Algolia）。"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from backend.app.connector_heat_fetch import (
    GITHUB_TRENDING_DEFAULT,
    github_trending_is_discovery_url,
    hacker_news_algolia_is_search_url,
)
from backend.app.db import SessionLocal
from backend.app.models import AdminSourceConfig
from backend.app.product_connectors_bootstrap import (
    mainstream_heat_fetch_url_ok,
    repair_mainstream_heat_fetch_admin_sources,
)
from backend.app.scope_labels_util import get_scope_labels_from_source
from backend.app.services import ensure_mainstream_admin_sources


@pytest.fixture()
def db():
    url = os.getenv("AITRENDS_DATABASE_URL", "sqlite:///./_pytest_mainstream_repair.db")
    if url.startswith("sqlite:///./_pytest"):
        path = url.replace("sqlite:///", "")
        try:
            os.remove(path)
        except OSError:
            pass
    if url.startswith("sqlite"):
        from backend.app.db import Base, engine

        Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session


def _legacy_bad_url(source: str) -> str:
    if source == "hacker_news":
        return "https://hacker-news.firebaseio.com/v0/topstories.json"
    return ""


def test_mainstream_url_ok_matrix() -> None:
    assert mainstream_heat_fetch_url_ok("github", GITHUB_TRENDING_DEFAULT)
    assert mainstream_heat_fetch_url_ok("product_hunt", "https://api.producthunt.com/v2/api/graphql")
    assert mainstream_heat_fetch_url_ok("hacker_news", "https://hn.algolia.com/api/v1/search?tags=front_page")
    assert mainstream_heat_fetch_url_ok(
        "newsapi", "https://newsapi.org/v2/everything?q=ai&pageSize=10"
    )
    assert mainstream_heat_fetch_url_ok(
        "thenewsapi", "https://api.thenewsapi.com/v1/news/top?locale=us&limit=10"
    )
    assert not mainstream_heat_fetch_url_ok("hacker_news", "https://hacker-news.firebaseio.com/v0/topstories.json")
    assert not mainstream_heat_fetch_url_ok("github", "https://api.github.com/zen")
    assert mainstream_heat_fetch_url_ok("taaft", "https://theresanaiforthat.com/new/")
    assert mainstream_heat_fetch_url_ok(
        "acquire", "https://us-central1-microacquire.cloudfunctions.net/v1-search"
    )
    assert not mainstream_heat_fetch_url_ok("taaft", "https://theresanaiforthat.com/")


def test_repair_hn_url(db) -> None:
    """与生产一致：主流源行已存在时只更新 api_base / scope，不重复 INSERT。"""
    ensure_mainstream_admin_sources(db)

    row = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "hacker_news"))
    assert row is not None
    row.api_base = _legacy_bad_url("hacker_news")
    row.scope_label = ""
    row.scope_labels_json = "[]"
    db.commit()

    n = repair_mainstream_heat_fetch_admin_sources(db)
    assert n >= 1

    hn = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "hacker_news"))
    assert hn is not None
    assert hacker_news_algolia_is_search_url(hn.api_base)
    assert get_scope_labels_from_source(hn) == ["AI｜社区资讯"]
