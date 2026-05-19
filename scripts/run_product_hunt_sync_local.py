"""本地：从 local/product_hunt.credentials 读取凭据，跑通 GraphQL → 连接器同步 → 入库。

用法（仓库根目录）:
  copy local\\product_hunt.credentials.example local\\product_hunt.credentials
  # 编辑 local/product_hunt.credentials 填入 Key/Secret 或 Access Token

  py -3.12 scripts/run_product_hunt_sync_local.py --sqlite
  py -3.12 scripts/run_product_hunt_sync_local.py --no-sync   # 只测 API

仍支持环境变量 PRODUCT_HUNT_* 与旧版仓库根 keys 文件中的 product_hunt 段（兼容）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDS = ROOT / "local" / "product_hunt.credentials"
LEGACY_KEYS = ROOT / "keys"


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--creds",
        type=Path,
        default=DEFAULT_CREDS,
        help="凭据文件（默认 local/product_hunt.credentials）",
    )
    ap.add_argument("--no-sync", action="store_true", help="仅测 GraphQL，不写库")
    ap.add_argument(
        "--sqlite",
        nargs="?",
        const=str(ROOT / "backend" / "data" / "dev_local.db"),
        default=None,
        help="用 SQLite（默认 backend/data/dev_local.db）",
    )
    return ap.parse_args()


def _configure_db(sqlite_arg: str | None) -> None:
    if sqlite_arg is None:
        default = ROOT / "backend" / "data" / "dev_local.db"
        if default.is_file():
            sqlite_arg = str(default)
    if sqlite_arg:
        p = Path(sqlite_arg)
        p.parent.mkdir(parents=True, exist_ok=True)
        os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{p.resolve().as_posix()}"


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "(空)"
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def _parse_dotenv_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k.upper()] = v
    return out


def load_product_hunt_credentials(creds_path: Path) -> tuple[str, str, str]:
    """返回 (api_key, oauth_secret, access_token_direct)。"""
    env_key = (os.environ.get("PRODUCT_HUNT_API_KEY") or os.environ.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
    env_sec = (
        os.environ.get("PRODUCT_HUNT_APP_SECRET") or os.environ.get("PRODUCT_HUNT_CLIENT_SECRET") or ""
    ).strip()
    env_tok = (os.environ.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
    if env_key or env_sec or env_tok:
        return env_key, env_sec, env_tok

    if creds_path.is_file():
        kv = _parse_dotenv_lines(creds_path.read_text(encoding="utf-8", errors="replace"))
        api_key = (kv.get("PRODUCT_HUNT_API_KEY") or kv.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
        secret = (kv.get("PRODUCT_HUNT_APP_SECRET") or kv.get("PRODUCT_HUNT_CLIENT_SECRET") or "").strip()
        direct = (kv.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
        if api_key or secret or direct:
            return api_key, secret, direct

    if LEGACY_KEYS.is_file():
        text = LEGACY_KEYS.read_text(encoding="utf-8", errors="replace")
        api_key = ""
        api_secret = ""
        in_ph = False
        for raw in text.splitlines():
            line = raw.strip()
            if re.match(r"^product_hunt\s*$", line, re.I):
                in_ph = True
                continue
            if in_ph and re.match(r"^[a-z_][a-z0-9_]*\s*:", line, re.I):
                if not line.lower().startswith("api key") and not line.lower().startswith("api secret"):
                    break
            if not in_ph:
                continue
            m = re.match(r"^API\s*Key\s*:\s*(.+)$", line, re.I)
            if m:
                api_key = m.group(1).strip()
                continue
            m = re.match(r"^API\s*Secret\s*:\s*(.+)$", line, re.I)
            if m:
                api_secret = m.group(1).strip()
        if api_key or api_secret:
            return api_key, api_secret, ""

    return "", "", ""


def main() -> int:
    args = _parse_args()
    _configure_db(args.sqlite)
    sys.path.insert(0, str(ROOT))

    from sqlalchemy import func, select

    from backend.app.connector_heat_fetch import sync_product_hunt_top_details
    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.lifespan import _startup_sync
    from backend.app.product_hunt_oauth import resolve_product_hunt_bearer
    from backend.app.product_models import Article, ProductConnector, ProductConnectorLog
    from backend.app.routers.admin_extended import run_connector_sync

    api_key, api_secret, access_direct = load_product_hunt_credentials(args.creds)
    if not api_key and not api_secret and not access_direct:
        print("FAIL: 未找到凭据。")
        print(f"  请复制 local/product_hunt.credentials.example -> {args.creds}")
        print("  并填写 PRODUCT_HUNT_API_KEY + PRODUCT_HUNT_APP_SECRET，或 PRODUCT_HUNT_ACCESS_TOKEN")
        return 1

    src = "env" if os.environ.get("PRODUCT_HUNT_API_KEY") or os.environ.get("PRODUCT_HUNT_ACCESS_TOKEN") else str(args.creds)
    if not args.creds.is_file() and (api_key or api_secret) and LEGACY_KEYS.is_file():
        src = f"{LEGACY_KEYS} (legacy)"
    print(f"credentials: {src}")
    print(f"  key={_mask(api_key)} secret={_mask(api_secret)} token={_mask(access_direct)}")

    ensure_schema_compatibility()
    _startup_sync()

    def try_bearer(k: str, sec: str) -> tuple[str, str] | None:
        try:
            return resolve_product_hunt_bearer(api_key=k, oauth_client_secret=sec)
        except (ValueError, RuntimeError):
            return None

    def graphql_probe(bearer: str) -> tuple[int, int]:
        headers = {
            "User-Agent": "AiTrends-PHLocal/1.0",
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer}",
        }
        code, body = sync_product_hunt_top_details(headers)
        n = 0
        if 200 <= code < 300 and body:
            try:
                n = len(json.loads(body).get("connector_sync_items_v1") or [])
            except json.JSONDecodeError:
                pass
        return code, n

    candidates: list[tuple[str, str, str]] = []
    if access_direct:
        candidates.append((access_direct, "", "access_token"))
    if api_secret:
        candidates.append((api_key, api_secret, "oauth"))
    if api_key:
        candidates.append((api_key, "", "direct"))

    bearer = ""
    mode = ""
    code = 0
    n_items = 0
    use_key, use_sec = api_key, api_secret
    for k, sec, label in candidates:
        got = try_bearer(k, sec)
        if not got:
            print(f"  {label}: auth failed")
            continue
        b, m = got
        c, n = graphql_probe(b)
        print(f"  {label}: mode={m} HTTP={c} items={n}")
        if 200 <= c < 300 and n > 0:
            bearer, mode, code, n_items = b, m, c, n
            use_key, use_sec = k, sec
            break
        if 200 <= c < 300 and not bearer:
            bearer, mode, code, n_items = b, m, c, n
            use_key, use_sec = k, sec

    if not bearer or not (200 <= code < 300) or n_items < 1:
        print("FAIL: GraphQL 未拿到有效榜单条目")
        return 1
    print(f"OK GraphQL: {n_items} items (mode={mode})")
    if args.no_sync:
        return 0

    db = SessionLocal()
    try:
        conn = db.scalar(
            select(ProductConnector)
            .where(ProductConnector.admin_source_key == "product_hunt")
            .order_by(ProductConnector.id)
        )
        if not conn:
            print("FAIL: no product_hunt connector in DB")
            return 1
        cfg = dict(conn.config_json or {})
        if mode == "direct_bearer" and access_direct and use_key == access_direct:
            cfg["api_key"] = access_direct
            cfg.pop("oauth_client_secret", None)
        elif mode == "oauth_exchange":
            cfg["api_key"] = use_key
            cfg["oauth_client_secret"] = use_sec
        else:
            cfg["api_key"] = use_key or api_key
            if use_sec:
                cfg["oauth_client_secret"] = use_sec
            else:
                cfg.pop("oauth_client_secret", None)
        conn.config_json = cfg
        conn.enabled = True
        conn.min_interval_seconds = 0
        db.flush()

        before = db.scalar(
            select(func.count()).select_from(Article).where(Article.third_party_source.like("%product_hunt%"))
        )
        out = run_connector_sync(db, conn.id, actor="local-ph-script", bypass_rate_limit=True)
        db.commit()
        after = db.scalar(
            select(func.count()).select_from(Article).where(Article.third_party_source.like("%product_hunt%"))
        )
        log = db.scalar(select(ProductConnectorLog).order_by(ProductConnectorLog.id.desc()).limit(1))
        print("sync:", {k: out.get(k) for k in ("articles_created", "error", "http_status") if k in out})
        print(f"articles product_hunt: {before} -> {after}")
        if log:
            print(f"log: status={log.status} rows={log.rows_ingested}")
        if out.get("error"):
            return 3
        return 0 if int(out.get("articles_created") or 0) > 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
