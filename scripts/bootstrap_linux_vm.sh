#!/usr/bin/env bash
# 在 Linux 虚拟机上**首次**部署 AiTrends：装系统依赖、Python venv、npm 构建、提示 systemd。
# 用法（在仓库根目录，或任意目录传入绝对路径）:
#   bash scripts/bootstrap_linux_vm.sh
#   AITRENDS_REPO=/opt/aitrends bash scripts/bootstrap_linux_vm.sh
set -euo pipefail

REPO="${AITRENDS_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$REPO"

if [[ ! -f backend/app/main.py ]]; then
  echo "错误: 未在 AiTrends 仓库根目录找到 backend/app/main.py（当前: $REPO）" >&2
  exit 1
fi

need_sudo() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    return 1
  fi
  return 0
}
SUDO=""
if need_sudo && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

echo "==> 安装系统包（Ubuntu/Debian）…"
$SUDO apt-get update -qq
$SUDO apt-get install -y git nginx python3-venv python3-pip curl ca-certificates

if ! command -v node >/dev/null 2>&1; then
  echo "==> 安装 Node.js LTS（使用 NodeSource 脚本）…"
  curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO bash -
  $SUDO apt-get install -y nodejs
fi

if [[ ! -d .venv ]]; then
  echo "==> 创建 Python 虚拟环境…"
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
source .venv/bin/activate
pip install -U pip wheel -q
pip install -e . -q

if [[ ! -f backend/.env ]]; then
  echo "==> 从 backend/.env.example 复制 backend/.env（请务必编辑数据库与密钥）"
  cp backend/.env.example backend/.env
fi

for fe in frontend frontend/admin; do
  if [[ ! -f "$fe/.env.production" ]]; then
    echo "VITE_API_BASE=" >"$fe/.env.production"
    echo "==> 已写入 $fe/.env.production（同域 /api 可留空；否则填 https://api.你的域名）"
  fi
done

echo "==> npm 构建公开站与管理端…"
( cd frontend && npm install --no-fund --no-audit && npm run build )
( cd frontend/admin && npm install --no-fund --no-audit && npm run build )

echo ""
echo "----- 接下来请你手工完成（需编辑机密） -----"
echo "1) 编辑 $REPO/backend/.env ：AITRENDS_DATABASE_URL、AITRENDS_ENV=production、AITRENDS_CORS_ORIGINS、"
echo "   AITRENDS_ADMIN_INIT_*、AITRENDS_LLM_API_KEY 等。"
echo "2) 安装 systemd 单元（示例在 deploy/systemd/aitrends-backend.service.example），把路径改成 $REPO ，然后:"
echo "   sudo cp deploy/systemd/aitrends-backend.service.example /etc/systemd/system/aitrends-backend.service"
echo "   sudo systemctl daemon-reload && sudo systemctl enable --now aitrends-backend"
echo "3) 配置 Nginx：参考 deploy/nginx/aitrends.conf 与 docs/deploy-tencent-cvm.md"
echo "4) 日后在你本机执行: py scripts/deploy_ssh.py（需 AITRENDS_DEPLOY_HOST 等）"
echo "----- bootstrap 脚本结束 -----"
