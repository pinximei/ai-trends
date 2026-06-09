#!/usr/bin/env python3
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

from backend.app.db import SessionLocal
from backend.app.product_models import GithubTrendingSnapshot


def main() -> None:
    db = SessionLocal()
    try:
        snaps = db.scalars(
            select(GithubTrendingSnapshot).order_by(desc(GithubTrendingSnapshot.id)).limit(10)
        ).all()
        for snap in snaps:
            aids = [r.get("article_id") for r in (snap.items_json or []) if isinstance(r, dict)]
            linked = sum(1 for a in aids if a)
            print(
                "id",
                snap.id,
                snap.since,
                snap.period_date,
                "items",
                snap.item_count,
                "linked",
                linked,
                "created",
                snap.created_at,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
