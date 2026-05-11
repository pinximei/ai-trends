# 腾讯云 CVM / 轻量：部署说明（学习向）

> 代码 **不绑定**腾讯云；任意 Linux 云主机同理。数据优先：**PostgreSQL 托管或自建 + 备份**（见 `requirements-master-v1.md` §4.1）。

## 0. 首次上机（Linux + SSH）

1. `git clone` 到例如 `/opt/aitrends` 后，SSH 登录该机器，在仓库根执行：  
   `chmod +x scripts/bootstrap_linux_vm.sh && AITRENDS_REPO=/opt/aitrends bash scripts/bootstrap_linux_vm.sh`  
   脚本会安装依赖、创建 `.venv`、构建两个前端，并提示编辑 `backend/.env` 与 systemd/Nginx。
2. systemd 示例：`deploy/systemd/aitrends-backend.service.example`（复制到 `/etc/systemd/system/` 后按需改 `User`/`WorkingDirectory`/`ExecStart` 路径）。
3. 日常更新仍可在**你本机**用 `py scripts/deploy_ssh.py`（需能 SSH 到该主机）。若使用 **Git Bash / WSL**，也可用 **`scripts/ssh_aitrends.sh`**（`login` / `bootstrap` / `update`，凭据走环境变量与 `ssh-agent`）。
4. **GitHub 推送自动部署（可选）**：见下文 **§2.1**。与本地部署共用远端脚本 **`scripts/vm_deploy.sh`**，避免命令两套不一致。

**本机密码登录（勿把含密码的文件提交 Git）**：复制 `scripts/ssh_local.env.example` 为 **`scripts/ssh_local.env`**（已在 `.gitignore`），填写 `AITRENDS_DEPLOY_*` 后执行 **`py scripts/ssh_connect.py`** 打开远端 shell；生产环境更推荐 **SSH 私钥**。

### 云桌面：把工程部署到哪里？

「**云桌面**」一般指公司给你的 **远程办公桌面**（常见是 Windows）。AiTrends 作为 **Web 前后端 + PostgreSQL**，应部署在 **一台 Linux 虚拟机（或云主机）** 上；云桌面只负责 **打开浏览器访问网址**、或用 **终端 / Cursor / PowerShell** 去 **SSH 那台 Linux**。

按你的环境二选一即可：

| 你的情况 | 做法 |
|----------|------|
| **Linux 虚拟机已有公网 IP / 跳板 SSH** | 在云桌面里安装 Git、Python、Node（或只用 Python 跑部署脚本）。`git clone` 本仓库后，设置 `AITRENDS_DEPLOY_HOST` 等环境变量，执行 **`py scripts/deploy_ssh.py`**，由脚本在远端 `git pull`、构建、`systemctl restart`（远端需已按 §0 做过首次 bootstrap 与 systemd）。 |
| **你能直接 SSH 登录那台 Linux** | SSH 进去后 `git clone` 到 `/opt/aitrends`，执行 **`bash scripts/bootstrap_linux_vm.sh`**，再按脚本末尾提示编辑 **`backend/.env`**、安装 **`deploy/systemd/aitrends-backend.service.example`**、配 **Nginx**（见下文 §2）。 |

**不要**指望在云桌面的「会话磁盘」里当正式生产服务器长期跑 Nginx（除非单位明确要求且你自行维护）；标准做法是 **Linux 一台机跑服务**，云桌面只做访问与运维入口。

## 1. 架构

- **一台机**：Nginx（HTTPS、静态前端、反代 `/api`）→ Uvicorn（FastAPI）→ **PostgreSQL**（建议独立云数据库或与机同 VPC）。
- **两前端构建产物**：`frontend/dist`、`frontend/admin/dist` 由 Nginx `root` / `alias` 提供；API 仅后端域名或同域 `/api`。

## 2. Nginx（标准做法）

