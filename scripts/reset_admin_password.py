#!/usr/bin/env python3
"""
在数据库中重置后台管理员密码（需在应用同一套 AITRENDS_DATABASE_URL 的环境下运行）。

典型用法（云主机 /opt/aitrends，已 venv + pip install -e .）:

  cd /opt/aitrends
  source .venv/bin/activate
  py scripts/reset_admin_password.py
  py scripts/reset_admin_password.py --username admin

说明:
  - 生产环境首次建号用的是 AITRENDS_ADMIN_INIT_*，不是 admin123456。
  - 本脚本会清除失败次数与锁定时间，避免「多次输错被锁」导致无法登录。
"""
from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from sqlalchemy import select

    from backend.app.admin_auth import hash_password
    from backend.app.db import SessionLocal
    from backend.app.models import AdminUser

    ap = argparse.ArgumentParser(description="重置后台管理员密码")
    ap.add_argument("--username", default="admin", help="管理员用户名，默认 admin")
    args = ap.parse_args()

    p1 = getpass.getpass("新密码: ")
    p2 = getpass.getpass("再输入一次: ")
    if not p1:
        print("密码不能为空", file=sys.stderr)
        return 2
    if p1 != p2:
        print("两次输入不一致", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        user = db.scalar(select(AdminUser).where(AdminUser.username == args.username))
        if not user:
            print(f"未找到用户: {args.username}", file=sys.stderr)
            return 1
        user.password_hash = hash_password(p1)
        user.failed_attempts = 0
        user.locked_until = None
        user.updated_at = datetime.utcnow()
        db.commit()
        print(f"已重置用户 {args.username!r} 的密码，请用新密码登录后台。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
