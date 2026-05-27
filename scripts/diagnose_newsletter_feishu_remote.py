#!/usr/bin/env python3
"""远端排查每日摘要 / 飞书推送（SSH 执行，不打印 Webhook 明文）。"""
from __future__ import annotations

import argparse
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE_PY = r"""
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.getcwd())
os.chdir(os.environ.get("AITRENDS_REPO", "/opt/aisoul"))

from sqlalchemy import select, text
from backend.app.db import SessionLocal
from backend.app.models import NewsletterDailyDigest
from backend.app.newsletter_settings_service import get_newsletter_settings_merged, get_newsletter_settings_public
from backend.app.us_content_calendar import US_CONTENT_TZ, us_calendar_today

us_today = us_calendar_today().isoformat()
now_us = datetime.now(US_CONTENT_TZ)
db = SessionLocal()
try:
    s = get_newsletter_settings_merged(db)
    pub = get_newsletter_settings_public(db)
    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == us_today))
    print("=== US now ===")
    print(now_us.isoformat())
    print("digest_date (US):", us_today)
    print("=== newsletter settings (safe) ===")
    for k in (
        "cron_enabled",
        "generate_enabled",
        "send_enabled",
        "feishu_enabled",
        "daily_digest_job_enabled",
        "daily_hour",
        "daily_minute",
        "has_feishu_webhook",
        "feishu_webhook_masked",
        "has_smtp_password",
    ):
        print(f"  {k}: {pub.get(k, s.get(k))}")
    h, m = int(s.get("daily_hour", 9)), int(s.get("daily_minute", 0))
    slot_start = now_us.replace(hour=h, minute=m, second=0, microsecond=0)
    slot_end = slot_start.replace() + __import__("datetime").timedelta(minutes=5)
    in_slot = slot_start <= now_us < slot_end
    print(f"  scheduler_slot_US: {h:02d}:{m:02d}–{h:02d}:{m+5:02d}  in_slot_now={in_slot}")
    print("=== today digest row ===")
    if not row:
        print("  (no row for today)")
    else:
        print("  status:", row.status)
        print("  subject:", (row.subject or "")[:80])
        print("  body_len:", len(row.body_md or ""))
        print("  sent_at:", row.sent_at)
        print("  feishu_sent_at:", row.feishu_sent_at)
        print("  error_message:", row.error_message)
    recent = db.execute(
        text(
            "SELECT digest_date, status, feishu_sent_at, sent_at, "
            "substr(coalesce(error_message,''),1,120) AS err "
            "FROM newsletter_daily_digests ORDER BY digest_date DESC LIMIT 5"
        )
    ).fetchall()
    print("=== last 5 digests ===")
    for r in recent:
        print(" ", dict(r._mapping))
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
    inner = REMOTE_PY.replace('os.environ.get("AITRENDS_REPO", "/opt/aitrends")', shlex.quote(args.repo))
    cmd = (
        f"cd {shlex.quote(args.repo)} && "
        f"(test -d .venv && source .venv/bin/activate; true) && "
        f"python3 -c {shlex.quote(inner)}"
    )
    os.execv(sys.executable, [sys.executable, str(deploy), "--cmd", cmd])


if __name__ == "__main__":
    raise SystemExit(main())
