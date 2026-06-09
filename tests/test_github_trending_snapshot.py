from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.app.application.github_trending_snapshot import (
    _parse_pack_meta,
    _ranked_rows_from_pack,
    period_date_for_since,
    week_ending_sunday,
)


def _sample_pack(*, since: str = "daily") -> str:
    items = []
    for i, slug in enumerate(("acme/a", "acme/b"), start=1):
        repo = {
            "full_name": slug,
            "name": slug.split("/")[-1],
            "node_id": f"R{i}",
            "trending_stars_today": 100 * i,
            "_aisoul_trending": {
                "since": since,
                "rank": i,
                "discovery_url": f"https://github.com/trending?since={since}",
            },
        }
        items.append({"snippet": json.dumps(repo, ensure_ascii=False)})
    return json.dumps(
        {
            "connector_sync_items_v1": items,
            "note": f"github_trending_{since}",
        },
        ensure_ascii=False,
    )


def test_period_date_daily_and_weekly():
    tz = ZoneInfo("Asia/Shanghai")
    daily = datetime(2026, 6, 9, 8, 0, tzinfo=tz)
    assert period_date_for_since("daily", when=daily) == date(2026, 6, 9)
    assert week_ending_sunday(date(2026, 6, 9)) == date(2026, 6, 14)
    assert period_date_for_since("weekly", when=daily) == date(2026, 6, 14)


def test_parse_pack_meta_and_ranked_rows():
    pack = _sample_pack(since="weekly")
    since, url = _parse_pack_meta(pack)
    assert since == "weekly"
    assert "since=weekly" in url
    rows = _ranked_rows_from_pack(pack)
    assert len(rows) == 2
    assert rows[0]["full_name"] == "acme/a"
    assert rows[0]["rank"] == 1
