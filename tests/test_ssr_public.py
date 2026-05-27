"""首页 SSR 注入。"""
from __future__ import annotations

import json

from backend.app.application.ssr_public import inject_home_ssr_into_index_html, read_bootstrap_from_html


def test_inject_home_ssr_puts_json_and_root_markup() -> None:
    html = "<!doctype html><html><head></head><body><div id='root'></div></body></html>"
    bootstrap = {
        "news": [],
        "apps": [],
        "editorialNews": [],
        "editorialApps": [],
        "highlightApps": [],
        "highlightMonetization": [],
        "newsLanes": [],
        "appsLanes": [],
        "sourceFacets": [],
        "topCategories": [],
        "industryWind": {
            "compare_mode": "week_over_week",
            "period_label": "本周 vs 上周",
            "industries": [
                {
                    "headline": "Cursor 工具链",
                    "summary": "多篇上榜",
                    "article_count": 3,
                    "prior_count": 1,
                    "growth_pct": 200.0,
                    "signal": "升温",
                }
            ],
        },
        "activeSourceCount": 6,
        "activeSourceKeys": [],
        "trendOverview": None,
    }
    out = inject_home_ssr_into_index_html(html, bootstrap)
    assert 'id="aitrends-ssr-home"' in out
    assert "ssr-home-fallback" in out
    assert "Cursor" in out
    parsed = read_bootstrap_from_html(out)
    assert parsed is not None
    assert parsed["industryWind"]["industries"][0]["headline"] == "Cursor 工具链"
