"""数据源同步策略：整批（美东 EOD）与单源自定义间隔。"""
from __future__ import annotations

from datetime import datetime, timezone

# TheNewsAPI 上游单次返回条数上限（与请求 limit 无关，仅作说明）
THENEWSAPI_API_MAX_ROWS = 3

CUSTOM_SYNC_INTERVAL_HOURS_DEFAULT = 2
CUSTOM_SYNC_INTERVAL_HOURS_MIN = 1
CUSTOM_SYNC_INTERVAL_HOURS_MAX = 168

# 启用「单独同步」后，手动点「同步」的最短间隔（秒）
CUSTOM_SYNC_MIN_INTERVAL_SECONDS = 30 * 60


def clamp_custom_sync_interval_hours(value: int | None) -> int:
    try:
        h = int(value if value is not None else CUSTOM_SYNC_INTERVAL_HOURS_DEFAULT)
    except (TypeError, ValueError):
        h = CUSTOM_SYNC_INTERVAL_HOURS_DEFAULT
    return max(CUSTOM_SYNC_INTERVAL_HOURS_MIN, min(CUSTOM_SYNC_INTERVAL_HOURS_MAX, h))


def custom_source_batch_due_now(
    *,
    interval_hours: int,
    last_batch_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """单源自定义调度：距上次成功是否已满 interval_hours。"""
    h = clamp_custom_sync_interval_hours(interval_hours)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    if last_batch_at is None:
        return True
    last = last_batch_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    else:
        last = last.astimezone(timezone.utc)
    return (ref - last).total_seconds() >= h * 3600
