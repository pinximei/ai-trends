"""
运行时可调参数：存 product_settings_kv.runtime，供管理端修改。
密钥类（JWT_SECRET、SIGNING_KEY、AISOU_DATABASE_URL 等）仍仅用环境变量，不入库。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from sqlalchemy.orm import Session

from .product_models import ProductSetting

RUNTIME_KEY = "runtime"
_LOCK = threading.RLock()
_SNAPSHOT: dict[str, Any] = {}
_SNAPSHOT_MONO: float = 0.0
_DEFAULT_CORS = (
    "http://127.0.0.1:5172,http://localhost:5172,http://127.0.0.1:5173,http://localhost:5173,"
    "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5174,http://localhost:5174"
)


def _env_defaults() -> dict[str, Any]:
    app_env = os.getenv("AISOU_ENV", "dev").lower()
    cookie_secure = os.getenv("AISOU_ADMIN_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"}
    if app_env in {"dev", "local"} and os.getenv("AISOU_ADMIN_COOKIE_SECURE") is None:
        cookie_secure = False
    return {
        "cors_origins_csv": os.getenv("AISOU_CORS_ORIGINS", _DEFAULT_CORS).strip(),
        "jwt_ttl_seconds": int(os.getenv("AISOU_JWT_TTL_SECONDS", "1800") or "1800"),
        "allowed_skew_seconds": int(os.getenv("AISOU_ALLOWED_SKEW_SECONDS", "300") or "300"),
        "require_https": os.getenv("AISOU_REQUIRE_HTTPS", "true").lower() in {"1", "true", "yes", "on"},
        "allow_insecure_localhost": os.getenv("AISOU_ALLOW_INSECURE_LOCALHOST", "true").lower()
        in {"1", "true", "yes", "on"},
        "admin_cookie_secure": cookie_secure,
        "app_env": app_env,
        "demo_seed_enabled": None,  # None = 按 AISOU_ENABLE_DEMO_SEED 或 app_env 推断
        "legacy_admin_enabled": os.getenv("AISOU_LEGACY_ADMIN_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
        "app_release_label": "",
        "hot_llm_model": os.getenv("AISOU_HOT_LLM_MODEL", "rule-based").strip() or "rule-based",
    }


def _normalize(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    out["jwt_ttl_seconds"] = max(60, min(864_000, int(out.get("jwt_ttl_seconds") or 1800)))
    out["allowed_skew_seconds"] = max(30, min(3600, int(out.get("allowed_skew_seconds") or 300)))
    out["require_https"] = bool(out.get("require_https", True))
    out["allow_insecure_localhost"] = bool(out.get("allow_insecure_localhost", True))
    out["admin_cookie_secure"] = bool(out.get("admin_cookie_secure", True))
    ae = str(out.get("app_env") or "dev").lower().strip()
    if ae not in {"dev", "local", "staging", "production", "prod"}:
        ae = "dev"
    if ae == "prod":
        ae = "production"
    out["app_env"] = ae
    if out.get("demo_seed_enabled") is not None:
        out["demo_seed_enabled"] = bool(out["demo_seed_enabled"])
    out["legacy_admin_enabled"] = bool(out.get("legacy_admin_enabled", False))
    out["cors_origins_csv"] = str(out.get("cors_origins_csv") or _DEFAULT_CORS).strip()
    out["app_release_label"] = str(out.get("app_release_label") or "").strip()
    out["hot_llm_model"] = str(out.get("hot_llm_model") or "rule-based").strip() or "rule-based"
    return out


def _merge_row_into(base: dict[str, Any], row: ProductSetting | None) -> dict[str, Any]:
    if not row or not isinstance(row.value_json, dict):
        return base
    for k, v in row.value_json.items():
        if v is None and k == "demo_seed_enabled":
            base[k] = None
            continue
        if v is not None:
            base[k] = v
    return base


def ensure_runtime_settings_row(db: Session) -> None:
    if db.get(ProductSetting, RUNTIME_KEY):
        return
    db.add(ProductSetting(key=RUNTIME_KEY, value_json={}))
    db.commit()


def refresh_runtime_snapshot(db: Session) -> dict[str, Any]:
    """从数据库合并后写入内存快照（多 worker 各自维护；保存配置后会再次调用）。"""
    global _SNAPSHOT, _SNAPSHOT_MONO
    ensure_runtime_settings_row(db)
    row = db.get(ProductSetting, RUNTIME_KEY)
    merged = _normalize(_merge_row_into(_env_defaults(), row))
    with _LOCK:
        _SNAPSHOT = merged
        _SNAPSHOT_MONO = time.monotonic()
    return merged


def get_snapshot() -> dict[str, Any]:
    """内存快照；在 lifespan 启动与保存「运行参数」后刷新。未刷新前为环境默认值。"""
    with _LOCK:
        if not _SNAPSHOT:
            return _normalize(_env_defaults())
        return dict(_SNAPSHOT)


def effective_app_env() -> str:
    return str(get_snapshot().get("app_env") or "dev").lower()


def demo_seed_enabled_effective() -> bool:
    return _demo_seed_effective_from_merged(get_snapshot())


def cors_allow_origins_list() -> list[str]:
    raw = str(get_snapshot().get("cors_origins_csv") or "").strip()
    return [o.strip() for o in raw.split(",") if o.strip()]


def jwt_ttl_seconds() -> int:
    return int(get_snapshot().get("jwt_ttl_seconds") or 1800)


def allowed_skew_seconds() -> int:
    return int(get_snapshot().get("allowed_skew_seconds") or 300)


def require_https_flag() -> bool:
    return bool(get_snapshot().get("require_https", True))


def allow_insecure_localhost_flag() -> bool:
    return bool(get_snapshot().get("allow_insecure_localhost", True))


def admin_cookie_secure_effective() -> bool:
    return bool(get_snapshot().get("admin_cookie_secure", True))


def legacy_admin_enabled() -> bool:
    return bool(get_snapshot().get("legacy_admin_enabled", False))


def hot_llm_model_effective() -> str:
    return str(get_snapshot().get("hot_llm_model") or "rule-based").strip() or "rule-based"


def app_release_label_effective() -> str:
    return str(get_snapshot().get("app_release_label") or "").strip()


def _demo_seed_effective_from_merged(merged: dict[str, Any]) -> bool:
    v = merged.get("demo_seed_enabled")
    if v is not None:
        return bool(v)
    if os.getenv("AISOU_ENABLE_DEMO_SEED") is not None:
        return os.getenv("AISOU_ENABLE_DEMO_SEED", "").lower() in {"1", "true", "yes", "on"}
    ae = str(merged.get("app_env") or "dev").lower()
    return ae in {"dev", "local"}


def get_runtime_settings_public(db: Session) -> dict[str, Any]:
    ensure_runtime_settings_row(db)
    merged = _normalize(_merge_row_into(_env_defaults(), db.get(ProductSetting, RUNTIME_KEY)))
    return {
        "cors_origins_csv": merged["cors_origins_csv"],
        "jwt_ttl_seconds": merged["jwt_ttl_seconds"],
        "allowed_skew_seconds": merged["allowed_skew_seconds"],
        "require_https": merged["require_https"],
        "allow_insecure_localhost": merged["allow_insecure_localhost"],
        "admin_cookie_secure": merged["admin_cookie_secure"],
        "app_env": merged["app_env"],
        "demo_seed_enabled": merged.get("demo_seed_enabled"),
        "demo_seed_effective": _demo_seed_effective_from_merged(merged),
        "legacy_admin_enabled": merged["legacy_admin_enabled"],
        "app_release_label": merged["app_release_label"],
        "hot_llm_model": merged["hot_llm_model"],
        "secrets_note": "JWT_SECRET / SIGNING_KEY / AISOU_AUTH_BOOTSTRAP_KEY / AISOU_DATABASE_URL / AISOU_ADMIN_TOKEN 仍仅通过环境变量配置，不入库。",
    }


def save_runtime_settings_patch(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    ensure_runtime_settings_row(db)
    row = db.get(ProductSetting, RUNTIME_KEY)
    assert row is not None
    cur = _normalize(_merge_row_into(_env_defaults(), row))
    allowed_keys = {
        "cors_origins_csv",
        "jwt_ttl_seconds",
        "allowed_skew_seconds",
        "require_https",
        "allow_insecure_localhost",
        "admin_cookie_secure",
        "app_env",
        "demo_seed_enabled",
        "legacy_admin_enabled",
        "app_release_label",
        "hot_llm_model",
    }
    for k, v in patch.items():
        if k not in allowed_keys:
            continue
        if k == "demo_seed_enabled":
            cur[k] = v
            continue
        if v is None:
            continue
        cur[k] = v
    row.value_json = {k: cur.get(k) for k in allowed_keys}
    from datetime import datetime

    row.updated_at = datetime.utcnow()
    db.commit()
    return refresh_runtime_snapshot(db)


def assert_production_security() -> None:
    """DB 或环境中的运行模式非 dev/local 时，禁止弱默认密钥（密钥本身仍只来自环境变量）。"""
    ae = effective_app_env()
    if ae in {"dev", "local"}:
        return
    weak = {"change-this-jwt-secret", "change-this-signing-key", "dev-bootstrap-key"}
    jwt_s = os.getenv("AISOU_JWT_SECRET", "change-this-jwt-secret")
    sig_s = os.getenv("AISOU_SIGNING_KEY", "change-this-signing-key")
    boot = os.getenv("AISOU_AUTH_BOOTSTRAP_KEY", "dev-bootstrap-key")
    if jwt_s in weak or sig_s in weak or boot in weak:
        raise RuntimeError("weak security defaults are not allowed outside dev/local (set AISOU_JWT_SECRET etc.)")


with _LOCK:
    _SNAPSHOT = _normalize(_env_defaults())
    _SNAPSHOT_MONO = time.monotonic()
