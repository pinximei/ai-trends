"""主流数据源 URL / scope_label 修复（HN Algolia、arXiv Atom）。"""
from __future__ import annotations

import os

import pytest

from backend.app.connector_heat_fetch import (
    arxiv_api_is_query_url,
    hacker_news_algolia_is_search_url,
)
from backend.app.db import SessionLocal
from backend.app.models import AdminSourceConfig
from backend.app.product_connectors_bootstrap import repair_mainstream_heat_fetch_admin_sources
from backend.app.scope_labels_util import get_scope_labels_from_source


@pytest.fixture()
def db():
    url = os.getenv("AITRENDS_DATABASE_URL", "sqlite:///./_pytest_mainstream_repair.db")
    if url.startswith("sqlite"):
        from backend.app.db import Base, engine

        Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session


def test_repair_hn_and_arxiv_urls(db) -> None:
    hn = AdminSourceConfig(
        source="hacker_news",
        enabled=True,
        api_base="https://hacker-news.firebaseio.com/v0/topstories.json",
        scope_label="",
        scope_labels_json="[]",
    )
    ax = AdminSourceConfig(
        source="arxiv",
        enabled=True,
        api_base="https://arxiv.org/abs/2401.00001",
        scope_label="",
        scope_labels_json="[]",
    )
    db.add_all([hn, ax])
    db.commit()

    n = repair_mainstream_heat_fetch_admin_sources(db)
    assert n >= 2

    db.refresh(hn)
    db.refresh(ax)
    assert hacker_news_algolia_is_search_url(hn.api_base)
    assert arxiv_api_is_query_url(ax.api_base)
    assert get_scope_labels_from_source(hn) == ["AI｜社区资讯"]
    assert get_scope_labels_from_source(ax) == ["AI｜论文预印本"]
