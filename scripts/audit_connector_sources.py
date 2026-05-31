#!/usr/bin/env python3
"""巡检各连接器：拉取 pack 条数、上游字数、README、LLM Key（本地/运维用）。"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend.app.domain import articles as art
from backend.app.connector_heat_fetch import (
    sync_github_trending_top_details,
    sync_newsapi_top_headlines,
    GITHUB_TRENDING_DEFAULT,
)
from backend.app.llm_settings_service import resolve_llm_http_config


def _pack_summary(name: str, code: int, body: str) -> None:
    print(f"\n=== {name} HTTP {code} ===")
    if code < 200 or code >= 300:
        print((body or "")[:500])
        return
    try:
        pack = json.loads(body)
    except json.JSONDecodeError:
        print("not json", (body or "")[:300])
        return
    items = pack.get("connector_sync_items_v1") or []
    note = pack.get("note") or ""
    diag = pack.get("diag") or {}
    print(f"note={note} items={len(items)} diag={json.dumps(diag, ensure_ascii=False)}")
    for i, it in enumerate(items[:3]):
        snip = (it.get("snippet") or "").strip()
        ok, msg = art.connector_upstream_has_ingest_material(snip, name)
        chars = art.connector_upstream_material_char_count(snip)
        has_readme = "readme_md" in snip and '"readme_md"' in snip
        title = ""
        try:
            title = str(json.loads(snip).get("title") or json.loads(snip).get("full_name") or "")[:60]
        except Exception:
            pass
        flag = "OK" if ok else "SKIP"
        print(f"  [{i+1}] {flag} chars={chars} readme_in_snippet={has_readme} | {title}")
        if not ok:
            print(f"       {msg}")


def main() -> int:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    db_url = os.getenv("DATABASE_URL", "").strip()
    llm_ok = "no_db"
    if db_url:
        eng = create_engine(db_url)
        with Session(eng) as db:
            _b, key, model = resolve_llm_http_config(db)
            llm_ok = f"key={'yes' if key else 'NO'} model={model}"
    print(f"LLM: {llm_ok}")

    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_API_KEY") or ""
    headers = {"Authorization": f"Bearer {gh_token}"} if gh_token else {}
    print(f"GitHub token configured: {bool(gh_token)}")
    code, body = sync_github_trending_top_details(GITHUB_TRENDING_DEFAULT, headers, limit=5)
    _pack_summary("github", code, body)

    news_key = os.getenv("NEWSAPI_API_KEY") or os.getenv("NEWSAPI_KEY") or ""
    if news_key:
        h = {"X-Api-Key": news_key}
        code2, body2 = sync_newsapi_top_headlines(
            "https://newsapi.org/v2/top-headlines?country=us&category=technology&pageSize=5",
            h,
            limit=5,
        )
        _pack_summary("newsapi", code2, body2)
    else:
        print("\n=== newsapi skipped (no NEWSAPI_API_KEY) ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
