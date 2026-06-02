#!/usr/bin/env python3
"""SSH 执行：清理日志 + 美东当日飞书摘要。"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ENV_FILE = SCRIPTS / "ssh_local.env"
SCRIPT = SCRIPTS / "_cleanup_logs_and_usa_digest_remote.py"


def main() -> int:
    if ENV_FILE.is_file():
        for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    host = (os.environ.get("AITRENDS_DEPLOY_HOST") or "").strip()
    user = (os.environ.get("AITRENDS_DEPLOY_USER") or "ubuntu").strip()
    password = (os.environ.get("AITRENDS_DEPLOY_SSH_PASSWORD") or "").strip()
    key_path = (os.environ.get("AITRENDS_DEPLOY_KEY_PATH") or "").strip()
    port = int((os.environ.get("AITRENDS_DEPLOY_SSH_PORT") or "22").strip() or "22")
    repo = (os.environ.get("AITRENDS_DEPLOY_DIR") or "/opt/aisoul").strip()
    if not host or not SCRIPT.is_file():
        return 2
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kw: dict = {"hostname": host, "port": port, "username": user, "timeout": 90}
    if key_path and Path(key_path).expanduser().is_file():
        connect_kw["key_filename"] = str(Path(key_path).expanduser())
    elif password:
        connect_kw["password"] = password
    else:
        return 2
    client.connect(**connect_kw)
    payload = base64.b64encode(SCRIPT.read_bytes()).decode("ascii")
    remote = "/tmp/aitrends_cleanup_logs.py"
    shell = f"""set -euo pipefail
cd {repo}
echo {payload} | base64 -d > {remote}
export PYTHONPATH={repo}
.venv/bin/python {remote}
rm -f {remote}
"""
    _, stdout, stderr = client.exec_command(shell, timeout=600)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
