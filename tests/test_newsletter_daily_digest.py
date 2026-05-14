"""每日订阅摘要：解析与日历边界（无 DB / 无 LLM）。"""
from __future__ import annotations

from datetime import date

from backend.app.application.newsletter_daily_digest import (
    _parse_digest_json,
    utc_naive_bounds_for_shanghai_date,
)


def test_parse_digest_json_ok() -> None:
    raw = '{"subject": "今日 AI 精选", "body_md": "## 要点\\n\\n- 一条\\n"}'
    out = _parse_digest_json(raw)
    assert out is not None
    assert out[0] == "今日 AI 精选"
    assert "要点" in out[1]


def test_shanghai_day_bounds_cross_midnight() -> None:
    start, end = utc_naive_bounds_for_shanghai_date(date(2026, 6, 15))
    assert start < end
    delta = (end - start).total_seconds()
    assert abs(delta - 86400) < 2
