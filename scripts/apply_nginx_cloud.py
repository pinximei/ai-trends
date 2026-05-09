#!/usr/bin/env python3
"""
将仓库内标准 Nginx 站点配置应用到云主机（sites-available + 仅符号链接在 sites-enabled）。

会执行：
  - 备份当前 /etc/nginx/sites-available/aitrends 到 /var/backups/nginx/
  - 写入新配置
  - 删除误放在 sites-enabled/ 下的 *.bak（避免 server_name 重复）
  - 确保 sites-enabled/aitrends -> sites-available/aitrends
  - nginx -t && systemctl reload nginx

环境变量（与 deploy_ssh.py 一致）:
  AITRENDS_DEPLOY_HOST, AITRENDS_DEPLOY_USER (默认 ubuntu), AITRENDS_DEPLOY_SSH_PASSWORD

可选:
  AITRENDS_NGINX_CONF   本地配置文件路径（默认仓库 deploy/nginx/aitrends.conf）
  AITRENDS_NGINX_SITE   远端站点文件名（默认 aitrends，即 .../sites-available/aitrends）
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _require_paramiko():
    try:
        import paramiko  # noqa: F401
    except ImportError:
        print("pip install paramiko", file=sys.stderr)
        sys.exit(2)
    return __import__("paramiko")


def main() -> int:
    paramiko = _require_paramiko()
    host = os.environ.get("AITRENDS_DEPLOY_HOST")
    user = os.environ.get("AITRENDS_DEPLOY_USER", "ubuntu")
    password = os.environ.get("AITRENDS_DEPLOY_SSH_PASSWORD", "")
    site = os.environ.get("AITRENDS_NGINX_SITE", "aitrends")
    local_conf = Path(os.environ.get("AITRENDS_NGINX_CONF", str(_repo_root() / "deploy" / "nginx" / "aitrends.conf")))
    if not host or not password:
        print("需要 AITRENDS_DEPLOY_HOST 与 AITRENDS_DEPLOY_SSH_PASSWORD", file=sys.stderr)
        return 2
    if not local_conf.is_file():
        print(f"找不到本地配置: {local_conf}", file=sys.stderr)
        return 2

    text = local_conf.read_text(encoding="utf-8")
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(hostname=host, username=user, password=password, timeout=25)

    def run(cmd: str) -> tuple[int, str, str]:
        _, stdout, stderr = c.exec_command(cmd, get_pty=True)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    avail = f"/etc/nginx/sites-available/{site}"
    enab = f"/etc/nginx/sites-enabled/{site}"

    steps = [
        "sudo mkdir -p /var/backups/nginx",
        f"sudo test -f {avail} && sudo cp {avail} /var/backups/nginx/{site}.$(date +%s) || true",
        f"echo {b64} | base64 -d | sudo tee {avail} > /dev/null",
        # 禁止在 sites-enabled 放裸文件备份（会当作独立 server 加载）
        "sudo rm -f /etc/nginx/sites-enabled/*.bak* /etc/nginx/sites-enabled/*.bak.* 2>/dev/null || true",
        f"sudo ln -sf {avail} {enab}",
        "sudo nginx -t",
        "sudo systemctl reload nginx",
    ]
    for cmd in steps:
        code, out, err = run(cmd)
        sys.stdout.write(out)
        sys.stderr.write(err)
        if code != 0:
            print(f"失败: {cmd}", file=sys.stderr)
            c.close()
            return 1

    code, out, err = run(
        "curl -sI -m 8 https://www.ai-trends.news/ | grep -i content-length; "
        "curl -sI -m 8 https://www.ai-trends.news/admin/ | grep -i content-length"
    )
    sys.stdout.write(out)
    sys.stderr.write(err)
    c.close()
    print("OK: 已按 deploy/nginx/aitrends.conf 写入并 reload。请浏览器验证 / 与 /admin/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
