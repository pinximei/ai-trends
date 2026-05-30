#!/usr/bin/env python3
"""审计近期已发布文章是否「仅链接」。"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from backend.app.domain import articles as art

MIN = art.PUBLISH_MIN_SUBSTANTIVE_CHARS


def main() -> None:
    url = (
        os.environ.get("AISOU_DATABASE_URL")
        or os.environ.get("AISOU_DB_URL_TEST")
        or "postgresql+psycopg://aisoul:aisoul@127.0.0.1:5432/aisoul"
    )
    eng = create_engine(url)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    q = text(
        """
        SELECT id, title, feed_kind, admin_source_key, status,
               summary, body, ai_tabs_json,
               published_at, updated_at
        FROM product_articles
        WHERE status = 'published' AND updated_at >= :since
        ORDER BY updated_at DESC
        LIMIT 80
        """
    )
    with eng.connect() as c:
        rows = list(c.execute(q, {"since": since}).mappings())

    print(f"published since {since.date()}: {len(rows)}\n")
    by_src: dict[str, list] = {}
    link_only: list = []
    for r in rows:
        blob = art.stored_article_text_blob(
            title=r["title"] or "",
            summary=r["summary"] or "",
            body=r["body"] or "",
            ai_tabs_json=r.get("ai_tabs_json"),
        )
        stripped = art.strip_urls_and_markdown_links(blob)
        sub = art.polish_substantive_char_count(stripped)
        cjk = art.polish_substantive_cjk_count(stripped)
        raw = art.polish_substantive_char_count(blob)
        fk = str(r["feed_kind"] or "news").strip().lower()
        ok = art.stored_article_has_substantive_content(
            title=r["title"] or "",
            summary=r["summary"] or "",
            body=r["body"] or "",
            ai_tabs_json=r.get("ai_tabs_json"),
            feed_kind=fk,
        )
        sk = (r["admin_source_key"] or "?").strip()
        by_src.setdefault(sk, []).append(sub)
        rec = {
            "id": r["id"],
            "fk": fk,
            "src": sk,
            "sub": sub,
            "cjk": cjk,
            "raw": raw,
            "title": (r["title"] or "")[:60],
            "summary_head": (r["summary"] or "")[:120],
            "body_head": (r["body"] or "")[:120],
        }
        if not ok:
            link_only.append(rec)

    print("=== by admin_source_key (avg substantive after strip URLs) ===")
    for sk, scores in sorted(by_src.items()):
        ok_n = sum(1 for s in scores if s >= MIN)
        bad = len(scores) - ok_n
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {sk}: n={len(scores)} ok={ok_n} link_only={bad} avg_sub={avg:.0f}")

    print(f"\n=== LINK_ONLY (<{MIN} total or news CJK<{art.PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS}) ===")
    for rec in link_only:
        print(
            f"  id={rec['id']} fk={rec['fk']} src={rec['src']} sub={rec['sub']} cjk={rec['cjk']} raw={rec['raw']}"
            f" | {rec['title']}"
        )
        print(f"    summary: {rec['summary_head']!r}")
        print(f"    body: {rec['body_head']!r}")

    print("\n=== NEWS feed_kind only ===")
    for r in rows:
        if (r["feed_kind"] or "").lower() != "news":
            continue
        blob = art.stored_article_text_blob(
            title=r["title"] or "",
            summary=r["summary"] or "",
            body=r["body"] or "",
            ai_tabs_json=r.get("ai_tabs_json"),
        )
        stripped = art.strip_urls_and_markdown_links(blob)
        sub = art.polish_substantive_char_count(stripped)
        cjk = art.polish_substantive_cjk_count(stripped)
        ok = art.stored_article_has_substantive_content(
            title=r["title"] or "",
            summary=r["summary"] or "",
            body=r["body"] or "",
            ai_tabs_json=r.get("ai_tabs_json"),
            feed_kind="news",
        )
        flag = "OK" if ok else "LINK_ONLY"
        print(
            f"  [{flag}] id={r['id']} src={r['admin_source_key']} sub={sub} cjk={cjk} | {(r['title'] or '')[:55]}"
        )


if __name__ == "__main__":
    main()
