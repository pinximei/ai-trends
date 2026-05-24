"""数据源单次拉取条数配置。"""
from __future__ import annotations

from backend.app.admin_source_fetch import normalize_fetch_limit, per_item_snippet_max


def test_normalize_fetch_limit_product_hunt_default() -> None:
    assert normalize_fetch_limit(None, source="product_hunt") == 30
    assert normalize_fetch_limit(0, source="product_hunt") == 30


def test_normalize_fetch_limit_clamps() -> None:
    assert normalize_fetch_limit(100, source="github") == 80
    assert normalize_fetch_limit(5, source="github") == 5


def test_per_item_snippet_max_scales_with_n() -> None:
    small = per_item_snippet_max(30)
    large = per_item_snippet_max(10)
    assert small < large
