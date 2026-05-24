"""从 local/credentials（单文件）或环境变量读取密钥，写入 DB 连接器与 LLM 配置。

推荐（SQLite 本地）:
  copy local\\credentials.example local\\credentials
  编辑 local\\credentials 填入各 Key
  set AITRENDS_DATABASE_URL=sqlite:///D:/aisoul/backend/data/dev_local.db
  py -3.12 scripts/load_local_credentials.py

仍兼容 local/newsapi.credentials 等分散文件（credentials 优先）。
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
UNIFIED_CREDENTIALS = LOCAL / "credentials"


def _parse_credentials_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    kv: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip().lstrip("\ufeff").upper()] = v.strip().strip('"').strip("'")
    return kv


@lru_cache(maxsize=1)
def merged_credentials_kv() -> dict[str, str]:
    """合并：local/credentials → 环境变量 → 各 legacy 分散文件。"""
    kv: dict[str, str] = {}

    if UNIFIED_CREDENTIALS.is_file():
        kv.update(_parse_credentials_file(UNIFIED_CREDENTIALS))
    alt = LOCAL / "secrets.env"
    if alt.is_file():
        for k, v in _parse_credentials_file(alt).items():
            kv.setdefault(k, v)

    _ENV_KEYS = (
        "AITRENDS_LLM_API_KEY",
        "AISOU_LLM_API_KEY",
        "AITRENDS_LLM_BASE_URL",
        "AISOU_LLM_BASE_URL",
        "AITRENDS_LLM_MODEL",
        "AISOU_LLM_MODEL",
        "NEWSAPI_KEY",
        "AITRENDS_NEWSAPI_KEY",
        "THENEWSAPI_API_TOKEN",
        "AITRENDS_THENEWSAPI_TOKEN",
        "PRODUCT_HUNT_API_KEY",
        "PRODUCT_HUNT_CLIENT_ID",
        "PRODUCT_HUNT_APP_SECRET",
        "PRODUCT_HUNT_CLIENT_SECRET",
        "PRODUCT_HUNT_ACCESS_TOKEN",
    )
    for ek in _ENV_KEYS:
        ev = (os.getenv(ek) or "").strip()
        if ev:
            kv.setdefault(ek.upper(), ev)

    # 分散文件仅作迁移备用；日常使用请只维护 local/credentials
    if not UNIFIED_CREDENTIALS.is_file():
        for name in ("newsapi", "thenewsapi", "product_hunt"):
            p = LOCAL / f"{name}.credentials"
            if p.is_file():
                for k, v in _parse_credentials_file(p).items():
                    kv.setdefault(k, v)

    return kv


def _kv(*keys: str) -> str:
    m = merged_credentials_kv()
    for k in keys:
        v = (m.get(k.upper()) or "").strip()
        if v:
            return v
    return ""


def load_product_hunt_credentials() -> tuple[str, str, str]:
    api_key = _kv("PRODUCT_HUNT_API_KEY", "PRODUCT_HUNT_CLIENT_ID")
    secret = _kv("PRODUCT_HUNT_APP_SECRET", "PRODUCT_HUNT_CLIENT_SECRET")
    token = _kv("PRODUCT_HUNT_ACCESS_TOKEN")
    return api_key, secret, token


def load_newsapi_credentials() -> str:
    return _kv("NEWSAPI_KEY", "NEWSAPI_API_KEY", "AITRENDS_NEWSAPI_KEY")


def load_thenewsapi_credentials() -> str:
    return _kv("THENEWSAPI_API_TOKEN", "THENEWSAPI_TOKEN", "AITRENDS_THENEWSAPI_TOKEN")


def load_llm_credentials() -> tuple[str, str, str]:
    return (
        _kv("AITRENDS_LLM_API_KEY", "AISOU_LLM_API_KEY"),
        _kv("AITRENDS_LLM_BASE_URL", "AISOU_LLM_BASE_URL") or "https://api.deepseek.com/v1",
        _kv("AITRENDS_LLM_MODEL", "AISOU_LLM_MODEL") or "deepseek-chat",
    )


def apply_llm_credentials(db) -> bool:
    key, base, model = load_llm_credentials()
    if not key:
        return False
    from backend.app.product_models import ProductSetting

    from backend.app.llm_settings_service import DEFAULT_LLM

    row = db.get(ProductSetting, "llm")
    if not row:
        row = ProductSetting(key="llm", value_json={})
        db.add(row)
    cur = {**DEFAULT_LLM, **((row.value_json if row else {}) or {})}
    cur["api_key"] = key
    if base:
        cur["base_url"] = base.rstrip("/")
    if model:
        cur["model"] = model
    row.value_json = cur
    db.commit()
    return True


def apply_newsapi_credentials(db) -> bool:
    api_key = load_newsapi_credentials()
    if not api_key:
        return False
    from sqlalchemy import select

    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import ProductConnector

    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "newsapi"))
    if src:
        src.enabled = True
    conn = db.scalar(
        select(ProductConnector).where(ProductConnector.admin_source_key == "newsapi").order_by(ProductConnector.id)
    )
    if conn:
        cfg = dict(conn.config_json or {})
        cfg["api_key"] = api_key
        cfg["auth_mode"] = "query_key"
        cfg["key_param"] = "apiKey"
        conn.config_json = cfg
        conn.enabled = True
    db.commit()
    return True


def apply_thenewsapi_credentials(db) -> bool:
    token = load_thenewsapi_credentials()
    if not token:
        return False
    from sqlalchemy import select

    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import ProductConnector

    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "thenewsapi"))
    if src:
        src.enabled = True
    conn = db.scalar(
        select(ProductConnector).where(ProductConnector.admin_source_key == "thenewsapi").order_by(ProductConnector.id)
    )
    if conn:
        cfg = dict(conn.config_json or {})
        cfg["api_key"] = token
        cfg["auth_mode"] = "query_key"
        cfg["key_param"] = "api_token"
        conn.config_json = cfg
        conn.enabled = True
    db.commit()
    return True


def apply_news_credentials(db) -> dict[str, bool]:
    return {
        "newsapi": apply_newsapi_credentials(db),
        "thenewsapi": apply_thenewsapi_credentials(db),
    }


def apply_product_hunt_credentials(db) -> bool:
    api_key, secret, token = load_product_hunt_credentials()
    if not api_key and not secret and not token:
        return False
    from sqlalchemy import select

    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import ProductConnector

    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "product_hunt"))
    if src:
        src.enabled = True
    conn = db.scalar(
        select(ProductConnector).where(ProductConnector.admin_source_key == "product_hunt").order_by(ProductConnector.id)
    )
    if conn:
        cfg = dict(conn.config_json or {})
        cfg["api_key"] = api_key or token
        if secret:
            cfg["oauth_client_secret"] = secret
        elif "oauth_client_secret" in cfg and token:
            cfg.pop("oauth_client_secret", None)
        conn.config_json = cfg
        conn.enabled = True
    db.commit()
    return True


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "(未配置)"
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def seed_all_local_credentials(db) -> dict[str, bool]:
    merged_credentials_kv.cache_clear()
    out = {
        "llm": apply_llm_credentials(db),
        **apply_news_credentials(db),
        "product_hunt": apply_product_hunt_credentials(db),
    }
    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="将 local/credentials 注入当前 DB")
    p.add_argument("--db-url", default="", help="例如 sqlite:///D:/aisoul/backend/data/dev_local.db")
    args = p.parse_args()
    if args.db_url:
        os.environ["AITRENDS_DATABASE_URL"] = args.db_url.strip()

    if not UNIFIED_CREDENTIALS.is_file():
        print(f"缺少 {UNIFIED_CREDENTIALS}")
        print("  copy local\\credentials.example local\\credentials")
        print("  或 py -3.12 scripts/merge_local_credentials.py  # 从旧分散文件合并")
        return 1

    from sqlalchemy import select

    from backend.app.db import SessionLocal, engine
    from backend.app.llm_settings_service import resolve_llm_http_config
    from backend.app.product_models import ProductConnector

    db = SessionLocal()
    try:
        from backend.app.db import Base, ensure_schema_compatibility
        from backend.app.product_connectors_bootstrap import ensure_core_admin_connectors
        from backend.app.services import ensure_mainstream_admin_sources

        Base.metadata.create_all(bind=engine)
        ensure_schema_compatibility()
        ensure_mainstream_admin_sources(db)
        ensure_core_admin_connectors(db)

        applied = seed_all_local_credentials(db)
        _base, llm_key, model = resolve_llm_http_config(db)
        print(f"凭据文件: {UNIFIED_CREDENTIALS}")
        print(f"数据库: {engine.url.database}")
        print(f"LLM: model={model} key={_mask(llm_key)}")
        print("写入结果:")
        for src, ok in sorted(applied.items()):
            print(f"  {src}: {'OK' if ok else '跳过(文件中为空)'}")
        print("\n连接器 api_key:")
        for c in db.scalars(select(ProductConnector).order_by(ProductConnector.id)).all():
            cfg = dict(c.config_json or {})
            has = bool(str(cfg.get("api_key") or "").strip())
            sec = bool(str(cfg.get("oauth_client_secret") or "").strip())
            print(f"  id={c.id} {c.admin_source_key}: {_mask(str(cfg.get('api_key') or ''))}{' +secret' if sec else ''}")
        need = {"newsapi", "thenewsapi", "product_hunt"}
        missing = [
            c.admin_source_key
            for c in db.scalars(select(ProductConnector).where(ProductConnector.enabled.is_(True))).all()
            if c.admin_source_key in need and not str((dict(c.config_json or {}).get("api_key") or "")).strip()
        ]
        if not (llm_key or "").strip():
            print("\n仍缺 LLM Key — 在 local/credentials 填写 AITRENDS_LLM_API_KEY")
            return 1
        if missing:
            print(f"\n仍缺数据源 Key: {', '.join(missing)}")
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
