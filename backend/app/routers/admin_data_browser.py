"""受控库表浏览：仅允许白名单内的 ORM 表，支持时间范围与维度筛选。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

from ..admin_auth import require_role
from ..db import get_db
from ..models import AdminSession
from ..product_models import (
    AnomalyEvent,
    Article,
    CmsPage,
    HotSnapshot,
    Industry,
    Inspiration,
    InspirationVersion,
    LlmUsageLog,
    MetricDefinition,
    MetricPoint,
    ProductConnector,
    ProductConnectorLog,
    ProductSetting,
    Segment,
)

router = APIRouter(prefix="/api/admin/v1/data", tags=["admin-data-browser"])


def ok(data):
    return {"code": 0, "message": "ok", "data": data}


def _parse_iso_dt(s: str | None) -> datetime | None:
    if not s or not str(s).strip():
        return None
    t = str(s).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        raise HTTPException(400, "invalid datetime") from None


def _serialize_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat() + "Z"
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, float):
        return v
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v
    return str(v)


def _row_dict(obj) -> dict[str, Any]:
    out: dict[str, Any] = {}
    state = sa_inspect(obj)
    for attr in state.mapper.column_attrs:
        name = attr.key
        val = getattr(obj, name)
        if name in ("body", "body_md", "summary", "payload_json", "detail_json", "context_snapshot_json", "config_json", "value_json"):
            if isinstance(val, str) and len(val) > 2000:
                out[name] = val[:2000] + "…(truncated)"
                continue
            if isinstance(val, (dict, list)):
                j = _serialize_val(val)
                s = str(j)
                if len(s) > 2000:
                    out[name] = s[:2000] + "…(truncated)"
                else:
                    out[name] = j
                continue
        out[name] = _serialize_val(val)
    return out


_TABLES: dict[str, dict[str, Any]] = {
    "metric_points": {
        "label": "指标数据点",
        "model": MetricPoint,
        "time_attr": "bucket_start",
        "segment": True,
        "metric": True,
    },
    "metric_definitions": {
        "label": "指标定义",
        "model": MetricDefinition,
        "time_attr": None,
        "segment": True,
    },
    "articles": {
        "label": "文章",
        "model": Article,
        "time_attr": "updated_at",
        "segment": True,
        "status": True,
    },
    "hot_snapshots": {
        "label": "热门快照",
        "model": HotSnapshot,
        "time_attr": "generated_at",
    },
    "anomaly_events": {
        "label": "异动事件",
        "model": AnomalyEvent,
        "time_attr": "created_at",
        "segment": True,
        "metric": True,
    },
    "segments": {
        "label": "板块",
        "model": Segment,
        "time_attr": None,
    },
    "industries": {
        "label": "行业",
        "model": Industry,
        "time_attr": None,
    },
    "inspirations": {
        "label": "灵感",
        "model": Inspiration,
        "time_attr": None,
        "segment": True,
    },
    "inspiration_versions": {
        "label": "灵感版本",
        "model": InspirationVersion,
        "time_attr": "created_at",
    },
    "llm_usage_logs": {
        "label": "大模型用量",
        "model": LlmUsageLog,
        "time_attr": "created_at",
    },
    "product_connectors": {
        "label": "连接器",
        "model": ProductConnector,
        "time_attr": "created_at",
    },
    "connector_logs": {
        "label": "连接器同步日志",
        "model": ProductConnectorLog,
        "time_attr": "started_at",
    },
    "cms_pages": {
        "label": "CMS 页面",
        "model": CmsPage,
        "time_attr": "updated_at",
    },
    "settings_kv": {
        "label": "产品键值配置",
        "model": ProductSetting,
        "time_attr": "updated_at",
    },
}


@router.get("/tables")
def list_data_tables(session: AdminSession = Depends(require_role("viewer"))):
    items = []
    for key, cfg in _TABLES.items():
        dims = []
        if cfg.get("segment"):
            dims.append({"name": "segment_id", "label": "板块 ID"})
        if cfg.get("metric"):
            dims.append({"name": "metric_id", "label": "指标 ID"})
        if cfg.get("status"):
            dims.append({"name": "status", "label": "状态（精确）"})
        items.append(
            {
                "key": key,
                "label": cfg["label"],
                "has_time": cfg.get("time_attr") is not None,
                "time_hint": cfg.get("time_attr"),
                "dimensions": dims,
            }
        )
    return ok(items)


@router.get("/rows")
def browse_rows(
    table: str = Query(..., description="白名单表 key"),
    since: str | None = Query(None),
    until: str | None = Query(None),
    segment_id: int | None = Query(None),
    metric_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=100_000),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    if table not in _TABLES:
        raise HTTPException(400, "unknown table")
    cfg = _TABLES[table]
    model = cfg["model"]
    q: Select = select(model)
    t0 = _parse_iso_dt(since)
    t1 = _parse_iso_dt(until)
    time_attr: str | None = cfg.get("time_attr")
    if time_attr and (t0 or t1):
        col = getattr(model, time_attr)
        if t0 is not None:
            q = q.where(col >= t0)
        if t1 is not None:
            q = q.where(col <= t1)

    if cfg.get("segment") and segment_id is not None:
        if hasattr(model, "segment_id"):
            q = q.where(model.segment_id == segment_id)
    if cfg.get("metric") and metric_id is not None:
        if hasattr(model, "metric_id"):
            q = q.where(model.metric_id == metric_id)
    if cfg.get("status") and status is not None and str(status).strip():
        if hasattr(model, "status"):
            q = q.where(model.status == str(status).strip())

    pk_cols = sa_inspect(model).mapper.primary_key
    order_col = getattr(model, time_attr) if time_attr and hasattr(model, time_attr) else pk_cols[0]
    q = q.order_by(order_col.desc()).offset(offset).limit(limit)

    rows = db.scalars(q).all()
    out_rows = [_row_dict(r) for r in rows]
    columns = sorted(out_rows[0].keys()) if out_rows else [c.key for c in sa_inspect(model).mapper.column_attrs]

    return ok({"table": table, "columns": columns, "rows": out_rows, "limit": limit, "offset": offset, "count": len(out_rows)})


@router.get("/rows/count")
def browse_rows_count(
    table: str = Query(...),
    since: str | None = Query(None),
    until: str | None = Query(None),
    segment_id: int | None = Query(None),
    metric_id: int | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    if table not in _TABLES:
        raise HTTPException(400, "unknown table")
    cfg = _TABLES[table]
    model = cfg["model"]
    q = select(func.count()).select_from(model)
    t0 = _parse_iso_dt(since)
    t1 = _parse_iso_dt(until)
    time_attr: str | None = cfg.get("time_attr")
    if time_attr and (t0 or t1):
        col = getattr(model, time_attr)
        if t0 is not None:
            q = q.where(col >= t0)
        if t1 is not None:
            q = q.where(col <= t1)
    if cfg.get("segment") and segment_id is not None and hasattr(model, "segment_id"):
        q = q.where(model.segment_id == segment_id)
    if cfg.get("metric") and metric_id is not None and hasattr(model, "metric_id"):
        q = q.where(model.metric_id == metric_id)
    if cfg.get("status") and status is not None and str(status).strip() and hasattr(model, "status"):
        q = q.where(model.status == str(status).strip())

    total = db.scalar(q) or 0
    return ok({"table": table, "total": int(total)})
