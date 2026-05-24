"""内容日历：美国东部（America/New_York）当日；连接器在当日最后一小时拉取。"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

US_CONTENT_TZ = ZoneInfo("America/New_York")
US_TIMEZONE_LABEL = "America/New_York（美东）"
# 美东当日 23:00–23:59 触发整批连接器拉取（与 NewsAPI 等按 US 日切分的数据源对齐）
US_END_OF_DAY_PULL_HOUR = 23


def us_calendar_today() -> date:
    return datetime.now(US_CONTENT_TZ).date()


def utc_naive_bounds_for_us_date(d: date) -> tuple[datetime, datetime]:
    """与库内 naive UTC ``published_at`` 对齐：[美东 d 日 00:00, d+1 日 00:00)。"""
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=US_CONTENT_TZ)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def us_end_of_day_pull_start_local(now: datetime | None = None) -> datetime:
    """美东当日 23:00（整批拉取窗口起点）。"""
    ref = now or datetime.now(US_CONTENT_TZ)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc).astimezone(US_CONTENT_TZ)
    else:
        ref = ref.astimezone(US_CONTENT_TZ)
    return ref.replace(hour=US_END_OF_DAY_PULL_HOUR, minute=0, second=0, microsecond=0)
