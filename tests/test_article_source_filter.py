"""公开列表按 admin_source_key 筛选。"""
from __future__ import annotations

from backend.app.application import article_public as ap
from backend.app.domain import articles as art


def test_normalize_source_filter() -> None:
    assert ap.normalize_source_filter("  GitHub  ") == "github"
    assert ap.normalize_source_filter("") is None
    assert ap.normalize_source_filter(None) is None


def test_admin_source_key_parses_connector_prefix() -> None:
    assert art.admin_source_key("github / trending") == "github"
    assert art.admin_source_key("product_hunt / daily") == "product_hunt"
