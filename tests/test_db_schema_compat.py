"""ensure_schema_compatibility：PostgreSQL 与 SQLite 布尔默认值。"""
from __future__ import annotations

import backend.app.db as db_mod


def test_sql_bool_default_postgres() -> None:
    orig = db_mod.DATABASE_URL
    try:
        db_mod.DATABASE_URL = "postgresql+psycopg://u:p@127.0.0.1/db"
        assert db_mod._sql_bool_default() == "DEFAULT false"
    finally:
        db_mod.DATABASE_URL = orig


def test_sql_bool_default_sqlite() -> None:
    orig = db_mod.DATABASE_URL
    try:
        db_mod.DATABASE_URL = "sqlite:///./x.db"
        assert db_mod._sql_bool_default() == "DEFAULT 0"
    finally:
        db_mod.DATABASE_URL = orig
