from pathlib import Path
import json
import os


def _load_backend_dotenv() -> None:
    """启动时加载 backend/.env（无 python-dotenv 依赖）；仅当环境变量尚未设置时写入 os.environ。

    建议长期保留该文件：生产密钥、数据库连接等仍可只放在 .env / systemd EnvironmentFile 中；
    部分可后台管理的项（如 LLM、邮件 SMTP）若库内尚未配置，启动时会尝试把 .env 里已有变量一次性写入库，
    文件本身可继续作为凭据备份与运维单一来源，无需删除。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        raw_text = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_backend_dotenv()


def _migrate_aisou_env_aliases() -> None:
    """兼容已废弃的 AISOU_* 前缀（backend/.env 或 systemd 仍可能使用）。"""
    for new_key, old_key in (
        ("AITRENDS_DATABASE_URL", "AISOU_DATABASE_URL"),
        ("AITRENDS_DB_MODE", "AISOU_DB_MODE"),
        ("AITRENDS_DB_URL_TEST", "AISOU_DB_URL_TEST"),
        ("AITRENDS_DB_URL_PROD", "AISOU_DB_URL_PROD"),
        ("AITRENDS_LLM_API_KEY", "AISOU_LLM_API_KEY"),
        ("AITRENDS_LLM_BASE_URL", "AISOU_LLM_BASE_URL"),
        ("AITRENDS_LLM_MODEL", "AISOU_LLM_MODEL"),
    ):
        if not (os.getenv(new_key) or "").strip() and (os.getenv(old_key) or "").strip():
            os.environ[new_key] = os.environ[old_key]


_migrate_aisou_env_aliases()

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 默认 PostgreSQL（本地可用 docker compose up -d）。不再默认 SQLite。
_DEFAULT_PG = "postgresql+psycopg://aitrends:aitrends@127.0.0.1:5432/aitrends"

DB_MODE = os.getenv("AITRENDS_DB_MODE", "test").lower()
DB_URL_TEST = os.getenv("AITRENDS_DB_URL_TEST", _DEFAULT_PG)
DB_URL_PROD = os.getenv("AITRENDS_DB_URL_PROD", _DEFAULT_PG)
DB_URL = os.getenv("AITRENDS_DATABASE_URL")
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
            if "preset_label" not in cols:
                conn.execute(text("ALTER TABLE admin_source_configs ADD COLUMN preset_label VARCHAR(128) DEFAULT ''"))
            if "content_role" not in cols:
                conn.execute(text("ALTER TABLE admin_source_configs ADD COLUMN content_role VARCHAR(32) DEFAULT ''"))
            if "app_secret_masked" not in cols:
                conn.execute(text("ALTER TABLE admin_source_configs ADD COLUMN app_secret_masked VARCHAR(128) DEFAULT ''"))
        cols = _column_names(conn, "product_connectors")
        if cols and "admin_source_key" not in cols:
            conn.execute(text("ALTER TABLE product_connectors ADD COLUMN admin_source_key VARCHAR(64)"))
        cols = _column_names(conn, "product_articles")
        if cols:
            if "ingest_fingerprint" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN ingest_fingerprint VARCHAR(40)"))
            if "ai_categories_json" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN ai_categories_json TEXT DEFAULT '[]'"))
            if "feed_kind" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN feed_kind VARCHAR(8)"))
            if "ai_tabs_json" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN ai_tabs_json TEXT DEFAULT '[]'"))
            if "source_original_url" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN source_original_url VARCHAR(2048)"))
            if "connector_sync_log_id" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN connector_sync_log_id INTEGER"))
            if "source_external_id" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN source_external_id VARCHAR(512)"))
            if "heat_score" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN heat_score DOUBLE PRECISION DEFAULT 0"))
            if "engagement_stars_total" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN engagement_stars_total INTEGER"))
            if "engagement_stars_today" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN engagement_stars_today INTEGER"))
            if "cover_image_url" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN cover_image_url VARCHAR(2048)"))
            if "replication_tier" not in cols:
                conn.execute(text("ALTER TABLE product_articles ADD COLUMN replication_tier VARCHAR(4)"))
        if not _column_names(conn, "product_sync_diagnostic_logs"):
            conn.execute(
                text(
                    "CREATE TABLE product_sync_diagnostic_logs ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "
                    "run_id VARCHAR(32) NOT NULL, "
                    "created_at TIMESTAMP, "
                    "level VARCHAR(16) DEFAULT 'info', "
                    "step VARCHAR(64) DEFAULT 'log', "
                    "message TEXT, "
                    "connector_id INTEGER, "
                    "source_key VARCHAR(64)"
                    ")"
                )
                if DATABASE_URL.startswith("sqlite")
                else text(
                    "CREATE TABLE product_sync_diagnostic_logs ("
                    "id SERIAL PRIMARY KEY, "
                    "run_id VARCHAR(32) NOT NULL, "
                    "created_at TIMESTAMP, "
                    "level VARCHAR(16) DEFAULT 'info', "
                    "step VARCHAR(64) DEFAULT 'log', "
                    "message TEXT, "
                    "connector_id INTEGER, "
                    "source_key VARCHAR(64)"
                    ")"
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sync_diag_run_id ON product_sync_diagnostic_logs (run_id)"))
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_sync_diag_created_at ON product_sync_diagnostic_logs (created_at)")
            )
        cols = _column_names(conn, "product_software_downloads")
        if cols:
            if "artifact_rel_path" not in cols:
                conn.execute(text("ALTER TABLE product_software_downloads ADD COLUMN artifact_rel_path VARCHAR(512)"))
            if "artifact_download_name" not in cols:
                conn.execute(text("ALTER TABLE product_software_downloads ADD COLUMN artifact_download_name VARCHAR(256)"))
            if "artifact_mime" not in cols:
                conn.execute(text("ALTER TABLE product_software_downloads ADD COLUMN artifact_mime VARCHAR(128)"))
        cols = _column_names(conn, "newsletter_subscribers")
        if cols:
            if "unsubscribe_token" not in cols:
                conn.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN unsubscribe_token VARCHAR(64)"))
            if "unsubscribed_at" not in cols:
                conn.execute(text("ALTER TABLE newsletter_subscribers ADD COLUMN unsubscribed_at TIMESTAMP"))


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
