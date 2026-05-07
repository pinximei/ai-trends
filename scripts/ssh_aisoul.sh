#!/usr/bin/env bash
# 从本机或「云桌面」里的 Git Bash / WSL，用 SSH 连到 **Linux 虚拟机**（AISoul 跑在这台上）。
# 不在脚本里写密码；请用环境变量或 ssh-agent。
#
# 必填:
#   export AISOU_DEPLOY_HOST=虚拟机IP或域名
# 常用可选:
#   export AISOU_DEPLOY_USER=ubuntu
#   export AISOU_DEPLOY_SSH_PORT=22
#   export AISOU_DEPLOY_DIR=/opt/aisoul
#   export AISOU_DEPLOY_KEY_PATH=~/.ssh/id_ed25519
#   export AISOU_DEPLOY_SYSTEMD_UNIT=aisoul-backend
#
# 用法:
#   chmod +x scripts/ssh_aisoul.sh
#   ./scripts/ssh_aisoul.sh              # 默认：打开交互 shell
#   ./scripts/ssh_aisoul.sh login        # 同上，可再跟 ssh 的参数
#   ./scripts/ssh_aisoul.sh bootstrap    # 远端执行 bootstrap_linux_vm.sh（远端需已 clone 到 AISOU_DEPLOY_DIR）
#   ./scripts/ssh_aisoul.sh update       # 远端 git pull + 构建 + systemctl restart
#   ./scripts/ssh_aisoul.sh run uptime
#   ./scripts/ssh_aisoul.sh run bash -lc 'cd /opt/aisoul && git status'

set -euo pipefail

HOST="${AISOU_DEPLOY_HOST:?请设置环境变量 AISOU_DEPLOY_HOST（虚拟机 IP 或域名）}"
USER="${AISOU_DEPLOY_USER:-ubuntu}"
PORT="${AISOU_DEPLOY_SSH_PORT:-22}"
DIR="${AISOU_DEPLOY_DIR:-/opt/aisoul}"
KEY="${AISOU_DEPLOY_KEY_PATH:-}"
UNIT="${AISOU_DEPLOY_SYSTEMD_UNIT:-aisoul-backend}"

ssh_base=( -p "$PORT" -o StrictHostKeyChecking=accept-new )
if [[ -n "$KEY" ]]; then
  KEY_EXPAND="${KEY/#\~/$HOME}"
  if [[ ! -f "$KEY_EXPAND" ]]; then
    echo "私钥不存在: $KEY_EXPAND" >&2
    exit 2
  fi
  ssh_base+=( -i "$KEY_EXPAND" )
fi

CMD="${1:-login}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$CMD" in
  login|shell)
    exec ssh "${ssh_base[@]}" "$USER@$HOST" "$@"
    ;;
  bootstrap)
    RDIR=$(printf '%q' "$DIR")
    exec ssh "${ssh_base[@]}" "$USER@$HOST" bash -lc "cd $RDIR && AISOU_REPO=$RDIR bash scripts/bootstrap_linux_vm.sh"
    ;;
  update)
    RDIR=$(printf '%q' "$DIR")
    RUN=$(printf '%q' "$UNIT")
    exec ssh "${ssh_base[@]}" "$USER@$HOST" bash -lc "set -euo pipefail; cd $RDIR; git pull; source .venv/bin/activate; pip install -e . -q; (cd frontend && npm install --no-fund --no-audit && npm run build); (cd frontend/admin && npm install --no-fund --no-audit && npm run build); sudo systemctl restart $RUN; sudo systemctl is-active --quiet $RUN && echo systemd: $UNIT is active"
    ;;
  run)
    if [[ $# -lt 1 ]]; then
      echo "用法: $0 run uptime   或   $0 run bash -lc 'cd /opt/aisoul && git status'" >&2
      exit 2
    fi
    exec ssh "${ssh_base[@]}" "$USER@$HOST" "$@"
    ;;
  help|-h|--help)
    grep '^#' "$0" | head -n 32 | cut -c2-
    exit 0
    ;;
  *)
    echo "未知子命令: $CMD （login | bootstrap | update | run）" >&2
    exit 1
    ;;
esac
