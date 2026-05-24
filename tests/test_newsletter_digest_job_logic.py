"""每日摘要：当日已存在则不重复生成（逻辑辅助）。"""
from __future__ import annotations

from types import SimpleNamespace

from backend.app.application.newsletter_daily_digest import (
    _article_counts_from_row,
    _digest_has_content,
)


def test_digest_has_content_ready() -> None:
    row = SimpleNamespace(status="ready", body_md="## 亮点")
    assert _digest_has_content(row) is True


def test_digest_has_content_pending_empty() -> None:
    row = SimpleNamespace(status="pending", body_md="")
    assert _digest_has_content(row) is False


def test_article_counts_from_row() -> None:
    row = SimpleNamespace(article_ids_json='{"apps":[1,2],"news":[3]}')
    assert _article_counts_from_row(row) == (2, 1)
