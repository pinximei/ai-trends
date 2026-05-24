"""数据源 Query 鉴权（NewsAPI / TheNewsAPI 等）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .product_models import ProductConnector

# source -> (auth_mode, query 参数名)
SOURCE_QUERY_KEY_AUTH: dict[str, tuple[str, str]] = {
    "newsapi": ("query_key", "apiKey"),
    "thenewsapi": ("query_key", "api_token"),
}


def source_uses_query_key_auth(source_key: str) -> bool:
    return (source_key or "").strip().lower() in SOURCE_QUERY_KEY_AUTH


def query_auth_for_source(source_key: str) -> tuple[str, str]:
    """返回 (auth_mode, key_param)；非 Query 源默认 bearer + key。"""
    sk = (source_key or "").strip().lower()
    if sk in SOURCE_QUERY_KEY_AUTH:
        return SOURCE_QUERY_KEY_AUTH[sk]
    return ("bearer", "key")


def apply_connector_auth_defaults(source_key: str, cfg: dict) -> dict:
    """写入连接器 config_json 时补齐 auth_mode / key_param。"""
    out = dict(cfg or {})
    mode, param = query_auth_for_source(source_key)
    if source_uses_query_key_auth(source_key):
        out["auth_mode"] = mode
        out["key_param"] = param
    else:
        out.setdefault("auth_mode", "bearer")
    return out


def load_stored_api_key_for_source(db: Session, source_key: str) -> str:
    """同步与「测试连接」共用：优先读绑定连接器的 config_json.api_key。"""
    sk = (source_key or "").strip().lower()
    if not sk:
        return ""
    conn = db.scalar(
        select(ProductConnector)
        .where(ProductConnector.admin_source_key == sk)
        .order_by(ProductConnector.id)
        .limit(1)
    )
    if not conn:
        return ""
    return str((dict(conn.config_json or {}).get("api_key") or "")).strip()


def merge_api_key_into_url(url: str, *, api_key: str, key_param: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit((url or "").strip())
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q[(key_param or "key").strip() or "key"] = api_key
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, urlencode(q), parts.fragment))
