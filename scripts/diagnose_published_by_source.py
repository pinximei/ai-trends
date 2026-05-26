#!/usr/bin/env python3
"""统计各数据源已发布文章数量（近 N 天展示时效），用于排查「某源没数据」。"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select

from backend.app.application.article_public import _article_matches_public_feed, _freshness_expr
from backend.app.db import SessionLocal
from backend.app.domain.articles import admin_source_key
from backend.app.product_models import Article, Industry


def main() -> int:
    p = argparse.ArgumentParser(description="Count published articles per admin_source_key")
    p.add_argument("--days", type=int, default=30, help="展示时效窗口（天）")
    p.add_argument("--industry", default="ai")
    args = p.parse_args()

    db = SessionLocal()
    try:
        ind = db.scalar(select(Industry).where(Industry.slug == args.industry.strip().lower()))
        if not ind:
            print(f"industry {args.industry!r} not found")
            return 1
        since = datetime.utcnow() - timedelta(days=max(1, args.days))
        fe = _freshness_expr()
        rows = db.scalars(
            select(Article).where(
                Article.industry_id == ind.id,
                Article.status == "published",
                fe.isnot(None),
                fe >= since,
            )
        ).all()
        print(f"=== published in last {args.days}d (display_at) industry={args.industry} total={len(rows)} ===\n")
        by_src: Counter[str] = Counter()
        apps_lane: Counter[str] = Counter()
        news_lane: Counter[str] = Counter()
        for a in rows:
            sk = admin_source_key(a.third_party_source) or "(none)"
            by_src[sk] += 1
            if _article_matches_public_feed(a, "apps"):
                apps_lane[sk] += 1
            if _article_matches_public_feed(a, "news"):
                news_lane[sk] += 1
        print("all sources:")
        for k, n in by_src.most_common():
            print(f"  {k:20} {n}")
        print("\napps feed lane:")
        for k, n in apps_lane.most_common():
            print(f"  {k:20} {n}")
        print("\nnews feed lane:")
        for k, n in news_lane.most_common():
            print(f"  {k:20} {n}")
        ph = [a for a in rows if admin_source_key(a.third_party_source) == "product_hunt"]
        if ph:
            print(f"\nproduct_hunt sample (max 5 titles):")
            for a in ph[:5]:
                lane = "apps" if _article_matches_public_feed(a, "apps") else "news"
                print(f"  id={a.id} lane={lane} heat={a.heat_score} tier={a.replication_tier!r} title={(a.title or '')[:60]}")
        else:
            print("\nproduct_hunt: 0 rows in window — check connector sync logs (skip_llm_*, no_posts, 429).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
