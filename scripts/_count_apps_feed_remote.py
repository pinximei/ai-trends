#!/usr/bin/env python3
"""Count public apps feed under different filters (remote diag)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.environ.get("AITRENDS_REPO", os.getcwd()))
os.chdir(os.environ.get("AITRENDS_REPO", os.getcwd()))

from backend.app.db import SessionLocal
from backend.app.application import article_public as ap

db = SessionLocal()
try:
    base = dict(
        feed="apps",
        industry_slug="ai",
        segment_id=None,
        segment_ids=None,
        published_on_latest_day=False,
    )
    for days in (2, 7, 30, None):
        label = f"days={days or 'all'}"
        for repl in (False, True):
            r = ap.list_articles_feed_by_heat_top(
                db,
                **base,
                published_within_days=days,
                replication_complete=repl,
                heat_page_size=500,
                heat_max_ranked=500,
            )
            print(f"{label} replication_complete={repl}: total={r['total']}")
finally:
    db.close()
