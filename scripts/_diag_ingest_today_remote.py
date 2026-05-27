"""排查美东「今日」连接器入库偏少。在部署机: PYTHONPATH=/opt/aisoul python scripts/_diag_ingest_today_remote.py"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from sqlalchemy import desc, func, select

from backend.app.db import SessionLocal
from backend.app.models import AdminSourceConfig
from backend.app.product_models import (
    Article,
    LlmUsageLog,
    ProductConnector,
    ProductConnectorLog,
    ProductSetting,
    ProductSyncDiagnosticLog,
)
from backend.app.us_content_calendar import utc_naive_bounds_for_us_date, us_calendar_today


def main() -> None:
    db = SessionLocal()
    try:
        today = us_calendar_today()
        start, end = utc_naive_bounds_for_us_date(today)
        print(f"=== ingest diagnostic US date {today} UTC [{start}, {end}) ===\n")

        articles = list(
            db.scalars(
                select(Article)
                .where(Article.created_at >= start, Article.created_at < end)
                .order_by(desc(Article.id))
            ).all()
        )
        print(f"articles_created_today={len(articles)}")
        for a in articles:
            print(
                f"  id={a.id} status={a.status} source={a.third_party_source!r} "
                f"title={(a.title or '')[:55]!r} created={a.created_at}"
            )
        print()

        rows = db.execute(
            select(
                ProductConnectorLog,
                ProductConnector.name,
                ProductConnector.admin_source_key,
                ProductConnector.enabled,
                ProductConnector.last_sync_at,
                ProductConnector.last_error,
            )
            .join(ProductConnector, ProductConnector.id == ProductConnectorLog.connector_id)
            .where(ProductConnectorLog.started_at >= start, ProductConnectorLog.started_at < end)
            .order_by(desc(ProductConnectorLog.started_at))
        ).all()
        print(f"connector_log_runs_today={len(rows)}")
        total_ingested = 0
        for log, cname, sk, enabled, last_sync, last_err in rows:
            total_ingested += int(log.rows_ingested or 0)
            err = (log.error_message or last_err or "")[:120]
            print(
                f"  log#{log.id} conn={cname!r} key={sk} enabled={enabled} "
                f"status={log.status} rows={log.rows_ingested} "
                f"started={log.started_at} err={err!r}"
            )
        print(f"sum_rows_ingested={total_ingested}\n")

        connectors = list(db.scalars(select(ProductConnector).order_by(ProductConnector.id)).all())
        print(f"connectors_total={len(connectors)} enabled={sum(1 for c in connectors if c.enabled)}")
        for c in connectors:
            print(
                f"  #{c.id} {c.name!r} key={c.admin_source_key} en={c.enabled} "
                f"last_sync={c.last_sync_at} last_err={(c.last_error or '')[:80]!r}"
            )
        print()

        diag = list(
            db.scalars(
                select(ProductSyncDiagnosticLog)
                .where(ProductSyncDiagnosticLog.created_at >= start, ProductSyncDiagnosticLog.created_at < end)
                .order_by(desc(ProductSyncDiagnosticLog.id))
                .limit(500)
            ).all()
        )
        print(f"diagnostic_lines_today={len(diag)} (max 500 recent)")
        step_ctr = Counter((d.level, d.step) for d in diag)
        for (level, step), n in step_ctr.most_common(30):
            print(f"  [{level}] {step}: {n}")
        print("\n--- recent error/diagnostic samples ---")
        for d in diag:
            if d.level == "error" or d.step.startswith("skip_") or "empty" in d.step:
                print(f"  {d.created_at} run={d.run_id[:8]} step={d.step} src={d.source_key} | {d.message[:200]}")
        print()

        llm = list(
            db.scalars(
                select(LlmUsageLog)
                .where(
                    LlmUsageLog.scenario == "article_ingest_polish",
                    LlmUsageLog.created_at >= start,
                    LlmUsageLog.created_at < end,
                )
                .order_by(desc(LlmUsageLog.id))
                .limit(20)
            ).all()
        )
        print(f"llm_polish_today={len(llm)} (show up to 20)")
        for r in llm:
            print(
                f"  id={r.id} ok={r.success} in={r.input_tokens} out={r.output_tokens} "
                f"ref={r.ref_id} err={(r.error_message or '')[:60]!r}"
            )

        settings = db.get(ProductSetting, "scheduler")
        if settings and settings.value_json:
            print(f"\nscheduler_settings={json.dumps(settings.value_json, ensure_ascii=False)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
