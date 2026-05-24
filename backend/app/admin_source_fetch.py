"""管理端数据源：单次同步拉取条数（热度 Top N）。"""
from __future__ import annotations

from .domain.articles import CONNECTOR_HEAT_TOP_N, CONNECTOR_SNIPPET_MAX_CHARS

CONNECTOR_FETCH_LIMIT_MIN = 1
CONNECTOR_FETCH_LIMIT_MAX = 80

# 内置源默认条数（可在后台卡片覆盖）
PRESET_FETCH_LIMIT: dict[str, int] = {
    "product_hunt": 30,
    "github": 10,
    "hacker_news": 10,
    "newsapi": 20,
    "thenewsapi": 10,
}


def default_fetch_limit_for_source(source: str) -> int:
    key = (source or "").strip().lower()
    return int(PRESET_FETCH_LIMIT.get(key, CONNECTOR_HEAT_TOP_N))


def normalize_fetch_limit(value: int | None, *, source: str | None = None) -> int:
    if value is None or int(value) <= 0:
        base = default_fetch_limit_for_source(source or "")
    else:
        base = int(value)
    return max(CONNECTOR_FETCH_LIMIT_MIN, min(CONNECTOR_FETCH_LIMIT_MAX, base))


def per_item_snippet_max(limit: int) -> int:
    n = max(1, min(CONNECTOR_FETCH_LIMIT_MAX, int(limit)))
    return min(48_000, CONNECTOR_SNIPPET_MAX_CHARS // n)
