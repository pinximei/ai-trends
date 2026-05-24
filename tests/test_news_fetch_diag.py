"""NewsAPI / TheNewsAPI 拉取 diag 统计。"""
from backend.app.connector_heat_fetch import _news_fetch_diag_message, _newsapi_pack_from_body


def test_newsapi_pack_from_body_counts_ai_filter() -> None:
    body = {
        "articles": [
            {"title": "AI startup raises funds", "url": "https://a.com/1", "description": "machine learning"},
            {"title": "Sports game tonight", "url": "https://b.com/2", "description": "football"},
        ],
    }
    normed, note, stats = _newsapi_pack_from_body(body, n=10)
    assert note == "newsapi_ok"
    assert len(normed) == 1
    assert stats["articles_in_response"] == 2
    assert stats["skip_ai_filter"] == 1
    assert stats["packed"] == 1


def test_news_fetch_diag_message_formats_stats() -> None:
    msg = _news_fetch_diag_message(
        "thenewsapi",
        "no_ai_articles",
        {"raw_rows": 20, "skip_ai_filter": 18, "packed": 0},
    )
    assert "thenewsapi" in msg
    assert "skip_ai_filter=18" in msg
    assert "packed=0" in msg
