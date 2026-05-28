#!/usr/bin/env python3
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
code = (ROOT / "scripts" / "_remote_digest_body.py").read_bytes()
b64 = base64.b64encode(code).decode()
remote = (
    "cd /opt/aisoul && . .venv/bin/activate && "
    f"python3 -c \"import base64; exec(base64.b64decode('{b64}').decode())\""
)
raise SystemExit(
    subprocess.run([sys.executable, str(ROOT / "scripts" / "deploy_ssh.py"), "--cmd", remote]).returncode
)
