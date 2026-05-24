"""连接器批量调度：间隔与开关存 product_settings_kv.scheduler（后台可改）；新建行默认 6 小时。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .product_models import ProductSetting
from .us_content_calendar import (
    US_CONTENT_TZ,
    US_END_OF_DAY_PULL_HOUR,
    US_TIMEZONE_LABEL,
    us_end_of_day_pull_start_local,
)

SCHEDULER_KEY = "scheduler"
CONNECTOR_SCHEDULER_TZ = US_CONTENT_TZ
CONNECTOR_GATE_CHECK_MINUTES = 15


def default_scheduler_json() -> dict[str, Any]:
    return {
        "connector_scheduler_enabled": True,
        "connector_sync_interval_hours": 6,
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
    interval_h = int(m["connector_sync_interval_hours"])
    return {
        "connector_scheduler_enabled": m["connector_scheduler_enabled"],
        "connector_sync_interval_hours": interval_h,
        "last_connector_batch_at": m.get("last_connector_batch_at"),
        "gate_interval_minutes": CONNECTOR_GATE_CHECK_MINUTES,
        "scheduler_timezone": US_TIMEZONE_LABEL,
        "sync_anchor": "us_eod_last_hour",
        "daily_slot_times_local": _connector_slot_times_label(interval_h),
    }


def _connector_slot_times_label(interval_h: int) -> str:
    """美东当日最后一小时（23:00–24:00）整批拉取；间隔小时数仅作展示保留。"""
    _ = interval_h
    return f"每日 {US_END_OF_DAY_PULL_HOUR:02d}:00–24:00（{US_TIMEZONE_LABEL}，gate 每 {CONNECTOR_GATE_CHECK_MINUTES} 分钟检查）"


def connector_batch_due_now(
    *,
    interval_hours: int,
    last_batch_at: datetime | None,
    now: datetime | None = None,
    gate_window_minutes: int = CONNECTOR_GATE_CHECK_MINUTES,
) -> bool:
    """
    是否应在当前 gate 周期触发整批拉取。

    仅在 **美东当日 23:00–23:59** 触发（最后一小时拉取，便于对齐 US 日切数据源）。
    每个美东日历日最多成功触发一次（``last_batch_at`` 早于当日 23:00 美东）。
    ``interval_hours`` 保留配置项，不再用于切分拉取时段。
    """
    _ = interval_hours, gate_window_minutes
    ref = now or datetime.now(CONNECTOR_SCHEDULER_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc).astimezone(CONNECTOR_SCHEDULER_TZ)
    else:
        ref = ref.astimezone(CONNECTOR_SCHEDULER_TZ)

    if ref.hour != US_END_OF_DAY_PULL_HOUR:
        return False

    slot_start = us_end_of_day_pull_start_local(ref)
    if last_batch_at is None:
        return True

    last = last_batch_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    last_local = last.astimezone(CONNECTOR_SCHEDULER_TZ)
    return last_local < slot_start


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
