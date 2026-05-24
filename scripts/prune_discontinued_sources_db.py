"""
从当前库删除已下线内置数据源（含 TAAFT、Acquire）的配置、连接器与文章。

用法（仓库根目录，需与线上一致的 AITRENDS_DATABASE_URL / AISOU_DB_URL_*）:
  py -3.12 scripts/prune_discontinued_sources_db.py
  py -3.12 scripts/prune_discontinued_sources_db.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="仅统计，不删除")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    from sqlalchemy import func, select

    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.models import AdminSourceConfig
    from backend.app.product_connectors_bootstrap import (
        _article_clauses_for_admin_source_keys,
        prune_discontinued_bootstrap_admin_sources,
    )
    from backend.app.product_models import Article, ProductConnector
    from backend.app.services import DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES

    ensure_schema_compatibility()
    keys = tuple(sorted(DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES))
    db = SessionLocal()
    try:
        n_src = db.scalar(
            select(func.count()).select_from(AdminSourceConfig).where(AdminSourceConfig.source.in_(keys))
        )
        n_conn = db.scalar(
            select(func.count()).select_from(ProductConnector).where(ProductConnector.admin_source_key.in_(keys))
        )
        clause = _article_clauses_for_admin_source_keys(keys)
        n_art = (
            db.scalar(select(func.count()).select_from(Article).where(clause))
            if clause is not None
            else 0
        )
        print(f"database: {db.get_bind().url.render_as_string(hide_password=True)}")
        print(f"discontinued keys ({len(keys)}): {', '.join(keys)}")
        print(f"would delete: admin_sources={n_src} connectors={n_conn} articles={n_art}")
        if args.dry_run:
            return 0
        out = prune_discontinued_bootstrap_admin_sources(db)
        print(
            "deleted:",
            f"admin_sources={out.get('admin_sources_deleted', 0)}",
            f"connectors={out.get('connectors_deleted', 0)}",
            f"articles={out.get('articles_deleted', 0)}",
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
