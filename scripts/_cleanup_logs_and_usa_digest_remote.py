"""生产：清理同步诊断/僵尸 connector 日志，并按美东当日重生成飞书摘要。"""
from __future__ import annotations

import os
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


_load_db_url_from_systemd()

from sqlalchemy import select, text

from backend.app.application.newsletter_daily_digest import run_daily_newsletter_digest_job
from backend.app.db import SessionLocal
from backend.app.models import NewsletterDailyDigest
from backend.app.newsletter_settings_service import get_newsletter_settings_merged
from backend.app.product_models import ProductConnectorLog
from backend.app.sync_diagnostic_log import clear_all as clear_sync_diagnostic_logs
from backend.app.us_content_calendar import us_calendar_today


def main() -> None:
    now = datetime.utcnow()
    keep_logs_after_id = int(os.environ.get("KEEP_CONNECTOR_LOGS_AFTER_ID", "1297"))
    print(f"=== cleanup logs {now.isoformat()} UTC ===")
    print(f"keep_connector_logs_with_id > {keep_logs_after_id}")

    db = SessionLocal()
    try:
        stuck = db.scalars(
            select(ProductConnectorLog).where(ProductConnectorLog.status == "running")
        ).all()
        for log in stuck:
            log.status = "failed"
            log.finished_at = now
            log.error_message = (log.error_message or "").strip() or "auto_closed: stale running"
        db.flush()
        print(f"closed_stuck_running={len(stuck)}")

        n_diag = clear_sync_diagnostic_logs(db)
        print(f"deleted_sync_diagnostic_logs={n_diag}")

        n_old = db.execute(
            text(
                "DELETE FROM product_connector_logs WHERE id <= :cut AND status IN ('running', 'failed')"
            ),
            {"cut": keep_logs_after_id},
        ).rowcount
        print(f"deleted_old_connector_logs={n_old or 0}")

        db.commit()

        print("\n=== USA digest regenerate ===")
        key = us_calendar_today().isoformat()
        row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == key))
        if row:
            row.feishu_sent_at = None
            row.sent_at = None
            db.commit()
        settings = get_newsletter_settings_merged(db)
        out = run_daily_newsletter_digest_job(
            db=db,
            settings=settings,
            digest_date=key,
            manual_run=True,
            regenerate=True,
        )
        print("us_digest_date", key)
        print("digest_result", out)
        row2 = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == key))
        if row2:
            print(
                "body_len",
                len(row2.body_md or ""),
                "feishu_sent_at",
                row2.feishu_sent_at,
                "has_content_analysis",
                "内容分析" in (row2.body_md or ""),
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
