"""本地：Hacker News Algolia 首页热门 → 连接器同步 → 入库。

用法（仓库根目录）:
  py -3.12 scripts/run_hacker_news_sync_local.py
  py -3.12 scripts/run_hacker_news_sync_local.py --sqlite
  py -3.12 scripts/run_hacker_news_sync_local.py --no-sync
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sqlite",
        nargs="?",
        const=str(ROOT / "backend" / "data" / "dev_local.db"),
        default=None,
    )
    ap.add_argument("--no-sync", action="store_true")
    return ap.parse_args()


def _configure_db(sqlite_arg: str | None) -> None:
    if sqlite_arg is None:
        default = ROOT / "backend" / "data" / "dev_local.db"
        if default.is_file():
            sqlite_arg = str(default)
    if sqlite_arg:
        p = Path(sqlite_arg)
        p.parent.mkdir(parents=True, exist_ok=True)
        os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{p.resolve().as_posix()}"


def main() -> int:
    args = _parse_args()
    _configure_db(args.sqlite)
    sys.path.insert(0, str(ROOT))

    from sqlalchemy import func, select

    from backend.app.connector_heat_fetch import sync_hacker_news_top_details
    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.lifespan import _startup_sync
    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import Article, ProductConnector, ProductConnectorLog
    from backend.app.routers.admin_extended import run_connector_sync

    ensure_schema_compatibility()
    _startup_sync()

    src = None
    db = SessionLocal()
    try:
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "hacker_news"))
        url = (src.api_base if src else "") or "https://hn.algolia.com/api/v1/search?tags=front_page"
        print(f"api_base: {url[:120]}")

        headers = {"User-Agent": "AiTrends-HNLocal/1.0", "Accept": "application/json"}
        code, body = sync_hacker_news_top_details(url, headers)
        n = 0
        if body:
            try:
                n = len(json.loads(body).get("connector_sync_items_v1") or [])
            except json.JSONDecodeError:
                pass
        print(f"HTTP probe: status={code} items={n}")
        if not (200 <= code < 300) or n < 1:
            print("FAIL: 未拿到有效 HN 条目")
            return 1
        if args.no_sync:
            return 0

        conn = db.scalar(
            select(ProductConnector)
            .where(ProductConnector.admin_source_key == "hacker_news")
            .order_by(ProductConnector.id)
        )
        if not conn:
            print("FAIL: 无 hacker_news 连接器")
            return 1
        conn.enabled = True
        conn.min_interval_seconds = 0
        cfg = dict(conn.config_json or {})
        cfg["url"] = url
        conn.config_json = cfg
        db.flush()

        before = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.third_party_source.like("%hacker_news%"))
        )
        out = run_connector_sync(db, conn.id, actor="local-hn-script", bypass_rate_limit=True)
        db.commit()
        after = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.third_party_source.like("%hacker_news%"))
        )
        log = db.scalar(select(ProductConnectorLog).order_by(ProductConnectorLog.id.desc()).limit(1))
        print("sync:", {k: out.get(k) for k in ("articles_created", "error", "http_status") if k in out})
        print(f"articles hacker_news: {before} -> {after}")
        if log:
            print(f"log: status={log.status} rows={log.rows_ingested}")
        if out.get("error"):
            return 3
        if not os.environ.get("AITRENDS_LLM_API_KEY", "").strip():
            print("WARN: 未设置 AITRENDS_LLM_API_KEY，入库可能为 0")
        return 0 if int(out.get("articles_created") or 0) > 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
