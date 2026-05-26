"""本地：修复 github api_base → Trending，执行一次连接器同步并统计结果。

用法（仓库根目录）:
  py -3.12 scripts/run_github_sync_local.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select  # noqa: E402

from backend.app.connector_heat_fetch import GITHUB_TRENDING_DEFAULT  # noqa: E402
from backend.app.db import SessionLocal  # noqa: E402
from backend.app.models import AdminSourceConfig  # noqa: E402
from backend.app.product_connectors_bootstrap import repair_short_probe_admin_sources  # noqa: E402
from backend.app.product_models import Article, ProductConnector, ProductConnectorLog  # noqa: E402
from backend.app.routers.admin_extended import run_connector_sync  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        repair_short_probe_admin_sources(db)
        row = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "github"))
        if row:
            print(f"github api_base -> {(row.api_base or '')[:80]}")
        conn = db.scalar(
            select(ProductConnector)
            .where(ProductConnector.admin_source_key == "github")
            .order_by(ProductConnector.id)
        )
        if not conn:
            print("FAIL: 无 github 连接器")
            return 1
        print(f"connector id={conn.id} enabled={conn.enabled}")
        before = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.third_party_source.like("%github%"))
        )
        out = run_connector_sync(db, conn.id, actor="local-script", bypass_rate_limit=True)
        db.commit()
        after = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.third_party_source.like("%github%"))
        )
        log = db.scalar(select(ProductConnectorLog).order_by(ProductConnectorLog.id.desc()).limit(1))
        print("sync result:", out)
        print(f"github articles: {before} -> {after}")
        if log:
            print(
                f"last log: status={log.status} rows={log.rows_ingested} err={(log.error_message or '')[:200]}"
            )
        created = int(out.get("articles_created") or 0)
        err = out.get("error")
        return 0 if created > 0 or (not err and (out.get("http_status") or 0) == 200) else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
