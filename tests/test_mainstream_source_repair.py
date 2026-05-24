"""主流数据源 URL / scope_label 修复（HN Algolia、arXiv Atom）。"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from backend.app.connector_heat_fetch import (
    arxiv_api_is_query_url,
    hacker_news_algolia_is_search_url,
)
from backend.app.db import SessionLocal
from backend.app.models import AdminSourceConfig
from backend.app.product_connectors_bootstrap import repair_mainstream_heat_fetch_admin_sources
from backend.app.scope_labels_util import get_scope_labels_from_source
from backend.app.services import ensure_mainstream_admin_sources


@pytest.fixture()
def db():
    url = os.getenv("AITRENDS_DATABASE_URL", "sqlite:///./_pytest_mainstream_repair.db")
    if url.startswith("sqlite"):
        from backend.app.db import Base, engine

        Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session


def _legacy_bad_url(source: str) -> str:
    if source == "hacker_news":
        return "https://hacker-news.firebaseio.com/v0/topstories.json"
    if source == "arxiv":
        return "https://arxiv.org/abs/2401.00001"
    return ""


def test_repair_hn_and_arxiv_urls(db) -> None:
    """与生产一致：主流源行已存在时只更新 api_base / scope，不重复 INSERT。"""
    ensure_mainstream_admin_sources(db)

    for source in ("hacker_news", "arxiv"):
        row = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == source))
        assert row is not None, f"missing seeded source {source}"
        row.api_base = _legacy_bad_url(source)
        row.scope_label = ""
        row.scope_labels_json = "[]"
    db.commit()

    n = repair_mainstream_heat_fetch_admin_sources(db)
    assert n >= 2

    hn = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "hacker_news"))
    ax = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "arxiv"))
    assert hn is not None and ax is not None
    assert hacker_news_algolia_is_search_url(hn.api_base)
    assert arxiv_api_is_query_url(ax.api_base)
    assert get_scope_labels_from_source(hn) == ["AI｜社区资讯"]
    assert get_scope_labels_from_source(ax) == ["AI｜论文预印本"]
