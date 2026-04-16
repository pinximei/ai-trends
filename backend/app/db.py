from pathlib import Path
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_MODE = os.getenv("AISOU_DB_MODE", "test").lower()
DB_URL_TEST = os.getenv("AISOU_DB_URL_TEST", f"sqlite:///{(DATA_DIR / 'app_test.db').as_posix()}")
DB_URL_PROD = os.getenv("AISOU_DB_URL_PROD", f"sqlite:///{(DATA_DIR / 'app_prod.db').as_posix()}")
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


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _has_column(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def ensure_schema_compatibility() -> None:
    """Lightweight migration for sqlite dev mode."""
    with engine.begin() as conn:
        if _has_column(conn, "admin_users", "id"):
            if not _has_column(conn, "admin_users", "failed_attempts"):
                conn.execute(text("ALTER TABLE admin_users ADD COLUMN failed_attempts INTEGER DEFAULT 0"))
            if not _has_column(conn, "admin_users", "locked_until"):
                conn.execute(text("ALTER TABLE admin_users ADD COLUMN locked_until DATETIME"))


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
