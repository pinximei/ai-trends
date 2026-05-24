"""低产出新闻源（如 TheNewsAPI 单次仅 ~3 条）的同步策略，与整批 EOD 调度分离。"""
from __future__ import annotations

from datetime import datetime, timezone

# 上游 API 单次返回条数上限（与请求 limit 无关）
THENEWSAPI_API_MAX_ROWS = 3

# 内置低产出源：走独立微批调度，不参与美东 23:00 整批
LOW_YIELD_MICRO_BATCH_SOURCES: frozenset[str] = frozenset({"thenewsapi"})

# 手动「同步」最短间隔（秒），避免运营连点浪费配额
LOW_YIELD_MIN_INTERVAL_SECONDS: dict[str, int] = {
    "thenewsapi": 30 * 60,
}

THENEWSAPI_SYNC_INTERVAL_HOURS_DEFAULT = 2
THENEWSAPI_SYNC_INTERVAL_HOURS_MIN = 1
THENEWSAPI_SYNC_INTERVAL_HOURS_MAX = 12


def is_low_yield_micro_batch_source(source_key: str) -> bool:
    return (source_key or "").strip().lower() in LOW_YIELD_MICRO_BATCH_SOURCES


def min_interval_seconds_for_source(source_key: str) -> int | None:
    return LOW_YIELD_MIN_INTERVAL_SECONDS.get((source_key or "").strip().lower())


def default_low_yield_sync_interval_hours(source_key: str) -> int:
    _ = source_key
    return THENEWSAPI_SYNC_INTERVAL_HOURS_DEFAULT


def low_yield_batch_due_now(
    *,
    interval_hours: int,
    last_batch_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """距上次微批成功是否已满 interval_hours（与 EOD 整批无关）。"""
    h = max(THENEWSAPI_SYNC_INTERVAL_HOURS_MIN, min(THENEWSAPI_SYNC_INTERVAL_HOURS_MAX, int(interval_hours or 2)))
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
