#!/usr/bin/env python3
"""本机 SSH：在 VM 上重新生成并推送今日飞书摘要（带 systemd 环境变量）。"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
code = (ROOT / "scripts" / "remote_feishu_repush.py").read_bytes()
b64 = base64.b64encode(code).decode()
remote = (
    "cd /opt/aisoul && . .venv/bin/activate && "
    "eval \"$(systemctl show aisoul-backend -p Environment --value | tr ' ' '\\n' | sed 's/^/export /')\" && "
    f"python3 -c \"import base64; exec(base64.b64decode('{b64}').decode()); "
    "import runpy; runpy.run_path('scripts/remote_feishu_repush.py')\""
)
# remote_feishu_repush is a script with main - use exec of file content instead
remote = (
    "cd /opt/aisoul && . .venv/bin/activate && "
    "eval \"$(systemctl show aisoul-backend -p Environment --value | tr ' ' '\\n' | sed 's/^/export /')\" && "
    "python3 scripts/remote_feishu_repush.py"
)
cmd = [sys.executable, str(ROOT / "scripts" / "deploy_ssh.py"), "--cmd", remote]
raise SystemExit(subprocess.run(cmd).returncode)
