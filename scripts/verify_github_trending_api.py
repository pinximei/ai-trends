#!/usr/bin/env python3
"""Verify public GitHub trending API returns article_id links."""
from __future__ import annotations

import json
import sys
import urllib.request


def check(since: str, base: str = "http://127.0.0.1:8000") -> None:
    url = f"{base}/api/public/v1/github/trending?since={since}&limit=10"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    items = data.get("items") or []
    aids = [i.get("article_id") for i in items]
    print(
        since,
        "count",
        len(items),
        "with_aid",
        sum(1 for a in aids if a),
        "period",
        data.get("period_date"),
    )
    print("aids", aids)


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    check("weekly", base)
    check("daily", base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
