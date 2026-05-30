#!/usr/bin/env python3
"""验证 News 快讯二次拉取：列表 API + enrich diag + 上游汉字门槛。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.connector_heat_fetch import (
    sync_hacker_news_top_details,
    sync_newsapi_top_headlines,
    sync_thenewsapi_top_news,
)
from backend.app.domain import articles as art


def _check_pack(name: str, code: int, body: str) -> bool:
    print(f"\n=== {name} HTTP {code} ===")
    if code < 200 or code >= 300:
        print("FAIL: bad status")
        print((body or "")[:400])
        return False
    try:
        pack = json.loads(body)
    except json.JSONDecodeError:
        print("FAIL: not json")
        return False
    items = pack.get("connector_sync_items_v1") or []
    diag = pack.get("diag") or {}
    print(f"note={pack.get('note')} items={len(items)}")
    print(f"diag={json.dumps(diag, ensure_ascii=False)}")
    if not items:
        print("WARN: empty pack (API/key/window)")
        return True
    ok_n = 0
    for i, it in enumerate(items[:5]):
        snip = (it.get("snippet") or "").strip()
        row = json.loads(snip)
        upstream_ok, msg = art.connector_upstream_has_ingest_material(snip, name)
        via = row.get("content_enriched_via") or "-"
        chars = art.connector_upstream_material_char_count(snip)
        title = (row.get("title") or "")[:50]
        flag = "OK" if upstream_ok else "THIN"
        print(f"  [{i+1}] [{flag}] material_chars={chars} via={via} | {title}")
        if not upstream_ok:
            print(f"       {msg}")
        else:
            ok_n += 1
    enrich_fetch = int(diag.get("enrich_url_fetch") or 0) + int(diag.get("enrich_hn_firebase") or 0)
    print(f"material_ok={ok_n}/{min(len(items),5)} enrich_fetched={enrich_fetch}")
    return True


def main() -> int:
    ua = {"User-Agent": "aisoul-verify-news-enrich/1.0"}
    ok = True
    hn_ok = _check_pack(
        "hacker_news",
        *sync_hacker_news_top_details(
            "https://hn.algolia.com/api/v1/search?tags=front_page",
            ua,
            limit=5,
        ),
    )
    ok &= hn_ok
    # newsapi / thenewsapi need keys
    try:
        from scripts.load_local_credentials import load_newsapi_credentials

        key = load_newsapi_credentials()
    except Exception:
        key = os.environ.get("NEWSAPI_KEY") or ""
    if key:
        h = {**ua, "X-Api-Key": key}
        code, body = sync_newsapi_top_headlines(
            "https://newsapi.org/v2/top-headlines?country=us&category=technology&pageSize=5",
            h,
            limit=5,
        )
        if code == 0:
            print("\n=== newsapi SKIP (network error) ===")
        else:
            ok &= _check_pack("newsapi", code, body)
    else:
        print("\n=== newsapi SKIP (no API key) ===")

    try:
        from scripts.load_local_credentials import load_thenewsapi_credentials

        token = load_thenewsapi_credentials()
    except Exception:
        token = ""
    if token:
        sep = "&" if "?" in "https://api.thenewsapi.com/v1/news/top?locale=us&language=en&categories=tech&limit=5" else "?"
        url = f"https://api.thenewsapi.com/v1/news/top?locale=us&language=en&categories=tech&limit=5{sep}api_token={token}"
        code, body = sync_thenewsapi_top_news(url, ua, limit=5)
        ok &= _check_pack("thenewsapi", code, body)
    else:
        print("\n=== thenewsapi SKIP (no API token) ===")

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
