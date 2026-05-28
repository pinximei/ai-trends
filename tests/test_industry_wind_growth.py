"""行业风向环比：前窗为 0 时不应一律显示 +100%。"""
from __future__ import annotations

from backend.app.application.industry_wind_public import _growth_pct


def test_growth_pct_zero_prior_is_none_not_100() -> None:
    assert _growth_pct(4, 0) is None
    assert _growth_pct(0, 0) is None


def test_growth_pct_normal_ratio() -> None:
    assert _growth_pct(6, 3) == 100.0
    assert _growth_pct(1, 4) == -75.0
