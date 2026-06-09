#!/usr/bin/env python3
"""回填 github_trending_snapshots.items_json 中的 article_id。"""
from __future__ import annotations

import json
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
from sqlalchemy.orm.attributes import flag_modified

from backend.app.application.github_trending_snapshot import _lookup_article_id
from backend.app.db import SessionLocal
from backend.app.product_models import GithubTrendingSnapshot, Industry


def main() -> int:
    db = SessionLocal()
    try:
        industry = db.scalar(select(Industry).where(Industry.slug == "ai").limit(1))
        industry_id = int(industry.id) if industry else None
        snaps = db.scalars(
            select(GithubTrendingSnapshot).order_by(desc(GithubTrendingSnapshot.created_at)).limit(20)
        ).all()
        fixed = 0
        for snap in snaps:
            items = list(snap.items_json or [])
            changed = False
            for row in items:
                if not isinstance(row, dict):
                    continue
                if row.get("article_id"):
                    continue
                aid = _lookup_article_id(
                    db,
                    industry_id=industry_id,
                    source_external_id=row.get("source_external_id"),
                    full_name=str(row.get("full_name") or ""),
                )
                if aid:
                    row["article_id"] = aid
                    changed = True
                    fixed += 1
            if changed:
                snap.items_json = items
                flag_modified(snap, "items_json")
        db.commit()
        print(f"backfilled article_id links: {fixed}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
