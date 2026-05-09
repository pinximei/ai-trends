#!/usr/bin/env python3
"""
修复旧版 Nginx 片段（仅当线上仍是「alias + try_files /admin/index.html」时）。

日常请以仓库标准配置为准，使用：
  py scripts/apply_nginx_cloud.py

用法（在仓库根目录，需已 pip install paramiko）:
  AITRENDS_DEPLOY_HOST=... AITRENDS_DEPLOY_USER=ubuntu AITRENDS_DEPLOY_SSH_PASSWORD=... \\
  py scripts/patch_nginx_admin_spa.py

默认改 /etc/nginx/sites-available/aitrends；可用 AITRENDS_NGINX_SITE=文件名（不含路径）覆盖。
"""
from __future__ import annotations

import base64
import os
import re
import sys

# 兼容行尾空格或细微差异
OLD_PATTERN = re.compile(
    r"\n    location /admin/ \{\n"
    r"        alias /opt/aitrends/frontend/admin/dist/;\n"
    r"        try_files \$uri \$uri/ /admin/index\.html;\n"
    r"    \}",
)

NEW = """    location = /admin {
        return 301 /admin/;
    }

    location = /admin/index.html {
        alias /opt/aitrends/frontend/admin/dist/index.html;
    }

    location ^~ /admin/ {
        alias /opt/aitrends/frontend/admin/dist/;
        try_files $uri $uri/ @admin_spa_fallback;
    }

    location @admin_spa_fallback {
        rewrite ^ /admin/index.html last;
    }"""


def main() -> int:
    try:
        import paramiko
    except ImportError:
        print("pip install paramiko", file=sys.stderr)
        return 2

    host = os.environ.get("AITRENDS_DEPLOY_HOST")
    user = os.environ.get("AITRENDS_DEPLOY_USER", "ubuntu")
    password = os.environ.get("AITRENDS_DEPLOY_SSH_PASSWORD", "")
    site_name = os.environ.get("AITRENDS_NGINX_SITE", "aitrends")
    site = f"/etc/nginx/sites-available/{site_name}"
    if not host or not password:
        print("需要 AITRENDS_DEPLOY_HOST 与 AITRENDS_DEPLOY_SSH_PASSWORD", file=sys.stderr)
        return 2

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(hostname=host, username=user, password=password, timeout=25)

    def run(cmd: str) -> tuple[int, str, str]:
        _, stdout, stderr = c.exec_command(cmd, get_pty=True)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), out, err

    code, out, err = run(f"sudo base64 -w0 {site} 2>/dev/null || sudo base64 {site} 2>/dev/null")
    if code != 0:
        print(err or out, file=sys.stderr)
        c.close()
        return 1
    raw = (out + err).strip().splitlines()[-1] if (out + err).strip() else ""
    try:
        text = base64.b64decode(raw).decode("utf-8")
    except Exception as e:
        print(f"解码站点文件失败: {e}", file=sys.stderr)
        c.close()
        return 1
    m = OLD_PATTERN.search(text)
    if not m:
        print("未找到预期片段，可能已修过或路径不同；请手动检查。", file=sys.stderr)
        c.close()
        return 1

    new_text = OLD_PATTERN.sub("\n" + NEW, text, count=1)
    b64 = base64.b64encode(new_text.encode("utf-8")).decode("ascii")

    for cmd in (
        "sudo mkdir -p /var/backups/nginx",
        f"sudo test -f {site} && sudo cp {site} /var/backups/nginx/{site_name}.$(date +%s) || true",
        f"echo {b64} | base64 -d | sudo tee {site} > /dev/null",
        f"sudo ln -sf {site} /etc/nginx/sites-enabled/{site_name}",
        "sudo rm -f /etc/nginx/sites-enabled/*.bak* 2>/dev/null || true",
        "sudo nginx -t",
        "sudo systemctl reload nginx",
    ):
        code, out, err = run(cmd)
        sys.stdout.write(out)
        sys.stderr.write(err)
        if code != 0:
            print(f"命令失败 (exit {code}): {cmd}", file=sys.stderr)
            c.close()
            return 1

    code, out, err = run(
        "curl -sI -m 10 https://www.ai-trends.news/admin/ 2>&1 | head -12; "
        "echo '---'; curl -s https://www.ai-trends.news/admin/ 2>&1 | head -3"
    )
    sys.stdout.write(out)
    sys.stderr.write(err)
    c.close()
    print("完成：已 reload nginx。请浏览器强刷 /admin/ 验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
