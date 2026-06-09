#!/usr/bin/env python3
"""生产机：初始化 github_weekly 并同步日榜/周榜，写入 trending 快照。"""
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

from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.product_connectors_bootstrap import ensure_github_weekly_source_and_connector
from backend.app.product_models import ProductConnector
from backend.app.routers.admin_extended import run_connector_sync


def main() -> int:
    db = SessionLocal()
    try:
        ensure_github_weekly_source_and_connector(db)
        results = []
        for sk in ("github", "github_weekly"):
            conn = db.scalar(
                select(ProductConnector)
                .where(
                    ProductConnector.admin_source_key == sk,
                    ProductConnector.enabled.is_(True),
                )
                .order_by(ProductConnector.id)
                .limit(1)
            )
            if not conn:
                results.append({"source": sk, "error": "no_enabled_connector"})
                continue
            out = run_connector_sync(
                db,
                conn.id,
                actor="bootstrap_github_snapshots",
                bypass_rate_limit=True,
            )
            results.append({"source": sk, "connector_id": conn.id, **out})
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
