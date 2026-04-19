from pathlib import Path
import json
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 默认 PostgreSQL（本地可用 docker compose up -d）。不再默认 SQLite。
_DEFAULT_PG = "postgresql+psycopg://aisoul:aisoul@127.0.0.1:5432/aisoul"

DB_MODE = os.getenv("AISOU_DB_MODE", "test").lower()
DB_URL_TEST = os.getenv("AISOU_DB_URL_TEST", _DEFAULT_PG)
DB_URL_PROD = os.getenv("AISOU_DB_URL_PROD", _DEFAULT_PG)
DB_URL = os.getenv("AISOU_DATABASE_URL")
if DB_URL:
    DATABASE_URL = DB_URL
    DB_MODE = "custom"
elif DB_MODE == "prod":
    DATABASE_URL = DB_URL_PROD
else:
    DB_MODE = "test"
    DATABASE_URL = DB_URL_TEST


class Base(DeclarativeBase):
    pass


_connect_args = {}
_engine_kwargs: dict = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
    _engine_kwargs.pop("pool_pre_ping", None)
engine = create_engine(DATABASE_URL, connect_args=_connect_args, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _column_names(conn, table: str) -> set[str]:
    insp = inspect(conn)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def ensure_schema_compatibility() -> None:
    """轻量兼容迁移（PostgreSQL / 可选 SQLite）。"""
    with engine.begin() as conn:
        cols = _column_names(conn, "admin_users")
        if cols:
            if "failed_attempts" not in cols:
                conn.execute(text("ALTER TABLE admin_users ADD COLUMN failed_attempts INTEGER DEFAULT 0"))
            if "locked_until" not in cols:
                conn.execute(text("ALTER TABLE admin_users ADD COLUMN locked_until TIMESTAMP"))
        cols = _column_names(conn, "admin_source_configs")
        if cols:
            if "scope_label" not in cols:
                conn.execute(text("ALTER TABLE admin_source_configs ADD COLUMN scope_label VARCHAR(128) DEFAULT ''"))
            if "scope_labels_json" not in cols:
                conn.execute(text("ALTER TABLE admin_source_configs ADD COLUMN scope_labels_json TEXT DEFAULT '[]'"))
                rows = conn.execute(text("SELECT id, COALESCE(scope_label, '') AS sl FROM admin_source_configs")).fetchall()
                for rid, sl in rows:
                    sl = (sl or "").strip()
                    arr = json.dumps([sl], ensure_ascii=False) if sl else "[]"
                    conn.execute(
                        text("UPDATE admin_source_configs SET scope_labels_json = :j WHERE id = :id"),
                        {"j": arr, "id": rid},
                    )
        cols = _column_names(conn, "product_connectors")
        if cols and "admin_source_key" not in cols:
            conn.execute(text("ALTER TABLE product_connectors ADD COLUMN admin_source_key VARCHAR(64)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _mask_db_url(url: str) -> str:
    try:
        parsed = make_url(url)
    except Exception:
        return "***"
    if parsed.password is not None:
        parsed = parsed.set(password="****")
    if parsed.username is not None:
        parsed = parsed.set(username="***")
    return parsed.render_as_string(hide_password=False)


def get_db_runtime_info() -> dict:
    return {
        "mode": DB_MODE,
        "database_url": _mask_db_url(DATABASE_URL),
        "test_url": _mask_db_url(DB_URL_TEST),
        "prod_url": _mask_db_url(DB_URL_PROD),
    }
