#!/usr/bin/env python3
"""
通过 SSH 在云主机执行部署命令（密码或私钥）。仓库内不写任何密码。

依赖:
  pip install paramiko
  或: pip install -e ".[deploy]"

环境变量（推荐）:
  AITRENDS_DEPLOY_HOST          必填，公网 IP 或域名
  AITRENDS_DEPLOY_USER          默认 ubuntu
  AITRENDS_DEPLOY_SSH_PASSWORD  可选；不设则在交互终端里隐式输入
  AITRENDS_DEPLOY_KEY_PATH      可选；若设置则优先用密钥登录（如 ~/.ssh/id_rsa）
  AITRENDS_DEPLOY_KEY_PASSPHRASE  加密私钥时的口令，可选
  AITRENDS_DEPLOY_DIR           默认 /opt/aitrends
  AITRENDS_DEPLOY_GIT_BRANCH    默认 main
  AITRENDS_DEPLOY_SYSTEMD_UNIT  默认 aitrends-backend（按你机器上实际 unit 名改）

示例（PowerShell，密码用环境变量仅当前会话，勿写入脚本文件）:
  $env:AITRENDS_DEPLOY_HOST="1.2.3.4"
  $env:AITRENDS_DEPLOY_SSH_PASSWORD="你的密码"
  py scripts/deploy_ssh.py

仅执行自定义远程命令:
  py scripts/deploy_ssh.py --cmd "cd /opt/aitrends && git status"

首次 Linux 虚拟机建议先在机器上跑: bash scripts/bootstrap_linux_vm.sh（见 docs/deploy-tencent-cvm.md §0）

远端 `git pull` 之后的固定步骤在 **scripts/vm_deploy.sh**（与 deploy_ssh、GitHub Actions 共用）。

本机交互登录（密码放 scripts/ssh_local.env，勿提交）: py scripts/ssh_connect.py（见 scripts/ssh_local.env.example）
"""
from __future__ import annotations

import argparse
import getpass
import os
import shlex
import sys
from pathlib import Path


def _load_ssh_local_env() -> None:
    """若存在 scripts/ssh_local.env（gitignore），且变量尚未导出，则加载（见 ssh_local.env.example）。"""
    p = Path(__file__).resolve().parent / "ssh_local.env"
    if not p.is_file():
        return
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _require_paramiko():
    try:
        import paramiko  # noqa: F401
    except ImportError:
        print(
            '缺少 paramiko。请执行: pip install paramiko  或  pip install -e ".[deploy]"',
            file=sys.stderr,
        )
        sys.exit(2)
    return __import__("paramiko")


def _password() -> str:
    p = os.environ.get("AITRENDS_DEPLOY_SSH_PASSWORD", "").strip()
    if p:
        return p
    if sys.stdin.isatty():
        return getpass.getpass("SSH 密码: ")
    print("非交互环境请设置环境变量 AITRENDS_DEPLOY_SSH_PASSWORD", file=sys.stderr)
    sys.exit(2)


def _default_remote_script(deploy_dir: str, branch: str, unit: str) -> str:
    return f"""set -euo pipefail
cd {shlex.quote(deploy_dir)}
if [[ ! -f backend/app/main.py ]]; then
  echo "deploy: 当前目录不是 AiTrends 仓库根（缺少 backend/app/main.py）: $(pwd)" >&2
  exit 2
fi
git fetch origin {shlex.quote(branch)}
git reset --hard {shlex.quote(f"origin/{branch}")}
if [[ ! -f scripts/vm_deploy.sh ]]; then
  echo "deploy: git pull 后仍无 scripts/vm_deploy.sh，请检查远端分支与仓库内容: $(pwd)" >&2
  ls -la scripts 2>/dev/null || true
  exit 2
fi
export AITRENDS_DEPLOY_SYSTEMD_UNIT={shlex.quote(unit)}
bash scripts/vm_deploy.sh
"""


def _configure_stdio_utf8() -> None:
    """避免 Windows 默认 GBK 在打印 npm 等 UTF-8 日志时崩溃。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _configure_stdio_utf8()
    _load_ssh_local_env()
    paramiko = _require_paramiko()
    ap = argparse.ArgumentParser(description="SSH 部署 / 远程执行（凭据来自环境或 getpass）")
    ap.add_argument("--host", default=os.environ.get("AITRENDS_DEPLOY_HOST"), help="或设 AITRENDS_DEPLOY_HOST")
    ap.add_argument("--user", default=os.environ.get("AITRENDS_DEPLOY_USER", "ubuntu"))
    ap.add_argument("--dir", default=os.environ.get("AITRENDS_DEPLOY_DIR", "/opt/aitrends"))
    ap.add_argument("--branch", default=os.environ.get("AITRENDS_DEPLOY_GIT_BRANCH", "main"))
    ap.add_argument(
        "--systemd-unit",
        default=os.environ.get("AITRENDS_DEPLOY_SYSTEMD_UNIT", "aitrends-backend"),
        help="或设 AITRENDS_DEPLOY_SYSTEMD_UNIT",
    )
    ap.add_argument(
        "--cmd",
        default="",
        help="若指定则只执行该远程命令（bash -lc），忽略默认部署脚本",
    )
    ap.add_argument("--port", type=int, default=int(os.environ.get("AITRENDS_DEPLOY_SSH_PORT", "22")))
    ap.add_argument(
        "--identity-file",
        default=os.environ.get("AITRENDS_DEPLOY_KEY_PATH", ""),
        help="或设 AITRENDS_DEPLOY_KEY_PATH；与密码二选一（优先密钥）",
    )
    args = ap.parse_args()
    if not args.host:
        ap.error("请提供 --host 或环境变量 AITRENDS_DEPLOY_HOST")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    key_path = (args.identity_file or "").strip()
    if key_path:
        p = Path(key_path).expanduser()
        if not p.is_file():
            print(f"私钥文件不存在: {p}", file=sys.stderr)
            return 2
        passphrase = os.environ.get("AITRENDS_DEPLOY_KEY_PASSPHRASE") or None
        key = None
        for loader in (
            paramiko.RSAKey.from_private_key_file,
            paramiko.Ed25519Key.from_private_key_file,
            paramiko.ECDSAKey.from_private_key_file,
        ):
            try:
                key = loader(str(p), password=passphrase)
                break
            except Exception:
                continue
        if key is None:
            print("无法加载私钥（格式或口令不对）", file=sys.stderr)
            return 2
        client.connect(
            hostname=args.host,
            port=args.port,
            username=args.user,
            pkey=key,
            timeout=30,
            banner_timeout=30,
        )
    else:
        client.connect(
            hostname=args.host,
            port=args.port,
            username=args.user,
            password=_password(),
            timeout=30,
            banner_timeout=30,
        )

    if args.cmd.strip():
        remote = args.cmd.strip()
    else:
        remote = _default_remote_script(args.dir, args.branch, args.systemd_unit)

    quoted = shlex.quote(remote)
    stdin, stdout, stderr = client.exec_command(f"bash -lc {quoted}", get_pty=True)
    stdin.close()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    status = stdout.channel.recv_exit_status()
    client.close()

    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if status != 0:
        print(f"\n远程退出码: {status}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
