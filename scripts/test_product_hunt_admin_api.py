"""通过本地管理端 API 测试 Product Hunt 数据源（需 uvicorn 已启动且可连库）。

用法（仓库根目录）:
  py -3.12 scripts/test_product_hunt_admin_api.py
  py -3.12 scripts/test_product_hunt_admin_api.py --base http://127.0.0.1:8000 --user admin --password admin123456
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000", help="API 根地址")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="admin123456")
    args = p.parse_args()
    base = args.base.rstrip("/")

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        try:
            login = client.post(
                f"{base}/api/admin/v1/auth/login",
                json={"username": args.user, "password": args.password},
            )
        except httpx.ConnectError as e:
            print(f"FAIL: 无法连接 {base} — {e}")
            print("请确认已启动: py -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000")
            return 1

        if login.status_code != 200:
            print(f"FAIL: 登录 HTTP {login.status_code}\n{login.text[:500]}")
            return 1
        login_body = login.json()
        if login_body.get("code") not in (0, None) and "data" not in login_body:
            print(f"FAIL: 登录响应异常\n{json.dumps(login_body, ensure_ascii=False)[:400]}")
            return 1

        test = client.post(
            f"{base}/api/admin/v1/sources/test",
            json={"source": "product_hunt"},
        )
        print(f"POST /sources/test → HTTP {test.status_code}")
        try:
            body = test.json()
        except json.JSONDecodeError:
            print(f"FAIL: 非 JSON\n{test.text[:600]}")
            return 1
        print(json.dumps(body, ensure_ascii=False, indent=2)[:2000])
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict):
            ok = data.get("ok")
            status = data.get("http_status") or data.get("status_code")
            snippet = (data.get("body_snippet") or data.get("snippet") or "")[:200]
            print(f"\nok={ok} http_status={status} snippet={snippet!r}")
            if ok:
                return 0
        if test.status_code == 200 and isinstance(body, dict) and body.get("code") == 0:
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
