"""NewsAPI / TheNewsAPI Query 鉴权辅助。"""
from __future__ import annotations

from backend.app.source_query_auth import (
    apply_connector_auth_defaults,
    merge_api_key_into_url,
    query_auth_for_source,
)


def test_query_auth_for_newsapi():
    assert query_auth_for_source("newsapi") == ("query_key", "apiKey")
    assert query_auth_for_source("thenewsapi") == ("query_key", "api_token")
    assert query_auth_for_source("github") == ("bearer", "key")


def test_merge_api_key_into_url():
    u = "https://newsapi.org/v2/everything?q=ai&pageSize=20"
    out = merge_api_key_into_url(u, api_key="secret", key_param="apiKey")
    assert "apiKey=secret" in out
    assert "q=ai" in out


def test_apply_connector_auth_defaults():
    cfg = apply_connector_auth_defaults("newsapi", {"api_key": "x"})
    assert cfg["auth_mode"] == "query_key"
    assert cfg["key_param"] == "apiKey"
