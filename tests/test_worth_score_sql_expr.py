"""worth_score SQL 排序：PostgreSQL 与 SQLite 方言兼容。"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql, sqlite

from backend.app.application.article_public import _worth_score_sql_expr


def test_worth_score_sql_uses_jsonb_on_postgresql() -> None:
    sql = str(
        _worth_score_sql_expr(dialect_name="postgresql").compile(
            dialect=postgresql.dialect(),
        )
    )
    assert "json_extract" not in sql.lower()
    assert "->>" in sql or "JSONB" in sql


def test_worth_score_sql_uses_json_extract_on_sqlite() -> None:
    sql = str(
        _worth_score_sql_expr(dialect_name="sqlite").compile(
            dialect=sqlite.dialect(),
        )
    )
    assert "json_extract" in sql.lower()
