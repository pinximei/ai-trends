"""连接器批量调度：间隔与开关存 product_settings_kv.scheduler（后台可改）；新建行默认 12 小时。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .product_models import ProductSetting
from .us_content_calendar import US_CONTENT_TZ, US_TIMEZONE_LABEL

logger = logging.getLogger(__name__)

SCHEDULER_KEY = "scheduler"
CONNECTOR_SCHEDULER_TZ = US_CONTENT_TZ
CONNECTOR_GATE_CHECK_MINUTES = 15
DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS = 12


def default_scheduler_json() -> dict[str, Any]:
    return {
        "connector_scheduler_enabled": True,
        "connector_sync_interval_hours": DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS,
        "last_connector_batch_at": None,
        # 启用「单独同步」的数据源上次成功时间 { source_key: iso }
        "last_custom_source_batch_at": {},
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
    h = int(base.get("connector_sync_interval_hours") or DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS)
    base["connector_sync_interval_hours"] = max(1, min(168, h))
    base["connector_scheduler_enabled"] = bool(base.get("connector_scheduler_enabled", True))
    raw_map = base.get("last_custom_source_batch_at") or base.get("last_low_yield_batch_at")
    base["last_custom_source_batch_at"] = raw_map if isinstance(raw_map, dict) else {}
    return base


def get_scheduler_settings_public(db: Session) -> dict[str, Any]:
    ensure_scheduler_settings_row(db)
    m = get_scheduler_settings_merged(db)
    interval_h = int(m["connector_sync_interval_hours"])
    ly_map = m.get("last_custom_source_batch_at") or {}
    return {
        "connector_scheduler_enabled": m["connector_scheduler_enabled"],
        "connector_sync_interval_hours": interval_h,
        "last_connector_batch_at": m.get("last_connector_batch_at"),
        "gate_interval_minutes": CONNECTOR_GATE_CHECK_MINUTES,
        "scheduler_timezone": US_TIMEZONE_LABEL,
        "sync_anchor": "interval_hours",
        "daily_slot_times_local": _connector_slot_times_label(interval_h),
        "last_custom_source_batch_at": ly_map,
        "custom_sync_note": "单独同步频率在「数据源」卡片配置；开启后不参与上方整批。",
    }


def _connector_slot_times_label(interval_h: int) -> str:
    h = max(1, min(168, int(interval_h or DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS)))
    return f"每 {h} 小时整批（{US_TIMEZONE_LABEL}，gate 每 {CONNECTOR_GATE_CHECK_MINUTES} 分钟检查）"


def connector_batch_due_now(
    *,
    interval_hours: int,
    last_batch_at: datetime | None,
    now: datetime | None = None,
    gate_window_minutes: int = CONNECTOR_GATE_CHECK_MINUTES,
) -> bool:
    """
    是否应在当前 gate 周期触发整批拉取。

    距 ``last_batch_at`` 已满 ``interval_hours`` 则触发；未单独设置同步频率的连接器参与整批。
    ``gate_window_minutes`` 仅保留参数兼容，不参与判断。
    """
    _ = gate_window_minutes
    h = max(1, min(168, int(interval_hours or DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS)))
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)
    if last_batch_at is None:
        return True
    last = last_batch_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    else:
        last = last.astimezone(timezone.utc)
    return (ref - last).total_seconds() >= h * 3600


def repair_connector_sync_interval_12h_once(db: Session) -> bool:
    """一次性：原默认 6 小时整批同步改为 12 小时，降低 LLM 调用频率。"""
    ensure_scheduler_settings_row(db)
    row = db.get(ProductSetting, SCHEDULER_KEY)
    assert row is not None
    cur = get_scheduler_settings_merged(db)
    if cur.get("connector_interval_12h_v1"):
        return False
    changed = False
    if int(cur.get("connector_sync_interval_hours") or DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS) == 6:
        cur["connector_sync_interval_hours"] = DEFAULT_CONNECTOR_SYNC_INTERVAL_HOURS
        changed = True
    cur["connector_interval_12h_v1"] = True
    row.value_json = cur
    row.updated_at = datetime.utcnow()
    db.commit()
    if changed:
        logger.info("connector batch sync interval migrated 6h -> 12h")
    return changed


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


def get_last_custom_source_batch_at(settings: dict[str, Any], source_key: str) -> datetime | None:
    sk = (source_key or "").strip().lower()
    raw_map = settings.get("last_custom_source_batch_at") or settings.get("last_low_yield_batch_at")
    if not isinstance(raw_map, dict):
        return None
    return parse_last_batch_at(raw_map.get(sk))


def set_last_custom_source_batch_at(db: Session, source_key: str, when: datetime) -> None:
    sk = (source_key or "").strip().lower()
    if not sk:
        return
    ensure_scheduler_settings_row(db)
    row = db.get(ProductSetting, SCHEDULER_KEY)
    assert row is not None
    v = dict(row.value_json or {})
    ly = dict(v.get("last_custom_source_batch_at") or v.get("last_low_yield_batch_at") or {})
    ly[sk] = when.replace(tzinfo=None).isoformat() + "Z"
    v["last_custom_source_batch_at"] = ly
    row.value_json = v
    row.updated_at = datetime.utcnow()
    db.commit()
