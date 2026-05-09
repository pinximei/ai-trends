#!/usr/bin/env python3
"""
从本机 **scripts/ssh_local.env**（勿提交，见 .gitignore）读取 SSH 变量，用 Paramiko 打开交互 shell。

与 deploy_ssh.py 使用相同变量名：AITRENDS_DEPLOY_HOST / AITRENDS_DEPLOY_USER /
AITRENDS_DEPLOY_SSH_PASSWORD / AITRENDS_DEPLOY_SSH_PORT。

准备步骤:
  1. copy scripts\\ssh_local.env.example scripts\\ssh_local.env
  2. 编辑 ssh_local.env 填入主机、密码等
  3. py scripts/ssh_connect.py

依赖: pip install paramiko
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / "ssh_local.env"


def _load_env_file() -> None:
    if not ENV_FILE.is_file():
        print(f"缺少 {ENV_FILE}。请复制 ssh_local.env.example 为 ssh_local.env 并填写。", file=sys.stderr)
        raise SystemExit(2)
    for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _require_paramiko():
    try:
        import paramiko  # noqa: F401
    except ImportError:
        print("请安装: pip install paramiko", file=sys.stderr)
        raise SystemExit(2)
    return __import__("paramiko")


def main() -> int:
    _load_env_file()
    host = (os.environ.get("AITRENDS_DEPLOY_HOST") or "").strip()
    user = (os.environ.get("AITRENDS_DEPLOY_USER") or "ubuntu").strip()
    password = (os.environ.get("AITRENDS_DEPLOY_SSH_PASSWORD") or "").strip()
    port = int((os.environ.get("AITRENDS_DEPLOY_SSH_PORT") or "22").strip() or "22")
    if not host:
        print("ssh_local.env 中需设置 AITRENDS_DEPLOY_HOST", file=sys.stderr)
        return 2
    if not password:
        print("ssh_local.env 中需设置 AITRENDS_DEPLOY_SSH_PASSWORD（或改用密钥 + deploy_ssh.py）", file=sys.stderr)
        return 2

    paramiko = _require_paramiko()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=user, password=password, timeout=30, banner_timeout=30)

    chan = client.invoke_shell(term="xterm", width=160, height=48)
    chan.settimeout(0.0)

    def pump_out() -> None:
        while True:
            try:
                if chan.recv_ready():
                    data = chan.recv(4096)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                elif chan.closed:
                    break
            except Exception:
                break

    t = threading.Thread(target=pump_out, daemon=True)
    t.start()

    try:
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                break
            chan.send(line)
    except (BrokenPipeError, EOFError, KeyboardInterrupt):
        pass
    finally:
        chan.close()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
