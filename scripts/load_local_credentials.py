"""从 local/*.credentials 读取密钥并注入验收库连接器（勿提交真实 .credentials）。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"


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


def load_product_hunt_credentials() -> tuple[str, str, str]:
    path = LOCAL / "product_hunt.credentials"
    if not path.is_file():
        return "", "", ""
    kv = _parse_credentials_file(path)
    api_key = (kv.get("PRODUCT_HUNT_API_KEY") or kv.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
    secret = (kv.get("PRODUCT_HUNT_APP_SECRET") or kv.get("PRODUCT_HUNT_CLIENT_SECRET") or "").strip()
    token = (kv.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
    return api_key, secret, token


def load_newsapi_credentials() -> str:
    key = (os.getenv("AITRENDS_NEWSAPI_KEY") or os.getenv("NEWSAPI_KEY") or "").strip()
    path = LOCAL / "newsapi.credentials"
    if path.is_file() and not key:
        kv = _parse_credentials_file(path)
        key = (kv.get("NEWSAPI_KEY") or kv.get("NEWSAPI_API_KEY") or kv.get("AITRENDS_NEWSAPI_KEY") or "").strip()
    return key


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


def load_thenewsapi_credentials() -> str:
    token = (os.getenv("AITRENDS_THENEWSAPI_TOKEN") or os.getenv("THENEWSAPI_API_TOKEN") or "").strip()
    path = LOCAL / "thenewsapi.credentials"
    if path.is_file() and not token:
        kv = _parse_credentials_file(path)
        token = (
            kv.get("THENEWSAPI_API_TOKEN")
            or kv.get("THENEWSAPI_TOKEN")
            or kv.get("AITRENDS_THENEWSAPI_TOKEN")
            or ""
        ).strip()
    return token


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
