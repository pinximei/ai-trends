"""连接器批量调度：间隔与开关存 product_settings_kv.scheduler（后台可改）；新建行默认 6 小时。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .product_models import ProductSetting

SCHEDULER_KEY = "scheduler"
CONNECTOR_SCHEDULER_TZ = ZoneInfo("Asia/Shanghai")
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
        "scheduler_timezone": "Asia/Shanghai",
        "sync_anchor": "calendar_midnight",
        "daily_slot_times_local": _connector_slot_times_label(interval_h),
    }


def _connector_slot_times_label(interval_h: int) -> str:
    """本日内在上海时区按整点划分的拉取时刻（每段窗口前 15 分钟触发）。"""
    h = max(1, min(168, int(interval_h)))
    if 24 % h == 0:
        return ", ".join(f"{x:02d}:00" for x in range(0, 24, h))
    return f"自每日 00:00 起每 {h} 小时一段（当日 00:00 为起点）"


def connector_batch_slot_start_local(now: datetime | None = None, *, interval_hours: int) -> datetime:
    """当前时间所属调度段的起点（Asia/Shanghai，对齐当日 00:00）。"""
    h = max(1, min(168, int(interval_hours)))
    ref = now or datetime.now(CONNECTOR_SCHEDULER_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc).astimezone(CONNECTOR_SCHEDULER_TZ)
    else:
        ref = ref.astimezone(CONNECTOR_SCHEDULER_TZ)
    day_start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    minute_of_day = ref.hour * 60 + ref.minute
    slot_len_min = h * 60
    slot_index = min(minute_of_day // slot_len_min, (24 * 60 - 1) // slot_len_min)
    return day_start + timedelta(minutes=slot_index * slot_len_min)


def connector_batch_due_now(
    *,
    interval_hours: int,
    last_batch_at: datetime | None,
    now: datetime | None = None,
    gate_window_minutes: int = CONNECTOR_GATE_CHECK_MINUTES,
) -> bool:
    """
    是否应在当前 gate 周期触发整批拉取。

    - 以 **Asia/Shanghai 当日 00:00** 为起点切分时段（24h → 每天 00:00 一段；6h → 0/6/12/18 点）。
    - 每段仅在开头 ``gate_window_minutes`` 分钟内触发一次（与进程内 15 分钟 gate 对齐）。
    - 与「服务启动后每隔 N 小时」无关；重启不会把锚点挪到启动时刻。
    """
    h = max(1, min(168, int(interval_hours)))
    ref = now or datetime.now(CONNECTOR_SCHEDULER_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc).astimezone(CONNECTOR_SCHEDULER_TZ)
    else:
        ref = ref.astimezone(CONNECTOR_SCHEDULER_TZ)

    slot_start = connector_batch_slot_start_local(ref, interval_hours=h)
    slot_start_min = slot_start.hour * 60 + slot_start.minute
    minute_of_day = ref.hour * 60 + ref.minute
    if minute_of_day - slot_start_min >= max(1, int(gate_window_minutes)):
        return False

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
