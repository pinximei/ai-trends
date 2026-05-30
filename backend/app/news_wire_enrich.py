"""快讯源二次取数：列表 API 一次拉全后，对素材过薄的条目按原文链接（或 HN item API）补正文。"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from .domain.articles import (
    NEWS_WIRE_UPSTREAM_MIN_CHARS,
    connector_snippet_upstream_text_blob,
    polish_substantive_char_count,
)

NEWS_ENRICH_HTTP_TIMEOUT = 22.0
NEWS_ENRICH_BODY_MAX = 12_000
NEWS_ENRICH_HTML_SCAN_MAX = 400_000

# 二次抓取间隔（秒），避免连续 hammer 同一域名
NEWS_ENRICH_FETCH_DELAY = 0.15

_SKIP_FETCH_HOST_SUFFIXES = (
    "news.ycombinator.com",
    "www.news.ycombinator.com",
    "news.google.com",
    "t.co",
)

_DEFAULT_UA = "AiTrends-NewsEnrich/1.0 (+https://github.com/aisoul)"


def _row_material_chars(row: dict[str, Any]) -> int:
    return polish_substantive_char_count(connector_snippet_upstream_text_blob(json.dumps(row, ensure_ascii=False)))


def _host_should_skip_fetch(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return True
    if not host:
        return True
    for suf in _SKIP_FETCH_HOST_SUFFIXES:
        if host == suf or host.endswith("." + suf):
            return True
    return False


def extract_text_from_html(html: str, *, max_len: int = NEWS_ENRICH_BODY_MAX) -> str:
    """轻量 HTML → 纯文本（无额外依赖）。"""
    raw = (html or "")[:NEWS_ENRICH_HTML_SCAN_MAX]
    if not raw.strip():
        return ""
    chunk = raw
    for pat in (
        r"<script[^>]*>[\s\S]*?</script>",
        r"<style[^>]*>[\s\S]*?</style>",
        r"<noscript[^>]*>[\s\S]*?</noscript>",
    ):
        chunk = re.sub(pat, " ", chunk, flags=re.IGNORECASE)
    picked = ""
    for tag in ("article", "main", "div", "body"):
        m = re.search(rf"<{tag}[^>]*>([\s\S]{{400,}})</{tag}>", chunk, flags=re.IGNORECASE)
        if m:
            picked = m.group(1)
            break
    if not picked:
        picked = chunk
    picked = re.sub(r"<br\s*/?>", "\n", picked, flags=re.IGNORECASE)
    picked = re.sub(r"</(?:p|div|h[1-6]|li|tr)>", "\n", picked, flags=re.IGNORECASE)
    picked = re.sub(r"<[^>]+>", " ", picked)
    picked = html_lib.unescape(picked)
    picked = re.sub(r"[ \t]+\n", "\n", picked)
    picked = re.sub(r"\n{3,}", "\n\n", picked)
    picked = re.sub(r"[ \t]{2,}", " ", picked).strip()
    if len(picked) > max_len:
        picked = picked[:max_len]
    return picked


def fetch_article_body_from_url(url: str, client: httpx.Client, *, headers: dict[str, str] | None = None) -> str:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")) or _host_should_skip_fetch(u):
        return ""
    h = {
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "User-Agent": _DEFAULT_UA,
    }
    if headers:
        h.update(headers)
    try:
        r = client.get(u, headers=h, timeout=NEWS_ENRICH_HTTP_TIMEOUT, follow_redirects=True)
    except Exception:
        return ""
    if r.status_code < 200 or r.status_code >= 400:
        return ""
    ctype = (r.headers.get("content-type") or "").lower()
    if "html" not in ctype and "text/plain" not in ctype and ctype:
        return ""
    text = r.text or ""
    if "text/plain" in ctype and "<" not in text[:200]:
        return text.strip()[:NEWS_ENRICH_BODY_MAX]
    return extract_text_from_html(text)


def fetch_hn_item_text(object_id: str, client: httpx.Client) -> str:
    oid = str(object_id or "").strip()
    if not oid.isdigit():
        return ""
    api = f"https://hacker-news.firebaseio.com/v0/item/{oid}.json"
    try:
        r = client.get(api, timeout=12.0, headers={"User-Agent": _DEFAULT_UA})
    except Exception:
        return ""
    if r.status_code < 200 or r.status_code >= 300:
        return ""
    try:
        data = r.json()
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    for key in ("title", "text"):
        v = str(data.get(key) or "").strip()
        if v:
            parts.append(v)
    return "\n\n".join(parts)[:NEWS_ENRICH_BODY_MAX]


def _merge_body_into_row(row: dict[str, Any], body: str, *, via: str) -> None:
    text = (body or "").strip()
    if not text:
        return
    text = text[:NEWS_ENRICH_BODY_MAX]
    row["article_body"] = text
    row["content_enriched_via"] = via
    desc = str(row.get("description") or "").strip()
    if desc and text not in desc:
        row["description"] = f"{desc}\n\n{text}"[:NEWS_ENRICH_BODY_MAX]
    elif not desc:
        row["description"] = text


def enrich_news_wire_row(
    row: dict[str, Any],
    source_key: str,
    client: httpx.Client,
    *,
    min_chars: int = NEWS_WIRE_UPSTREAM_MIN_CHARS,
) -> str:
    """
    单条补全。返回动作标签：skip_ok | skip_no_url | hn_firebase | url_fetch | fail。
    """
    if _row_material_chars(row) >= int(min_chars):
        return "skip_ok"
    sk = (source_key or row.get("source") or "").strip().lower()
    if sk == "hacker_news":
        story = str(row.get("story_text") or "").strip()
        if polish_substantive_char_count(story) >= int(min_chars):
            return "skip_ok"
        oid = str(row.get("objectID") or "").strip()
        if oid:
            body = fetch_hn_item_text(oid, client)
            if polish_substantive_char_count(body) >= int(min_chars):
                _merge_body_into_row(row, body, via="hn_firebase")
                return "hn_firebase"
        url = str(row.get("url") or "").strip()
        if url and not _host_should_skip_fetch(url):
            body = fetch_article_body_from_url(url, client)
            if polish_substantive_char_count(body) >= int(min_chars):
                _merge_body_into_row(row, body, via="url_fetch")
                return "url_fetch"
        return "fail"

    url = str(row.get("url") or "").strip()
    if not url or _host_should_skip_fetch(url):
        return "skip_no_url"
    body = fetch_article_body_from_url(url, client)
    if polish_substantive_char_count(body) >= int(min_chars):
        _merge_body_into_row(row, body, via="url_fetch")
        return "url_fetch"
    return "fail"


def enrich_news_wire_items(
    items: list[dict[str, Any]],
    source_key: str,
    *,
    client: httpx.Client | None = None,
    min_chars: int = NEWS_WIRE_UPSTREAM_MIN_CHARS,
    fetch_delay: float = NEWS_ENRICH_FETCH_DELAY,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    对列表 API 已打包的条目做二次 enrichment（仅处理素材不足者）。
    返回 (items, stats) 供 connector diag 合并。
    """
    stats = {
        "enrich_candidates": 0,
        "enrich_skip_ok": 0,
        "enrich_hn_firebase": 0,
        "enrich_url_fetch": 0,
        "enrich_skip_no_url": 0,
        "enrich_fail": 0,
    }
    if not items:
        return items, stats

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=NEWS_ENRICH_HTTP_TIMEOUT, follow_redirects=True)

    try:
        for i, row in enumerate(items):
            if not isinstance(row, dict):
                continue
            if _row_material_chars(row) >= int(min_chars):
                stats["enrich_skip_ok"] += 1
                continue
            stats["enrich_candidates"] += 1
            action = enrich_news_wire_row(row, source_key, client, min_chars=min_chars)
            key = f"enrich_{action}"
            if key in stats:
                stats[key] += 1
            elif action == "fail":
                stats["enrich_fail"] += 1
            if fetch_delay > 0 and i + 1 < len(items) and action in ("hn_firebase", "url_fetch"):
                import time

                time.sleep(fetch_delay)
    finally:
        if own_client and client is not None:
            client.close()

    return items, stats