- **仓库模板**：`deploy/nginx/aitrends.conf`（含 HTTP→HTTPS、`/` 公开 SPA、`/admin/` 管理端 SPA、`/api/` 反代）。按你的域名与证书路径修改 `server_name`、`ssl_certificate*`、安装目录。
- **Ubuntu 惯例**：配置放在 **`/etc/nginx/sites-available/aitrends`**，仅在 **`/etc/nginx/sites-enabled/`** 里放指向它的 **符号链接**，不要在该目录放 `*.bak` 等裸文件（会被 `include sites-enabled/*` 当成第二份站点，触发 `conflicting server name`）。
- **管理端子路径**：`alias` 与 `try_files` 最后一项不能写成 URI `/admin/index.html`（会错误回落到 `root` 下的公开站 `index.html`）。模板使用 **`location = /admin/index.html` + 命名 `@admin_spa_fallback`**，与 [Nginx 对 alias 的语义](https://nginx.org/en/docs/http/ngx_http_core_module.html#alias) 一致。
- **一键应用**（本机已安装 `paramiko`、能 SSH 到云机）：

```text
AITRENDS_DEPLOY_HOST=你的公网IP AITRENDS_DEPLOY_USER=ubuntu AITRENDS_DEPLOY_SSH_PASSWORD=... py scripts/apply_nginx_cloud.py
```

**发布版本号**：公开站与后台顶栏会显示 **前端构建** 与 **API** 两段标识；API 来自 `GET /api/public/v1/version`。生产建议在 `backend/.env` 设置 `AITRENDS_APP_RELEASE`（可与 git 短 SHA 一致），与前端构建对照即可确认是否已部署到新代码。`deploy_ssh.py` 在远端构建前端时会注入 `VITE_GIT_SHA=$(git rev-parse --short HEAD)`。

## 2.1 GitHub Actions（推送 `main` 自动编译部署）

1. 工作流：`.github/workflows/deploy-vm.yml`。触发条件：**push 到 `main`**，或 **Actions → deploy-vm → Run workflow**；Runner 上先跑 **`pytest`**，通过后再 SSH 到 VM 执行 `git pull` 与 `scripts/vm_deploy.sh`（与本地 **`py scripts/deploy_ssh.py`** 同源，避免两套命令不一致）。
2. 在 GitHub：**Settings → Secrets and variables → Actions**  
   - **Secrets（敏感）**：至少具备 **SSH 登录方式之一**：  
     - **`AITRENDS_DEPLOY_SSH_KEY`**：私钥全文（推荐）；或  
     - **`AITRENDS_DEPLOY_SSH_PASSWORD`**：SSH 密码（**勿**写在 Variables，Variables 会在界面明文展示）。  
   - **HOST / USER**：可放在 **Secrets** 或 **Variables**（工作流对二者均可：`secrets.* || vars.*`）。名称：**`AITRENDS_DEPLOY_HOST`**、**`AITRENDS_DEPLOY_USER`**。  
   - **Variables（非密钥配置）**：**`AITRENDS_VM_REPO_DIR`**、**`AITRENDS_VM_SYSTEMD_UNIT`**（远端仓库路径与 systemd 单元名）。
3. VM 上需已有 **克隆好的仓库目录**（文档示例为 **`/opt/aitrends`**；若你装在 **`/opt/aisoul`** 等路径，见下方 **Variables**）。目录须能 **`git fetch` / `reset --hard`**（公仓即可；私仓在 VM 配置 [Deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)）；部署用户对目录可写；**`sudo systemctl restart <你的后端 unit>`** 可用（bootstrap / sudoers）。
4. **可选：仓库 Variables**（Settings → Secrets and variables → Actions → **Variables**）：与工作流 `.github/workflows/deploy-vm.yml` 对齐远端路径与 systemd 名，避免 SSH 步骤里 **`cd` 目录不存在** 导致失败。  
   - **`AITRENDS_VM_REPO_DIR`**：远端仓库根路径，默认 **`/opt/aitrends`**（未设置 Variable 时使用）。例如：`/opt/aisoul`。  
   - **`AITRENDS_VM_SYSTEMD_UNIT`**：后端 service 名（不含 `.service`），默认 **`aitrends-backend`**。例如：`aisoul-backend`。
5. 私钥带口令：当前工作流未传入 `passphrase`；可用无口令专用密钥，或自行改工作流接入 `appleboy/ssh-action` 的对应参数。

### 2.2 Actions / SSH 部署失败排查

- **pytest 在 Actions 里失败**：查看 Run 日志中「Install dependencies & run tests」步骤；常见原因是数据库尚未接受连接（工作流已加入 `pg_isready` 等待，仍失败时可重试 Run）。本地对齐验证：`docker compose`/临时 Postgres + `AITRENDS_DATABASE_URL` 后执行 `python -m pytest tests/`。
- **凭据不完整被跳过**：须同时具备 **HOST + USER**（Secrets 或 Variables 均可）以及 **私钥或密码之一**（**`AITRENDS_DEPLOY_SSH_KEY` / `AITRENDS_DEPLOY_SSH_PASSWORD` 只能放在 Secrets**）。仅把密码写在 Variables 无效且不安全。
- **SSH 报 `cd: /opt/aitrends: No such file`** 或 **`VM_REPO_DIR: unbound variable`**：在仓库 **Variables** 设置远端仓库根路径（**`AITRENDS_VM_REPO_DIR`** 或 **`AITRENDS_DEPLOY_VM_REPO_DIR`** 或 **`AITRENDS_REMOTE_REPO_DIR`**）及 systemd 单元（对应 **`AITRENDS_*_SYSTEMD_UNIT`** 三名之一）。工作流在 **「Resolve VM paths for SSH」** 步骤把 Variables 写成 step output，再交给 SSH（避免 composite action 内 **`vars` 未解析** 一直落到默认 `/opt/aitrends`）。
- **SSH 其它报错**：在 VM 上确认 Variables 中的目录存在且 **`git fetch` + `reset --hard origin/main`** 成功（私仓需 [Deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)）；手动执行：  
  `cd <你的仓库根> && bash scripts/vm_deploy.sh`  
  查看是否缺 **Node/npm**、**pip**、或 **`sudo systemctl restart …`** 权限（sudoers）。若日志里出现 **`appleboy/ssh-action@v1.0.x`** 等旧版本，请合并最新 **`main`**（当前工作流使用 **`v1.2.5`**）。
- **不用 GitHub Actions**：在本机配置 `scripts/ssh_local.env` 或环境变量后执行 **`py scripts/deploy_ssh.py`**，与 Actions 调用同一套远端脚本。
- **浏览器报 HTTP 502、前端提示「响应非 JSON」**：通常是 Nginx 反代 `/api` 时连不上本机 Uvicorn（`127.0.0.1:8000`）。在 VM 上执行 **`systemctl status`**（你的后端 unit，例如 `aisoul-backend` / `aitrends-backend`）与 **`journalctl -u <unit> -n 80`**。若日志里是 **PostgreSQL 认证失败**，且 systemd 里仍使用旧前缀 **`AISOU_*`**：当前后端只读取 **`AITRENDS_*`**，请把 unit 中的环境变量全部改为 `AITRENDS_`（例如 `AITRENDS_DATABASE_URL`），或改用 **`EnvironmentFile=/path/to/repo/backend/.env`**（文件内同样使用 `AITRENDS_`）。修复后 **`curl -sS http://127.0.0.1:8000/api/public/v1/version`** 应返回 JSON。

## 3. 环境变量（示例）

```text
# 数据库（腾讯云 PostgreSQL 控制台复制连接串）
AITRENDS_DATABASE_URL=postgresql+psycopg://user:pass@内网或公网:5432/aitrends

# CORS：你的前端访问来源
AITRENDS_CORS_ORIGINS=https://你的域名,https://www.你的域名

# 管理端首次账号（生产务必改密）
AITRENDS_ADMIN_INIT_USERNAME=admin
AITRENDS_ADMIN_INIT_PASSWORD=强密码
AITRENDS_ENV=production
```

首次启动后，管理员密码即为上面的 **`AITRENDS_ADMIN_INIT_PASSWORD`**，与本地开发默认的 `admin123456` **无关**。若遗忘，可在服务器项目目录执行 **`py scripts/reset_admin_password.py`**（交互输入新密码，需与线上同一 `AITRENDS_DATABASE_URL`）。

**运行参数（CORS、JWT 时长、HTTPS 策略、app_env、演示种子、旧版内部接口开关、版本展示串、热门默认模型等）** 已迁至库表 **`product_settings_kv.runtime`**，在管理端 **「账号管理」→「运行参数」** 修改即可；**数据库连接串、JWT_SECRET、SIGNING_KEY、AUTH_BOOTSTRAP_KEY、LLM 密钥、AITRENDS_ADMIN_TOKEN** 仍仅用环境变量。

已启用连接器由后端 **APScheduler** 按 **库内配置**（`product_settings_kv.scheduler`：间隔小时数、是否启用）做整批同步；进程每 **15 分钟**检查一次是否到点，无需改代码或重启即可在管理端 **「AI 资讯与数据」→ 定时同步与数据清理」** 保存。新建库时若未写过库表，默认间隔可读环境变量 **`AITRENDS_CONNECTOR_SYNC_INTERVAL_HOURS`**（1～168）。**管理员**可在同页一键清空连接器入库相关表（文章、指标点、同步日志、热门快照、LLM 用量）并重置连接器上次同步时间。

前端构建：

```text
# 公开站：API 为 https://api.你的域名 或 https://你的域名/api
cd frontend
echo VITE_API_BASE=https://api.你的域名 > .env.production
npm run build
```

若 **同域**：Nginx 把 `/api` 反代到 uvicorn，则 `VITE_API_BASE` 可留空，由浏览器访问同域 `/api`。

## 4. systemd（示例）

`ExecStart`：`/path/venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`

## 5. 备案与 HTTPS

- 使用 **大陆域名 + 大陆机房** 对外提供 Web 服务，需按政策 **ICP 备案**。
- 证书：Let’s Encrypt（acme.sh）或腾讯云 SSL 证书。

## 6. 备份

- 云数据库开启 **自动备份**；应用层定期 `pg_dump` 到 COS 作双保险。
