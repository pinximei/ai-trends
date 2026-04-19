"""异动检测：稳健 Z + MAD（可调参数存 ProductSetting anomaly）。"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .product_models import AnomalyEvent, MetricDefinition, MetricPoint, ProductSetting


def _mad(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    med = statistics.median(xs)
    devs = [abs(x - med) for x in xs]
    return statistics.median(devs) or 1e-9


def _robust_z(x: float, baseline: list[float]) -> float:
    if not baseline:
        return 0.0
    med = statistics.median(baseline)
    mad = _mad(baseline)
    return 0.6745 * (x - med) / mad


def get_anomaly_settings(db: Session) -> dict:
    row = db.get(ProductSetting, "anomaly")
    if row and row.value_json:
        return row.value_json
    return {
        "short_window_days": 7,
        "baseline_days": 28,
        "l1_z": 3.0,
        "l2_z": 4.0,
        "cooldown_hours": 48,
        "board_k": 2,
    }


def save_anomaly_settings(db: Session, data: dict) -> dict:
    row = db.get(ProductSetting, "anomaly")
    if not row:
        row = ProductSetting(key="anomaly", value_json={})
        db.add(row)
    row.value_json = {**get_anomaly_settings(db), **data}
    row.updated_at = datetime.utcnow()
    db.commit()
    return row.value_json


def compute_anomalies(db: Session) -> int:
    """扫描指标点，写入异动事件；返回新增条数。"""
    cfg = get_anomaly_settings(db)
    short_d = int(cfg.get("short_window_days", 7))
    base_d = int(cfg.get("baseline_days", 28))
    l1 = float(cfg.get("l1_z", 3.0))
    l2 = float(cfg.get("l2_z", 4.0))
    cooldown_h = float(cfg.get("cooldown_hours", 48))

    now = datetime.utcnow()
    short_since = now - timedelta(days=short_d)
    base_end = short_since
    base_since = base_end - timedelta(days=base_d)

    metrics = db.scalars(select(MetricDefinition)).all()
    created = 0
    for m in metrics:
        pts = db.scalars(
            select(MetricPoint)
            .where(MetricPoint.metric_id == m.id)
            .where(MetricPoint.bucket_start >= base_since)
            .order_by(MetricPoint.bucket_start)
        ).all()
        if len(pts) < 5:
            continue
        short_pts = [p for p in pts if p.bucket_start >= short_since]
        base_pts = [p for p in pts if p.bucket_start < short_since]
        if not short_pts or not base_pts:
            continue
        baseline_vals = [p.value for p in base_pts]
        last = short_pts[-1].value
        z = abs(_robust_z(last, baseline_vals))
        level = 0
        if z >= l2:
            level = 2
        elif z >= l1:
            level = 1
        if level == 0:
            continue
        seg_id = short_pts[-1].segment_id
        recent = db.scalar(
            select(AnomalyEvent)
            .where(AnomalyEvent.metric_id == m.id, AnomalyEvent.segment_id == seg_id)
            .order_by(desc(AnomalyEvent.created_at))
            .limit(1)
        )
        if recent and (now - recent.created_at).total_seconds() < cooldown_h * 3600:
            continue

        ev = AnomalyEvent(
            segment_id=seg_id,
            metric_id=m.id,
            score=z,
            level=level,
            detail_json={"metric_key": m.key, "last_value": last, "z": z},
        )
        db.add(ev)
        created += 1
    db.commit()
    return created


def list_anomaly_events(db: Session, limit: int = 100):
    return db.scalars(select(AnomalyEvent).order_by(desc(AnomalyEvent.created_at)).limit(limit)).all()


def mark_anomaly_read(db: Session, event_id: int) -> bool:
    ev = db.get(AnomalyEvent, event_id)
    if not ev:
        return False
    ev.read_at = datetime.utcnow()
    db.commit()
    return True
