"""内置三路数据源热度拉取自动监测（不写库文章，仅探测 HTTP + pack 数）。"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .connector_heat_fetch import (
    sync_github_trending_top_details,
    sync_hacker_news_top_details,
    sync_product_hunt_top_details,
)
from .domain.articles import parse_connector_sync_item_snippets
from .models import AdminSourceConfig
from .product_models import ProductConnector, ProductSetting
from .product_hunt_oauth import resolve_product_hunt_bearer
from .services import MAINSTREAM_ADMIN_SOURCE_PRESETS

logger = logging.getLogger(__name__)

HEALTH_MONITOR_KEY = "mainstream_sources_health"
DEFAULT_INTERVAL_MINUTES = 30
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PH_CREDS_FILE = _REPO_ROOT / "local" / "product_hunt.credentials"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_health_monitor_json() -> dict[str, Any]:
    return {
        "enabled": True,
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "last_run_at": None,
        "last_all_ok": None,
        "sources": {},
    }


def ensure_health_monitor_row(db: Session) -> None:
    if db.get(ProductSetting, HEALTH_MONITOR_KEY):
        return
    db.add(ProductSetting(key=HEALTH_MONITOR_KEY, value_json=default_health_monitor_json()))
    db.commit()


def get_health_monitor_merged(db: Session) -> dict[str, Any]:
    ensure_health_monitor_row(db)
    row = db.get(ProductSetting, HEALTH_MONITOR_KEY)
    base = default_health_monitor_json()
    if row and isinstance(row.value_json, dict):
        base.update(row.value_json)
    base["enabled"] = bool(base.get("enabled", True))
    im = int(base.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES)
    base["interval_minutes"] = max(10, min(360, im))
    if not isinstance(base.get("sources"), dict):
        base["sources"] = {}
    return base


def save_health_monitor_snapshot(db: Session, snapshot: dict[str, Any]) -> dict[str, Any]:
    ensure_health_monitor_row(db)
    row = db.get(ProductSetting, HEALTH_MONITOR_KEY)
    merged = get_health_monitor_merged(db)
    merged.update(snapshot)
    if row:
        row.value_json = merged
    db.commit()
    return merged


def get_health_monitor_public(db: Session) -> dict[str, Any]:
    m = get_health_monitor_merged(db)
    sources = m.get("sources") if isinstance(m.get("sources"), dict) else {}
    items = []
    for preset in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        key = preset["source"]
        row = sources.get(key) if isinstance(sources.get(key), dict) else {}
        items.append(
            {
                "source": key,
                "label": preset.get("preset_label") or key,
                **row,
            }
        )
    failed = [x for x in items if x.get("status") == "fail"]
    degraded = [x for x in items if x.get("status") == "degraded"]
    return {
        "enabled": m.get("enabled"),
        "interval_minutes": m.get("interval_minutes"),
        "last_run_at": m.get("last_run_at"),
        "last_all_ok": m.get("last_all_ok"),
        "summary": {
            "total": len(items),
            "ok": sum(1 for x in items if x.get("status") == "ok"),
            "degraded": len(degraded),
            "fail": len(failed),
        },
        "sources": items,
    }


def save_health_monitor_settings_patch(db: Session, patch: dict[str, Any]) -> dict[str, Any]:
    cur = get_health_monitor_merged(db)
    if "enabled" in patch and patch["enabled"] is not None:
        cur["enabled"] = bool(patch["enabled"])
    if "interval_minutes" in patch and patch["interval_minutes"] is not None:
        cur["interval_minutes"] = max(10, min(360, int(patch["interval_minutes"])))
    return save_health_monitor_snapshot(db, cur)


def _load_ph_credentials_from_file() -> tuple[str, str, str]:
    if not _PH_CREDS_FILE.is_file():
        return "", "", ""
    kv: dict[str, str] = {}
    for raw in _PH_CREDS_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip().upper()] = v.strip().strip('"').strip("'")
    api_key = (kv.get("PRODUCT_HUNT_API_KEY") or kv.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
    secret = (kv.get("PRODUCT_HUNT_APP_SECRET") or kv.get("PRODUCT_HUNT_CLIENT_SECRET") or "").strip()
    token = (kv.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
    return api_key, secret, token


def _product_hunt_headers(db: Session) -> tuple[dict[str, str], str]:
    api_key = ""
    secret = ""
    conn = db.scalar(
        select(ProductConnector)
        .where(ProductConnector.admin_source_key == "product_hunt")
        .order_by(ProductConnector.id)
    )
    if conn and isinstance(conn.config_json, dict):
        api_key = (conn.config_json.get("api_key") or "").strip()
        secret = (conn.config_json.get("oauth_client_secret") or "").strip()
    if not api_key and not secret:
        fk, fs, ft = _load_ph_credentials_from_file()
        api_key, secret = fk or ft, fs
    if not api_key and not secret:
        api_key = (os.environ.get("PRODUCT_HUNT_API_KEY") or os.environ.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
        secret = (os.environ.get("PRODUCT_HUNT_APP_SECRET") or "").strip()
    bearer, mode = resolve_product_hunt_bearer(api_key=api_key, oauth_client_secret=secret)
    return {"User-Agent": "AiTrends-HealthMonitor/1.0", "Authorization": f"Bearer {bearer}"}, mode


def _pack_count(body: str) -> int:
    return len(parse_connector_sync_item_snippets((body or "")[:120000]) or [])


def check_mainstream_source_heat(db: Session, source_key: str) -> dict[str, Any]:
    """单源热度探测；返回 status: ok | degraded | fail。"""
    key = (source_key or "").strip().lower()
    checked_at = _utc_now_iso()
    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
    if not src:
        return {
            "status": "fail",
            "ok": False,
            "http_status": 0,
            "packs": 0,
            "message": "no admin_source_config",
            "checked_at": checked_at,
        }

    url = (src.api_base or "").strip()
    headers: dict[str, str] = {"User-Agent": "AiTrends-HealthMonitor/1.0", "Accept": "application/json"}
    detail = key
    code, body = 0, ""
    attempts = 4 if key == "product_hunt" else 1

    for attempt in range(attempts):
        try:
            if key == "product_hunt":
                headers, detail = _product_hunt_headers(db)
                code, body = sync_product_hunt_top_details(headers)
            elif key == "github":
                from .connector_heat_fetch import GITHUB_TRENDING_DEFAULT, github_trending_is_discovery_url

                if not github_trending_is_discovery_url(url):
                    url = GITHUB_TRENDING_DEFAULT
                if (os.environ.get("GITHUB_TOKEN") or os.environ.get("AITRENDS_GITHUB_TOKEN") or "").strip():
                    headers["Authorization"] = f"Bearer {(os.environ.get('GITHUB_TOKEN') or os.environ.get('AITRENDS_GITHUB_TOKEN') or '').strip()}"
                code, body = sync_github_trending_top_details(url, headers)
                detail = "trending"
            elif key == "hacker_news":
                code, body = sync_hacker_news_top_details(url, headers)
                detail = "algolia"
            else:
                return {
                    "status": "fail",
                    "ok": False,
                    "http_status": 0,
                    "packs": 0,
                    "message": "unknown source",
                    "checked_at": checked_at,
                }
        except Exception as e:
            return {
                "status": "fail",
                "ok": False,
                "http_status": 0,
                "packs": 0,
                "message": f"{type(e).__name__}: {e}"[:240],
                "checked_at": checked_at,
            }

        if key == "product_hunt" and code == 429 and attempt + 1 < attempts:
            time.sleep(15.0 * (attempt + 1))
            continue
        break

    packs = _pack_count(body)
    note = ""
    try:
        obj = json.loads((body or "")[:8000])
        if isinstance(obj, dict):
            note = str(obj.get("note") or "")
    except json.JSONDecodeError:
        note = "not_json"

    ok_http = bool(code and 200 <= code < 300)
    if ok_http and packs > 0:
        return {
            "status": "ok",
            "ok": True,
            "http_status": code,
            "packs": packs,
            "note": note,
            "message": f"HTTP {code} packs={packs} ({detail})",
            "checked_at": checked_at,
        }
    if ok_http and packs == 0 and key == "github" and note in ("repo_api_empty", "trending_parse_empty"):
        return {
            "status": "degraded",
            "ok": True,
            "http_status": code,
            "packs": 0,
            "note": note,
            "message": f"HTTP {code} packs=0 ({note}); 建议配置 GitHub api_key",
            "checked_at": checked_at,
        }
    if ok_http and packs == 0:
        return {
            "status": "fail",
            "ok": False,
            "http_status": code,
            "packs": 0,
            "note": note,
            "message": f"HTTP {code} packs=0 note={note!r} ({detail})",
            "checked_at": checked_at,
        }
    return {
        "status": "fail",
        "ok": False,
        "http_status": code or 0,
        "packs": packs,
        "note": note,
        "message": f"HTTP {code or 0} len={len(body or '')} note={note!r}",
        "checked_at": checked_at,
    }


def run_mainstream_sources_health_check(db: Session) -> dict[str, Any]:
    """探测全部内置三路，写入 product_settings_kv.mainstream_sources_health。"""
    settings = get_health_monitor_merged(db)
    sources_out: dict[str, Any] = {}
    for preset in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        key = preset["source"]
        row = check_mainstream_source_heat(db, key)
        sources_out[key] = row
        if row.get("status") == "fail":
            logger.warning("source health FAIL %s: %s", key, row.get("message"))
        elif row.get("status") == "degraded":
            logger.debug("source health DEGRADED %s: %s", key, row.get("message"))

    failed = [k for k, v in sources_out.items() if v.get("status") == "fail"]
    all_ok = len(failed) == 0
    snapshot = {
        **settings,
        "last_run_at": _utc_now_iso(),
        "last_all_ok": all_ok,
        "sources": sources_out,
    }
    save_health_monitor_snapshot(db, snapshot)
    if failed:
        logger.warning(
            "mainstream sources health check: fail=%s (%s)",
            len(failed),
            ", ".join(failed),
        )
    return get_health_monitor_public(db)


def health_monitor_due(settings: dict[str, Any], *, now: datetime | None = None) -> bool:
    if not settings.get("enabled", True):
        return False
    last = settings.get("last_run_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except ValueError:
        return True
    ref = now or datetime.now(timezone.utc)
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    interval = max(10, int(settings.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES))
    return (ref - last_dt).total_seconds() >= interval * 60
