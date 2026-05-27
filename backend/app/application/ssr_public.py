"""首页 SSR：注入仪表盘 JSON + 行业风向首屏 HTML（供 Nginx 回退到后端渲染 index）。"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .home_public import get_home_dashboard

_SSR_BOOTSTRAP_ID = "aitrends-ssr-home"
_INDEX_CANDIDATES = (
    Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html",
    Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html",
)


def _repo_index_html() -> Path | None:
    for p in _INDEX_CANDIDATES:
        if p.is_file():
            return p
    return None


def build_home_ssr_bootstrap(db: Session, *, industry_slug: str = "ai") -> dict[str, Any]:
    """与前端 ``HomeDashboardCachePayload`` 字段对齐。"""
    dash = get_home_dashboard(db, industry_slug=industry_slug, published_within_days=30)
    return {
        "news": dash.get("news") or [],
        "apps": dash.get("apps") or [],
        "editorialNews": dash.get("editorial_news") or [],
        "editorialApps": dash.get("editorial_apps") or [],
        "highlightApps": dash.get("highlight_replicable_apps") or [],
        "highlightMonetization": dash.get("highlight_monetization_apps") or [],
        "newsLanes": dash.get("news_source_lanes") or [],
        "appsLanes": dash.get("apps_source_lanes") or [],
        "sourceFacets": dash.get("source_facets") or [],
        "topCategories": dash.get("top_categories") or [],
        "industryWind": dash.get("industry_wind"),
        "activeSourceCount": dash.get("active_source_count") or 6,
        "activeSourceKeys": dash.get("active_source_keys") or [],
        "trendOverview": dash.get("trend"),
    }


def _esc(text: str) -> str:
    return html.escape((text or "").strip(), quote=True)


def render_industry_wind_ssr_html(wind: dict[str, Any] | None) -> str:
    if not wind or not isinstance(wind.get("industries"), list) or not wind["industries"]:
        return ""
    period = _esc(str(wind.get("period_label") or "本周 vs 上周"))
    parts = [
        '<section id="industry-wind" class="ui-card scroll-mt-24 overflow-hidden p-5 sm:p-6" data-ssr="industry-wind">',
        '<h2 class="text-lg font-bold text-slate-900">行业风向</h2>',
        f'<p class="mt-1 text-sm text-slate-600">{period}</p>',
        '<ol class="mt-4 space-y-3 list-none p-0 m-0">',
    ]
    for row in wind["industries"][:6]:
        if not isinstance(row, dict):
            continue
        headline = _esc(str(row.get("headline") or row.get("label") or ""))
        summary = _esc(str(row.get("summary") or ""))
        signal = _esc(str(row.get("signal") or ""))
        growth = row.get("growth_pct")
        growth_s = "—" if growth is None else f"{growth:+.0f}%" if isinstance(growth, (int, float)) else _esc(str(growth))
        ac = int(row.get("article_count") or 0)
        pc = int(row.get("prior_count") or 0)
        parts.append(
            f'<li class="rounded-xl border border-slate-200/80 bg-slate-50/50 px-3 py-3">'
            f'<p class="text-sm font-bold text-slate-900">{headline} '
            f'<span class="text-xs font-semibold text-orange-700">{signal}</span></p>'
            f'<p class="mt-1 text-xs text-slate-600">{summary}</p>'
            f'<p class="mt-1 text-xs text-slate-500">较上周 {growth_s} · 本周 {ac} 篇 · 上周 {pc} 篇</p>'
            f"</li>"
        )
    parts.append("</ol></section>")
    return "".join(parts)


def inject_home_ssr_into_index_html(html: str, bootstrap: dict[str, Any]) -> str:
    payload_json = json.dumps(bootstrap, ensure_ascii=False, separators=(",", ":"))
    payload_json = payload_json.replace("</", "<\\/")
    script = f'<script id="{_SSR_BOOTSTRAP_ID}" type="application/json">{payload_json}</script>'

    wind_html = render_industry_wind_ssr_html(bootstrap.get("industryWind"))
    root_inner = f'<div id="ssr-home-fallback" data-ssr="home">{wind_html}</div>' if wind_html else ""

    if f'id="{_SSR_BOOTSTRAP_ID}"' not in html:
        html = html.replace("</head>", f"{script}\n</head>", 1)
    if root_inner and "ssr-home-fallback" not in html:
        replaced, n = re.subn(
            r'<div\s+id=["\']root["\']\s*>\s*</div>',
            f'<div id="root">{root_inner}</div>',
            html,
            count=1,
        )
        if n == 0 and '<div id="root">' in html:
            html = html.replace('<div id="root">', f'<div id="root">{root_inner}', 1)
        else:
            html = replaced
    return html


def render_home_ssr_document(db: Session, *, industry_slug: str = "ai") -> str:
    index_path = _repo_index_html()
    if not index_path:
        raise FileNotFoundError("frontend/dist/index.html not found; run npm run build in frontend/")
    html = index_path.read_text(encoding="utf-8")
    bootstrap = build_home_ssr_bootstrap(db, industry_slug=industry_slug)
    return inject_home_ssr_into_index_html(html, bootstrap)


def read_bootstrap_from_html(html: str) -> dict[str, Any] | None:
    m = re.search(
        rf'<script id="{re.escape(_SSR_BOOTSTRAP_ID)}" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
