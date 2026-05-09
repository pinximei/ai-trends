#!/usr/bin/env bash
# 在仓库根目录执行（与 git pull 分开调用：先 pull 再跑本脚本，确保拉到的新版脚本在下一轮生效）。
# 被 deploy_ssh.py 与 .github/workflows/deploy-vm.yml 共用。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

UNIT="${AITRENDS_DEPLOY_SYSTEMD_UNIT:-aitrends-backend}"

if [[ -d .venv ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

python3 -m pip install -e . -q

VITE_GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export VITE_GIT_SHA

(cd frontend && npm install --no-fund --no-audit && npm run build)
(cd frontend/admin && npm install --no-fund --no-audit && npm run build)

sudo systemctl restart "$UNIT"
sudo systemctl is-active --quiet "$UNIT" && echo "systemd: ${UNIT} is active"
