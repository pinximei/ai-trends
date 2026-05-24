"""NewsAPI / TheNewsAPI 拉取 diag 统计。"""
from backend.app.connector_heat_fetch import (
    _news_fetch_diag_message,
    _newsapi_fetch_url,
    _newsapi_pack_from_body,
    _thenewsapi_fetch_url,
)
from backend.app.product_connectors_bootstrap import _news_wire_url_needs_repair


def test_newsapi_pack_from_body_no_ai_filter() -> None:
    body = {
        "articles": [
            {"title": "AI startup raises funds", "url": "https://a.com/1", "description": "machine learning"},
            {"title": "Sports game tonight", "url": "https://b.com/2", "description": "football"},
        ],
    }
    normed, note, stats = _newsapi_pack_from_body(body, n=10)
    assert note == "newsapi_ok"
    assert len(normed) == 2
    assert stats["articles_in_response"] == 2
    assert stats.get("skip_ai_filter", 0) == 0
    assert stats["packed"] == 2


def test_newsapi_fetch_url_rewrites_legacy_everything() -> None:
    legacy = "https://newsapi.org/v2/everything?q=artificial+intelligence&pageSize=20"
    u = _newsapi_fetch_url(legacy, n=10)
    assert "top-headlines" in u
    assert "q=" not in u


def test_thenewsapi_fetch_url_strips_search() -> None:
    legacy = (
        "https://api.thenewsapi.com/v1/news/top?locale=us&categories=tech"
        "&search=artificial+intelligence&limit=10"
    )
    u = _thenewsapi_fetch_url(legacy, n=10)
    assert "search=" not in u
    assert "limit=10" in u


def test_news_wire_url_needs_repair_detects_legacy() -> None:
    assert _news_wire_url_needs_repair(
        "newsapi", "https://newsapi.org/v2/everything?q=ai&pageSize=10"
    )
    assert _news_wire_url_needs_repair(
        "thenewsapi",
        "https://api.thenewsapi.com/v1/news/top?search=artificial+intelligence&limit=10",
    )
    assert not _news_wire_url_needs_repair(
        "newsapi", "https://newsapi.org/v2/top-headlines?country=us&pageSize=10"
    )


def test_news_fetch_diag_message_formats_stats() -> None:
    msg = _news_fetch_diag_message(
        "thenewsapi",
        "no_data",
        {"raw_rows": 3, "packed": 0},
    )
    assert "thenewsapi" in msg
    assert "packed=0" in msg
