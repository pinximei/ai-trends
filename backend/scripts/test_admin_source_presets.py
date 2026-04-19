"""
批量探测 MAINSTREAM_ADMIN_SOURCE_PRESETS 中 api_base 的 HTTP 可达性（无密钥）。
与后台「测试连接」一致：2xx–3xx，或 401/403/405/429 视为可达。

用法（在 backend 目录下）:
  python scripts/test_admin_source_presets.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.services import MAINSTREAM_ADMIN_SOURCE_PRESETS  # noqa: E402


def _ok_code(code: int) -> bool:
    return (200 <= code < 400) or code in (401, 403, 405, 429)


def main() -> int:
    failed: list[tuple[str, str, int | str]] = []
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        url = (row.get("api_base") or "").strip()
        src = row.get("source", "?")
        if not url:
            failed.append((src, "", "empty api_base"))
            print(f"FAIL {src} (empty api_base)")
            continue
        try:
            r = httpx.get(
                url,
                timeout=25.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "AISoul-Admin-SourceTest/1.0",
                    "Accept": "application/json, */*",
                },
            )
            if _ok_code(r.status_code):
                print(f"OK   {src} HTTP {r.status_code}")
            else:
                failed.append((src, url, r.status_code))
                print(f"FAIL {src} HTTP {r.status_code} {url[:90]}")
        except Exception as e:
            failed.append((src, url, repr(e)))
            print(f"FAIL {src} ERR {e!s}")

    if failed:
        print(f"\n共 {len(failed)} 条未通过（共 {len(MAINSTREAM_ADMIN_SOURCE_PRESETS)} 条预设）。")
        return 1
    print(f"\n全部 {len(MAINSTREAM_ADMIN_SOURCE_PRESETS)} 条预设探测通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
