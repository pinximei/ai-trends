"""排查美东「今日」连接器入库偏少。在部署机: PYTHONPATH=/opt/aisoul python scripts/_diag_ingest_today_remote.py"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy import desc, select

from backend.app.db import SessionLocal
from backend.app.product_models import (
    Article,
    LlmUsageLog,
    ProductConnector,
    ProductConnectorLog,
    ProductSetting,
    ProductSyncDiagnosticLog,
)
from backend.app.us_content_calendar import utc_naive_bounds_for_us_date, us_calendar_today


def _diag_window(db, label: str, start: datetime, end: datetime) -> None:
    print(f"=== {label} UTC [{start}, {end}) ===\n")

    articles_created = list(
        db.scalars(
            select(Article)
            .where(Article.created_at >= start, Article.created_at < end)
            .order_by(desc(Article.id))
        ).all()
    )
    print(f"articles_created_in_window={len(articles_created)}")
    for a in articles_created[:20]:
        print(
            f"  id={a.id} status={a.status} source={a.third_party_source!r} "
            f"pub={a.published_at} created={a.created_at} title={(a.title or '')[:50]!r}"
        )
    if len(articles_created) > 20:
        print(f"  ... and {len(articles_created) - 20} more")
    print()

    articles_published = list(
        db.scalars(
            select(Article)
            .where(
                Article.status == "published",
                Article.published_at.is_not(None),
                Article.published_at >= start,
                Article.published_at < end,
            )
            .order_by(desc(Article.published_at))
        ).all()
    )
    print(f"articles_published_at_in_window={len(articles_published)} (newsletter digest uses this)")
    for a in articles_published[:15]:
        print(
            f"  id={a.id} pub={a.published_at} log={a.connector_sync_log_id} "
            f"source={a.third_party_source!r} title={(a.title or '')[:45]!r}"
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
    print(f"connector_log_runs_in_window={len(rows)}")
    total_ingested = 0
    ok_runs = err_runs = 0
    for log, cname, sk, enabled, last_sync, last_err in rows:
        total_ingested += int(log.rows_ingested or 0)
        if log.status == "ok":
            ok_runs += 1
        else:
            err_runs += 1
        err = (log.error_message or last_err or "")[:120]
        print(
            f"  log#{log.id} conn={cname!r} key={sk} enabled={enabled} "
            f"status={log.status} rows={log.rows_ingested} "
            f"started={log.started_at} err={err!r}"
        )
    print(f"sum_rows_ingested={total_ingested} ok_runs={ok_runs} err_runs={err_runs}\n")

    diag = list(
        db.scalars(
            select(ProductSyncDiagnosticLog)
            .where(ProductSyncDiagnosticLog.created_at >= start, ProductSyncDiagnosticLog.created_at < end)
            .order_by(desc(ProductSyncDiagnosticLog.id))
            .limit(500)
        ).all()
    )
    print(f"diagnostic_lines_in_window={len(diag)} (max 500)")
    step_ctr = Counter((d.level, d.step) for d in diag)
    for (level, step), n in step_ctr.most_common(25):
        print(f"  [{level}] {step}: {n}")
    print("\n--- skip / empty / error samples ---")
    shown = 0
    for d in diag:
        if d.level == "error" or d.step.startswith("skip_") or "empty" in d.step or d.step == "connector_done":
            print(f"  {d.created_at} run={d.run_id[:8]} step={d.step} src={d.source_key} | {d.message[:220]}")
            shown += 1
            if shown >= 40:
                print("  ... truncated")
                break
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
            .limit(15)
        ).all()
    )
    print(f"llm_polish_in_window={len(llm)}")
    for r in llm:
        print(
            f"  id={r.id} ok={r.success} ref={r.ref_id} err={(r.error_message or '')[:60]!r}"
        )
    print()


def main() -> None:
    db = SessionLocal()
    try:
        today = us_calendar_today()
        start, end = utc_naive_bounds_for_us_date(today)
        _diag_window(db, f"US today {today}", start, end)

        d28 = date(2026, 5, 28)
        if today != d28:
            s28, e28 = utc_naive_bounds_for_us_date(d28)
            _diag_window(db, f"US date {d28} (digest check)", s28, e28)

        # last 48h connector activity (broader than US day)
        since = datetime.utcnow() - timedelta(hours=48)
        print(f"=== connector state now (UTC now={datetime.utcnow().isoformat()}) ===\n")
        connectors = list(db.scalars(select(ProductConnector).order_by(ProductConnector.id)).all())
        print(f"connectors_total={len(connectors)} enabled={sum(1 for c in connectors if c.enabled)}")
        for c in connectors:
            print(
                f"  #{c.id} {c.name!r} key={c.admin_source_key} en={c.enabled} "
                f"last_sync={c.last_sync_at} last_err={(c.last_error or '')[:100]!r}"
            )
        print()

        recent_logs = list(
            db.scalars(
                select(ProductConnectorLog)
                .where(ProductConnectorLog.started_at >= since)
                .order_by(desc(ProductConnectorLog.started_at))
                .limit(30)
            ).all()
        )
        print(f"connector_logs_last_48h={len(recent_logs)} (show up to 30)")
        for log in recent_logs:
            print(
                f"  log#{log.id} cid={log.connector_id} status={log.status} rows={log.rows_ingested} "
                f"started={log.started_at} err={(log.error_message or '')[:80]!r}"
            )

        settings = db.get(ProductSetting, "scheduler")
        if settings and settings.value_json:
            print(f"\nscheduler_settings={json.dumps(settings.value_json, ensure_ascii=False)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
