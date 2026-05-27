#!/usr/bin/env python3
"""
从 backend/.env（优先）或当前环境变量读取 AITRENDS_LLM_*，向 DeepSeek OpenAI 兼容接口发一条最小请求，用于验证 Key / base / model。

用法（在仓库根目录）:
  py scripts/test_deepseek_env.py

勿将含真密钥的 .env.example 提交 Git；真密钥只放在 backend/.env（已在 .gitignore）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_BACKEND = ROOT / "backend" / ".env"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main() -> int:
    _load_env_file(ENV_BACKEND)

    base = (os.environ.get("AITRENDS_LLM_BASE_URL") or "https://api.deepseek.com/v1").strip().rstrip("/")
    key = (os.environ.get("AITRENDS_LLM_API_KEY") or "").strip()
    model = (os.environ.get("AITRENDS_LLM_MODEL") or "deepseek-v4-flash").strip()

    if not key:
        print("未找到 AITRENDS_LLM_API_KEY。请在 backend/.env 中填写，或导出到环境变量。", file=sys.stderr)
        print(f"已读取: {ENV_BACKEND}（存在则已加载）", file=sys.stderr)
        return 2

    url = f"{base}/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复两个字：收到"}],
        "max_tokens": 32,
        "temperature": 0,
    }

    try:
        import httpx

        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=60.0,
        )
    except Exception as e:
        print(f"请求异常: {e}", file=sys.stderr)
        return 1

    print(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception:
        print(r.text[:800])
        return 1 if r.status_code >= 400 else 0

    if r.status_code >= 400:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1200])
        return 1

    try:
        msg = data["choices"][0]["message"]["content"]
        print("模型回复:", (msg or "").strip())
    except (KeyError, IndexError):
        print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
    print("OK: DeepSeek（OpenAI 兼容）配置可用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
