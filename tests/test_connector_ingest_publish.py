"""连接器入库：发布时间窗口与规则兜底润色。"""
from datetime import datetime

from backend.app.domain.articles import published_at_for_connector_ingest
from backend.app.llm_service import _parse_polish_response
from backend.app.polish_publish_compat import build_rule_fallback_polish_from_snippet
from backend.app.us_content_calendar import utc_naive_bounds_for_us_date, us_calendar_today


def test_parse_polish_allows_empty_tabs_for_repair():
    raw = (
        '{"title":"AI headline","summary":"' + ("x" * 40) + '",'
        '"feed_kind":"news","categories":["其他"],"tabs":[]}'
    )
    out, err = _parse_polish_response(raw, default_feed_kind="news")
    assert err == ""
    assert out is not None
    assert out["title"] == "AI headline"


def test_rule_fallback_thenewsapi_style():
    snippet = (
        '{"title":"Anthropic Eyes IPO","description":"' + ("d" * 120) + '",'
        '"url":"https://example.com/a"}'
    )
    ready = build_rule_fallback_polish_from_snippet(
        admin_source_key="thenewsapi",
        snippet=snippet,
        rule_title="同步资源 · AI · TheNewsAPI",
        rule_summary="规则摘要" * 12,
        feed_kind="news",
    )
    assert ready is not None
    assert "Anthropic" in ready["title"]


def test_published_at_clamps_old_upstream_to_sync_now():
    d = us_calendar_today()
    start, _ = utc_naive_bounds_for_us_date(d)
    old = start.replace(year=start.year - 1)
    now = datetime.utcnow()
    snippet = '{"title":"t","published_at":"' + old.isoformat() + 'Z"}'
    got = published_at_for_connector_ingest(snippet, now=now)
    assert got == now
