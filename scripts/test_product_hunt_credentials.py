"""探测库内 Product Hunt 凭据与 GraphQL 拉取是否正常（不打印密钥明文）。

用法（仓库根目录）:
  py -3.12 scripts/test_product_hunt_credentials.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

import os  # noqa: E402

from backend.app.connector_heat_fetch import sync_product_hunt_top_details  # noqa: E402
from backend.app.db import SessionLocal  # noqa: E402
from backend.app.models import AdminSourceConfig  # noqa: E402
from backend.app.product_hunt_oauth import resolve_product_hunt_bearer  # noqa: E402
from backend.app.product_models import ProductConnector  # noqa: E402


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "(空)"
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def _test_with_token(api_key: str, oauth_secret: str) -> int:
    try:
        bearer, mode = resolve_product_hunt_bearer(api_key=api_key, oauth_client_secret=oauth_secret)
    except (ValueError, RuntimeError) as e:
        print(f"FAIL: 凭据解析失败: {e}")
        return 1
    print(f"鉴权模式: {mode} token_masked={_mask(bearer)}")
    headers = {
        "User-Agent": "AiTrends-ProductHuntTest/1.0",
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer}",
    }
    code, body = sync_product_hunt_top_details(headers)
    print(f"GraphQL 拉取 HTTP {code} body_len={len(body or '')}")
    if not (200 <= code < 300):
        print(f"FAIL: 非 2xx\n{(body or '')[:500]}")
        return 1
    data = json.loads(body)
    if isinstance(data, dict) and data.get("connector_sync_items_v1") is not None:
        n = len(data.get("connector_sync_items_v1") or [])
        print(f"OK: connector_sync_items_v1 条数={n}")
        return 0 if n > 0 else 2
    if isinstance(data, dict) and data.get("errors"):
        print(f"FAIL: GraphQL errors\n{json.dumps(data['errors'], ensure_ascii=False)[:500]}")
        return 1
    print("OK: 收到 JSON 响应")
    return 0


def main() -> int:
    env_key = (os.environ.get("PRODUCT_HUNT_API_KEY") or os.environ.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
    env_sec = (os.environ.get("PRODUCT_HUNT_APP_SECRET") or os.environ.get("PRODUCT_HUNT_CLIENT_SECRET") or "").strip()
    if env_key or env_sec:
        print("使用环境变量 PRODUCT_HUNT_API_KEY / PRODUCT_HUNT_APP_SECRET 测试（不连库）")
        return _test_with_token(env_key, env_sec)

    db = SessionLocal()
    try:
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "product_hunt"))
        if not src:
            print("FAIL: 库中无 product_hunt 数据源行")
            return 1
        print(f"数据源 enabled={src.enabled} api_base={(src.api_base or '')[:60]}")
        print(f"  admin api_key_masked={_mask(src.api_key_masked or '')}")
        print(f"  admin app_secret_masked={_mask(getattr(src, 'app_secret_masked', '') or '')}")

        conns = list(
            db.scalars(
                select(ProductConnector).where(ProductConnector.admin_source_key == "product_hunt")
            ).all()
        )
        if not conns:
            print("FAIL: 无 admin_source_key=product_hunt 的连接器")
            return 1
        for c in conns:
            cfg = dict(c.config_json or {})
            token = str(cfg.get("api_key") or "").strip()
            secret = str(cfg.get("oauth_client_secret") or "").strip()
            print(
                f"连接器 id={c.id} name={c.name!r} enabled={c.enabled} "
                f"has_api_key={bool(token)} has_oauth_client_secret={bool(secret)}"
            )
            if not token:
                print(
                    "FAIL: 连接器 config_json.api_key 为空。"
                    " Product Hunt 同步需要 Bearer access_token（不是仅 client_secret）。"
                    " 请在后台「API Key」栏保存 OAuth 换到的 access_token。"
                )
                return 1

            return _test_with_token(token, secret)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
