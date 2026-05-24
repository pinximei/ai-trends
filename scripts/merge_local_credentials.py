"""将 local/*.credentials 与 backend/.env 中的 LLM 合并为 local/credentials（不打印明文）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local"
OUT = LOCAL / "credentials"
EXAMPLE = LOCAL / "credentials.example"

sys.path.insert(0, str(ROOT / "scripts"))
from load_local_credentials import _parse_credentials_file, merged_credentials_kv  # noqa: E402


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    kv: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and not k.startswith("#"):
            kv[k.upper()] = v
    return kv


def build_merged_kv() -> dict[str, str]:
    merged_credentials_kv.cache_clear()
    kv = dict(merged_credentials_kv())
    env = _load_env_file(ROOT / "backend" / ".env")
    for k in (
        "AITRENDS_LLM_API_KEY",
        "AISOU_LLM_API_KEY",
        "AITRENDS_LLM_BASE_URL",
        "AISOU_LLM_BASE_URL",
        "AITRENDS_LLM_MODEL",
        "AISOU_LLM_MODEL",
    ):
        if env.get(k) and not kv.get(k):
            kv[k] = env[k]
    return {k: v for k, v in kv.items() if (v or "").strip()}


def write_credentials(path: Path, kv: dict[str, str]) -> None:
    """按 example 顺序写出，并附带 example 中的注释头。"""
    header = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.is_file() else ""
    lines: list[str] = []
    if header.strip():
        lines.extend(header.splitlines())
        lines.append("")
    lines.append("# —— 以下由 merge_local_credentials.py 自动生成/更新 ——")
    order = [
        "AITRENDS_LLM_API_KEY",
        "AISOU_LLM_API_KEY",
        "AITRENDS_LLM_BASE_URL",
        "AISOU_LLM_BASE_URL",
        "AITRENDS_LLM_MODEL",
        "AISOU_LLM_MODEL",
        "NEWSAPI_KEY",
        "AITRENDS_NEWSAPI_KEY",
        "THENEWSAPI_API_TOKEN",
        "THENEWSAPI_TOKEN",
        "AITRENDS_THENEWSAPI_TOKEN",
        "PRODUCT_HUNT_API_KEY",
        "PRODUCT_HUNT_CLIENT_ID",
        "PRODUCT_HUNT_APP_SECRET",
        "PRODUCT_HUNT_CLIENT_SECRET",
        "PRODUCT_HUNT_ACCESS_TOKEN",
    ]
    written: set[str] = set()
    for key in order:
        val = (kv.get(key) or "").strip()
        if val:
            lines.append(f"{key}={val}")
            written.add(key)
    for key in sorted(kv):
        if key not in written and (kv[key] or "").strip():
            lines.append(f"{key}={kv[key].strip()}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    kv = build_merged_kv()
    if not kv:
        print("FAIL: 未找到任何凭据（请检查 local/*.credentials 与 backend/.env）")
        return 1
    write_credentials(OUT, kv)
    keys_present = sorted(k for k, v in kv.items() if (v or "").strip())
    print(f"已写入 {OUT}（{len(keys_present)} 个键，不显示明文）")
    for k in keys_present:
        print(f"  - {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
