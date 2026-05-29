"""连接器同步：统计聚合（管理端图表）。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..product_models import Article, LlmUsageLog, ProductConnector, ProductConnectorLog


def _utc_day(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.date().isoformat()


def connector_stats_overview(db: Session, *, days: int = 14) -> dict[str, Any]:
    days = max(1, min(int(days), 90))
    since = datetime.utcnow() - timedelta(days=days)

    connectors = {c.id: c for c in db.scalars(select(ProductConnector)).all()}
    logs = list(
        db.scalars(
            select(ProductConnectorLog).where(ProductConnectorLog.started_at >= since).order_by(ProductConnectorLog.started_at)
        ).all()
    )

    daily: dict[str, dict[str, int]] = defaultdict(
        lambda: {"sync_runs": 0, "rows_ingested": 0, "errors": 0, "articles_created": 0}
    )
    by_connector: dict[int, dict[str, Any]] = {}
    total_runs = 0
    ok_runs = 0
    error_runs = 0
    rows_total = 0

    for log in logs:
        day = _utc_day(log.started_at)
        total_runs += 1
        daily[day]["sync_runs"] += 1
        ing = int(log.rows_ingested or 0)
        rows_total += ing
        daily[day]["rows_ingested"] += ing
        is_err = (log.status or "") == "error"
        if is_err:
            error_runs += 1
            daily[day]["errors"] += 1
        elif (log.status or "") == "ok":
            ok_runs += 1

        cid = int(log.connector_id)
        bucket = by_connector.setdefault(
            cid,
            {
                "connector_id": cid,
                "name": (connectors.get(cid).name if connectors.get(cid) else f"#{cid}"),
                "admin_source_key": (connectors.get(cid).admin_source_key if connectors.get(cid) else None),
                "enabled": bool(connectors.get(cid).enabled) if connectors.get(cid) else False,
                "sync_runs": 0,
                "ok_runs": 0,
                "error_runs": 0,
                "rows_ingested": 0,
                "last_sync_at": None,
                "last_error": None,
            },
        )
        bucket["sync_runs"] += 1
        bucket["rows_ingested"] += ing
        if is_err:
            bucket["error_runs"] += 1
            if log.error_message:
                bucket["last_error"] = (log.error_message or "")[:240]
        elif (log.status or "") == "ok":
            bucket["ok_runs"] += 1
        ts = log.started_at.isoformat() + "Z"
        if not bucket["last_sync_at"] or ts > bucket["last_sync_at"]:
            bucket["last_sync_at"] = ts

    # 入库文章（按同步日志关联连接器）
    log_to_connector = {int(l.id): int(l.connector_id) for l in logs}
    articles = list(
        db.scalars(
            select(Article).where(
                Article.created_at >= since,
                Article.connector_sync_log_id.isnot(None),
            )
        ).all()
    )
    articles_by_connector: dict[int, int] = defaultdict(int)
    articles_by_source: dict[str, int] = defaultdict(int)
    for a in articles:
        lid = getattr(a, "connector_sync_log_id", None)
        cid = log_to_connector.get(int(lid)) if lid else None
        if cid:
            articles_by_connector[cid] += 1
            c = connectors.get(cid)
            sk = (c.admin_source_key if c else None) or "unknown"
            articles_by_source[sk] += 1
        day = _utc_day(a.created_at)
        daily[day]["articles_created"] += 1

    for cid, n in articles_by_connector.items():
        if cid in by_connector:
            by_connector[cid]["articles_created"] = n
        else:
            c = connectors.get(cid)
            by_connector[cid] = {
                "connector_id": cid,
                "name": c.name if c else f"#{cid}",
                "admin_source_key": c.admin_source_key if c else None,
                "enabled": bool(c.enabled) if c else False,
                "sync_runs": 0,
                "ok_runs": 0,
                "error_runs": 0,
                "rows_ingested": 0,
                "articles_created": n,
                "last_sync_at": c.last_sync_at.isoformat() + "Z" if c and c.last_sync_at else None,
                "last_error": (c.last_error or "")[:240] if c and c.last_error else None,
            }

    llm_rows = list(
        db.scalars(
            select(LlmUsageLog).where(
                LlmUsageLog.created_at >= since,
                LlmUsageLog.scenario == "article_ingest_polish",
            )
        ).all()
    )
    llm_ok = sum(1 for r in llm_rows if r.success)
    llm_fail = len(llm_rows) - llm_ok
    llm_in = sum(int(r.input_tokens or 0) for r in llm_rows)
    llm_out = sum(int(r.output_tokens or 0) for r in llm_rows)

    # 按日填充空缺（图表连续）
    series: list[dict[str, Any]] = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).date().isoformat()
        row = daily.get(d) or {"sync_runs": 0, "rows_ingested": 0, "errors": 0, "articles_created": 0}
        series.append({"date": d, **row})

    connector_list = sorted(
        by_connector.values(),
        key=lambda x: (-int(x.get("rows_ingested") or 0), -int(x.get("sync_runs") or 0)),
    )
    source_list = [
        {"source_key": k, "articles_created": v}
        for k, v in sorted(articles_by_source.items(), key=lambda kv: -kv[1])
    ]

    return {
        "days": days,
        "since": since.isoformat() + "Z",
        "summary": {
            "sync_runs": total_runs,
            "ok_runs": ok_runs,
            "error_runs": error_runs,
            "success_rate": round(ok_runs / total_runs, 3) if total_runs else None,
            "rows_ingested": rows_total,
            "articles_created": len(articles),
            "connectors_total": len(connectors),
            "connectors_enabled": sum(1 for c in connectors.values() if c.enabled),
            "llm_polish_calls": len(llm_rows),
            "llm_polish_ok": llm_ok,
            "llm_polish_fail": llm_fail,
            "llm_input_tokens": llm_in,
            "llm_output_tokens": llm_out,
        },
        "daily": series,
        "by_connector": connector_list,
        "by_source": source_list,
    }
