"""
探测 MAINSTREAM_ADMIN_SOURCE_PRESETS：各 URL 响应长度，以及在 800 / 12000 /
CONNECTOR_SNIPPET_MAX_CHARS 截断下是否为合法 JSON（与连接器历史截断行为对照）。

用法（在 backend 目录下）:
  python scripts/audit_preset_response_truncation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.domain.articles import CONNECTOR_SNIPPET_MAX_CHARS  # noqa: E402
from app.services import MAINSTREAM_ADMIN_SOURCE_PRESETS  # noqa: E402

HEADERS = {
    "User-Agent": "AiTrends-PresetTruncationAudit/1.0",
    "Accept": "application/json, application/xml, text/xml, */*",
}


def _try_json(s: str) -> tuple[bool, str]:
    s = s.strip()
    if not s:
        return False, "empty"
    try:
        json.loads(s)
        return True, ""
    except json.JSONDecodeError as e:
        return False, str(e)[:120]


def main() -> int:
    cuts = (800, 12_000, CONNECTOR_SNIPPET_MAX_CHARS)
    cap_k = max(1, CONNECTOR_SNIPPET_MAX_CHARS // 1024)
    rows: list[dict] = []
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        src = row["source"]
        url = (row.get("api_base") or "").strip()
        if not url:
            rows.append({"source": src, "error": "empty api_base"})
            continue
        try:
            with httpx.Client(timeout=90.0, follow_redirects=True) as client:
                r = client.get(url, headers=HEADERS)
            text = r.text or ""
            n = len(text)
            head = text.lstrip()[:1]
            looks_json = head in ("{", "[")
            entry: dict = {
                "source": src,
                "http": r.status_code,
                "bytes": n,
                "looks_json": looks_json,
            }
            for c in cuts:
                prefix = text[: min(c, n)]
                ok, err = _try_json(prefix)
                entry[f"json_ok_{c}"] = ok if n else False
                if not ok and n:
                    entry[f"json_err_{c}"] = err
            full_ok, full_err = _try_json(text)
            entry["json_ok_full"] = full_ok
            if not full_ok and looks_json:
                entry["json_err_full"] = full_err
            rows.append(entry)
        except Exception as e:
            rows.append({"source": src, "http": 0, "error": repr(e)[:200]})

    # 打印表格
    print(f"预设条数: {len(MAINSTREAM_ADMIN_SOURCE_PRESETS)}  CONNECTOR_SNIPPET_MAX_CHARS={CONNECTOR_SNIPPET_MAX_CHARS}\n")
    hdr = f"{'source':<22} {'http':>4} {'bytes':>8}  json?  {'800':>5} {'12k':>5} {str(cap_k) + 'k':>5}  full"
    print(hdr)
    print("-" * len(hdr))
    for e in rows:
        if "error" in e and "http" not in e:
            print(f"{e.get('source','?'):<22}  ERR {e.get('error','')}")
            continue
        src = e["source"]
        http = e.get("http", 0)
        b = e.get("bytes", 0)
        lj = "Y" if e.get("looks_json") else "N"
        j800 = "Y" if e.get("json_ok_800") else ("—" if b == 0 else "n")
        j12 = "Y" if e.get("json_ok_12000") else ("—" if b == 0 else "n")
        j65 = "Y" if e.get(f"json_ok_{CONNECTOR_SNIPPET_MAX_CHARS}") else ("—" if b == 0 else "n")
        jf = "Y" if e.get("json_ok_full") else ("—" if not e.get("looks_json") else "n")
        print(f"{src:<22} {http:4} {b:8}    {lj}    {j800:>5} {j12:>5} {j65:>5}    {jf:>4}")

    print("\n说明:")
    print("  json?= 整段响应是否以 { 或 [ 开头（粗判为 JSON API）")
    print(f"  800/12k/{cap_k}k = 截取前 N 字符后 json.loads 是否成功（{cap_k}k 列为 CONNECTOR_SNIPPET_MAX_CHARS）")
    print("  full = 整段文本 json.loads（仅对 JSON 有意义；XML/RSS 整段不会是合法 JSON）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
