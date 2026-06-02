#!/usr/bin/env python3
"""生产：按根因归类 LLM 润色失败（skip_llm / llm_polish_retry）。"""
from __future__ import annotations

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REMOTE_PY = r"""
import re
import sys
from datetime import datetime, timedelta
from collections import Counter

sys.path.insert(0, '.')

from sqlalchemy import text
from backend.app.db import SessionLocal

db = SessionLocal()
since = datetime.utcnow() - timedelta(hours=72)
try:
    rows = db.execute(
        text(
            "SELECT source_key, step, message FROM product_sync_diagnostic_logs "
            "WHERE created_at>=:s AND step IN ('skip_llm_polish','llm_polish_retry') "
            "ORDER BY id DESC LIMIT 200"
        ),
        {"s": since},
    ).fetchall()

    def bucket(msg: str) -> str:
        m = msg or ""
        if "json_parse_failed" in m or "JSON 解析失败" in m:
            return "A_json_parse"
        if "tabs_count=0" in m or "Tab 个数不对" in m and "tabs_count=0" in m:
            return "B_tabs_empty"
        if "tabs_count=" in m and "tabs_count=0" not in m:
            return "C_tabs_partial"
        if "replication_analysis" in m:
            return "D_replication_analysis"
        if "tab_" in m and "_short" in m:
            return "E_tab_too_short"
        if "llm_http_failed" in m or "HTTP" in m and "repair_http" in m:
            return "F_llm_http"
        if "api_json_leak" in m or "API 字段" in m:
            return "G_api_leak"
        if "no_content_substantive" in m or "汉字" in m and "need>=" in m:
            return "H_substantive_cjk"
        if "bad_categories" in m:
            return "I_categories"
        if "summary_too_short" in m:
            return "J_summary_short"
        if "repair_parse=" in m:
            return "K_repair_parse_fail"
        if "validate_failed_after_retry" in m:
            return "L_after_retry_exhausted"
        return "Z_other"

    by_src: dict[str, Counter] = {}
    samples: dict[str, list] = {}
    for sk, step, msg in rows:
        sk = sk or "?"
        b = bucket(msg)
        by_src.setdefault(sk, Counter())[b] += 1
        samples.setdefault((sk, b), [])
        if len(samples[(sk, b)]) < 2:
            samples[(sk, b)].append((step, msg[:280]))

    print("TOTAL_ROWS", len(rows))
    for sk in sorted(by_src.keys()):
        print("SRC", sk, dict(by_src[sk]))
    print("=== SAMPLES ===")
    for (sk, b), items in sorted(samples.items()):
        print(f"-- {sk} / {b} --")
        for step, msg in items:
            print(step, msg.replace(chr(10), " ")[:260])

    llm = db.execute(
        text(
            "SELECT success, substr(coalesce(error_code,''),1,80), count(*) "
            "FROM product_llm_usage_logs "
            "WHERE scenario='article_ingest_polish' AND created_at>=:s "
            "GROUP BY 1,2 ORDER BY count(*) DESC LIMIT 15"
        ),
        {"s": since},
    ).fetchall()
    print("LLM_USAGE_72H", llm)

    cfg = db.execute(
        text("SELECT value_json FROM product_settings_kv WHERE key='llm' LIMIT 1")
    ).scalar()
    if isinstance(cfg, dict):
        print("LLM_MODEL", cfg.get("model") or cfg.get("default_model"))
        print("LLM_BASE", (cfg.get("api_base") or cfg.get("base_url") or "")[:60])
finally:
    db.close()
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/opt/aisoul")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    from deploy_ssh import _load_ssh_local_env  # noqa: PLC0415

    _load_ssh_local_env()
    deploy = ROOT / "scripts" / "deploy_ssh.py"
    unit = "/etc/systemd/system/aisoul-backend.service"
    py = f"{args.repo}/.venv/bin/python3"
    cmd = (
        f"cd {shlex.quote(args.repo)} && "
        f"while IFS= read -r line; do "
        f'case "$line" in Environment=*) export "${{line#Environment=}}";; esac; '
        f"done < {shlex.quote(unit)}; "
        f"PY={shlex.quote(py)}; test -x \"$PY\" || PY=python3; "
        f"\"$PY\" -c {shlex.quote(REMOTE_PY)}"
    )
    return subprocess.call([sys.executable, str(deploy), "--cmd", cmd])


if __name__ == "__main__":
    raise SystemExit(main())
