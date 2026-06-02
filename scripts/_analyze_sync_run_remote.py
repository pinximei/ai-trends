"""按 run_id 分析单次同步诊断。"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
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


RUN = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not RUN:
    print("usage: analyze_sync_run.py <run_id>")
    raise SystemExit(2)

_load_db_url_from_systemd()
sys.path.insert(0, ".")
from sqlalchemy import text
from backend.app.db import SessionLocal

db = SessionLocal()
try:
    print(f"=== RUN {RUN} BY LEVEL/STEP ===")
    for r in db.execute(
        text(
            "SELECT coalesce(source_key,'?'), level, step, count(*) "
            "FROM product_sync_diagnostic_logs WHERE run_id=:r "
            "GROUP BY 1,2,3 ORDER BY count(*) DESC"
        ),
        {"r": RUN},
    ):
        print("DIAG", tuple(r))

    errs = db.execute(
        text(
            "SELECT created_at, source_key, step, substr(message,1,380) "
            "FROM product_sync_diagnostic_logs "
            "WHERE run_id=:r AND level='error' ORDER BY id"
        ),
        {"r": RUN},
    ).fetchall()
    print("ERROR_COUNT", len(errs))
    for ts, sk, step, msg in errs:
        print(f"{ts} | {sk} | {step} | {(msg or '').replace(chr(10), ' ')[:360]}")

    print("=== SKIPS THIS RUN ===")
    for sk, step, msg in db.execute(
        text(
            "SELECT source_key, step, substr(message,1,220) "
            "FROM product_sync_diagnostic_logs "
            "WHERE run_id=:r AND step LIKE 'skip%' ORDER BY id"
        ),
        {"r": RUN},
    ):
        print(f"SKIP | {sk} | {step} | {(msg or '')[:200]}")

    since = datetime.utcnow() - timedelta(minutes=15)
    print("=== LLM POLISH LAST 15MIN ===")
    for r in db.execute(
        text(
            "SELECT success, substr(coalesce(error_code,''),1,72), count(*) "
            "FROM product_llm_usage_logs "
            "WHERE scenario='article_ingest_polish' AND created_at>=:s "
            "GROUP BY 1,2 ORDER BY count(*) DESC"
        ),
        {"s": since},
    ):
        print("LLM", tuple(r))

    print("=== CONNECTOR LOGS #1298+ ===")
    for r in db.execute(
        text(
            "SELECT l.id, c.admin_source_key, l.status, l.rows_ingested, "
            "l.started_at, l.finished_at "
            "FROM product_connector_logs l "
            "JOIN product_connectors c ON c.id=l.connector_id "
            "WHERE l.id >= 1298 ORDER BY l.id"
        ),
    ):
        print("LOG", tuple(r))
finally:
    db.close()
