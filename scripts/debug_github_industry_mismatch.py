#!/usr/bin/env python3
"""Debug industry_id mismatch for GitHub snapshot article lookup."""
from __future__ import annotations

import os
from pathlib import Path


def _load_db_url_from_systemd(unit: str = "aisoul-backend") -> None:
    marker = "AITRENDS_DATABASE_URL="
    for path in (f"/etc/systemd/system/{unit}.service", f"/lib/systemd/system/{unit}.service"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if marker in line:
                os.environ["AITRENDS_DATABASE_URL"] = line[line.index(marker) + len(marker) :].strip()
                return


_load_db_url_from_systemd()

from sqlalchemy import desc, select

from backend.app.application.github_trending_snapshot import _lookup_article_id
from backend.app.db import SessionLocal
from backend.app.product_models import Article, GithubTrendingSnapshot, Industry


def main() -> None:
    db = SessionLocal()
    try:
        ai = db.scalar(select(Industry).where(Industry.slug == "ai").limit(1))
        ai_id = int(ai.id) if ai else None
        print("ai industry_id", ai_id)

        snap = db.scalars(select(GithubTrendingSnapshot).order_by(desc(GithubTrendingSnapshot.id)).limit(1)).first()
        if not snap:
            print("no snapshot")
            return

        for row in (snap.items_json or [])[:5]:
            fn = str(row.get("full_name") or "")
            ext = row.get("source_external_id")
            aid_with = _lookup_article_id(
                db, industry_id=ai_id, source_external_id=ext, full_name=fn
            )
            aid_without = _lookup_article_id(
                db, industry_id=None, source_external_id=ext, full_name=fn
            )
            print("rank", row.get("rank"), fn)
            print("  lookup with industry", aid_with, "without", aid_without)
            if ext:
                a = db.scalar(
                    select(Article)
                    .where(Article.source_external_id == str(ext)[:512])
                    .order_by(desc(Article.id))
                    .limit(1)
                )
                if a:
                    print("  article", a.id, "industry_id", a.industry_id, "status", a.status)
    finally:
        db.close()


if __name__ == "__main__":
    main()
