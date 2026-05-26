"""公开 SEO：sitemap 生成与站点根 URL。"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from backend.app.application import seo_public as seo_app
from backend.app.public_site import resolve_public_site_base_url


def test_resolve_public_site_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITRENDS_PUBLIC_BASE_URL", "https://seo.test")
    assert resolve_public_site_base_url() == "https://seo.test"


def test_build_sitemap_xml_includes_static_and_articles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITRENDS_PUBLIC_BASE_URL", "https://seo.test")
    db = MagicMock()
    db.execute.return_value.all.return_value = [(42, datetime(2026, 5, 1, 12, 0, 0))]

    xml = seo_app.build_sitemap_xml(db)

    assert xml.startswith('<?xml version="1.0"')
    assert "<urlset" in xml
    assert "<loc>https://seo.test/</loc>" in xml
    assert "<loc>https://seo.test/news</loc>" in xml
    assert "<loc>https://seo.test/apps</loc>" in xml
    assert "<loc>https://seo.test/resources/42</loc>" in xml
    assert "<lastmod>2026-05-01</lastmod>" in xml
