"""连接器批量调度：间隔与开关存 product_settings_kv.scheduler（后台可改）；环境变量仅作首次默认。"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .product_models import ProductSetting

SCHEDULER_KEY = "scheduler"


def _env_default_hours() -> int:
    raw = os.getenv("AISOU_CONNECTOR_SYNC_INTERVAL_HOURS", "").strip()
    if not raw:
        return 6
    try:
        return max(1, min(168, int(raw)))
    except ValueError:
        return 6


def default_scheduler_json() -> dict[str, Any]:
    return {
        "connector_scheduler_enabled": True,
        "connector_sync_interval_hours": _env_default_hours(),
        "last_connector_batch_at": None,
    }


def ensure_scheduler_settings_row(db: Session) -> None:
    if db.get(ProductSetting, SCHEDULER_KEY):
        return
    db.add(ProductSetting(key=SCHEDULER_KEY, value_json=default_scheduler_json()))
    db.commit()


def get_scheduler_settings_merged(db: Session) -> dict[str, Any]:
    row = db.get(ProductSetting, SCHEDULER_KEY)
    base = default_scheduler_json()
    if row and isinstance(row.value_json, dict):
        base.update(row.value_json)
    h = int(base.get("connector_sync_interval_hours") or 6)
    base["connector_sync_interval_hours"] = max(1, min(168, h))
    base["connector_scheduler_enabled"] = bool(base.get("connector_scheduler_enabled", True))
    return base


def get_scheduler_settings_public(db: Session) -> dict[str, Any]:
    ensure_scheduler_settings_row(db)
    m = get_scheduler_settings_merged(db)
    return {
        "connector_scheduler_enabled": m["connector_scheduler_enabled"],
        "connector_sync_interval_hours": m["connector_sync_interval_hours"],
        "last_connector_batch_at": m.get("last_connector_batch_at"),
        "gate_interval_minutes": 15,
        "env_default_hours_hint": _env_default_hours(),
    }


def save_scheduler_settings_patch(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_scheduler_settings_row(db)
    row = db.get(ProductSetting, SCHEDULER_KEY)
    assert row is not None
    cur = get_scheduler_settings_merged(db)
    if "connector_scheduler_enabled" in patch and patch["connector_scheduler_enabled"] is not None:
        cur["connector_scheduler_enabled"] = bool(patch["connector_scheduler_enabled"])
    if "connector_sync_interval_hours" in patch and patch["connector_sync_interval_hours"] is not None:
        try:
            h = int(patch["connector_sync_interval_hours"])
            cur["connector_sync_interval_hours"] = max(1, min(168, h))
        except (TypeError, ValueError):
            pass
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    return get_scheduler_settings_public(db)


def parse_last_batch_at(raw: Any) -> datetime | None:
    if raw is None or raw is False:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("Z", "")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def set_last_connector_batch_at(db: Session, when: datetime) -> None:
    ensure_scheduler_settings_row(db)
    row = db.get(ProductSetting, SCHEDULER_KEY)
    assert row is not None
    v = dict(row.value_json or {})
    v["last_connector_batch_at"] = when.replace(tzinfo=None).isoformat() + "Z"
    row.value_json = v
    row.updated_at = datetime.utcnow()
    db.commit()
