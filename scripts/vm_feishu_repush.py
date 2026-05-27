#!/usr/bin/env python3
"""Production VM: repush today's Feishu digest. Usage: cd /opt/aisoul && .venv/bin/python scripts/vm_feishu_repush.py"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_systemd_env(unit: str = "aisoul-backend") -> None:
    if os.environ.get("AITRENDS_DATABASE_URL"):
        return
    try:
        raw = subprocess.check_output(
            ["systemctl", "show", unit, "-p", "Environment", "--value"],
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.CalledProcessError):
        return
    for token in shlex.split(raw.strip()):
        if "=" in token:
            k, v = token.split("=", 1)
            os.environ.setdefault(k, v)

from sqlalchemy import select

from backend.app.application.newsletter_daily_digest import run_daily_newsletter_digest_job
from backend.app.db import SessionLocal
from backend.app.models import NewsletterDailyDigest
from backend.app.newsletter_settings_service import get_newsletter_settings_merged
from backend.app.us_content_calendar import us_calendar_today


def main() -> int:
    _load_systemd_env()
    db = SessionLocal()
    try:
        key = us_calendar_today().isoformat()
        row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == key))
        if row and row.feishu_sent_at is not None:
            row.feishu_sent_at = None
            db.commit()
        settings = get_newsletter_settings_merged(db)
        out = run_daily_newsletter_digest_job(
            db=db,
            settings=settings,
            digest_date=key,
            manual_run=True,
            push_only=True,
        )
        print("digest_date:", key)
        print("result:", out)
        return 0 if out.get("feishu_sent") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
