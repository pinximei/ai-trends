# 腾讯云 CVM / 轻量：部署说明（学习向）

> 代码 **不绑定**腾讯云；任意 Linux 云主机同理。数据优先：**PostgreSQL 托管或自建 + 备份**（见 `requirements-master-v1.md` §4.1）。

## 0. 首次上机（Linux + SSH）

1. `git clone` 到例如 `/opt/aisoul` 后，SSH 登录该机器，在仓库根执行：  
   `chmod +x scripts/bootstrap_linux_vm.sh && AISOU_REPO=/opt/aisoul bash scripts/bootstrap_linux_vm.sh`  
   脚本会安装依赖、创建 `.venv`、构建两个前端，并提示编辑 `backend/.env` 与 systemd/Nginx。
2. systemd 示例：`deploy/systemd/aisoul-backend.service.example`（复制到 `/etc/systemd/system/` 后按需改 `User`/`WorkingDirectory`/`ExecStart` 路径）。
3. 日常更新仍可在**你本机**用 `py scripts/deploy_ssh.py`（需能 SSH 到该主机）。若使用 **Git Bash / WSL**，也可用 **`scripts/ssh_aisoul.sh`**（`login` / `bootstrap` / `update`，凭据走环境变量与 `ssh-agent`）。

**本机密码登录（勿把含密码的文件提交 Git）**：复制 `scripts/ssh_local.env.example` 为 **`scripts/ssh_local.env`**（已在 `.gitignore`），填写 `AISOU_DEPLOY_*` 后执行 **`py scripts/ssh_connect.py`** 打开远端 shell；生产环境更推荐 **SSH 私钥**。

### 云桌面：把工程部署到哪里？

「**云桌面**」一般指公司给你的 **远程办公桌面**（常见是 Windows）。AISoul 作为 **Web 前后端 + PostgreSQL**，应部署在 **一台 Linux 虚拟机（或云主机）** 上；云桌面只负责 **打开浏览器访问网址**、或用 **终端 / Cursor / PowerShell** 去 **SSH 那台 Linux**。

按你的环境二选一即可：

| 你的情况 | 做法 |
|----------|------|
| **Linux 虚拟机已有公网 IP / 跳板 SSH** | 在云桌面里安装 Git、Python、Node（或只用 Python 跑部署脚本）。`git clone` 本仓库后，设置 `AISOU_DEPLOY_HOST` 等环境变量，执行 **`py scripts/deploy_ssh.py`**，由脚本在远端 `git pull`、构建、`systemctl restart`（远端需已按 §0 做过首次 bootstrap 与 systemd）。 |
| **你能直接 SSH 登录那台 Linux** | SSH 进去后 `git clone` 到 `/opt/aisoul`，执行 **`bash scripts/bootstrap_linux_vm.sh`**，再按脚本末尾提示编辑 **`backend/.env`**、安装 **`deploy/systemd/aisoul-backend.service.example`**、配 **Nginx**（见下文 §2）。 |

**不要**指望在云桌面的「会话磁盘」里当正式生产服务器长期跑 Nginx（除非单位明确要求且你自行维护）；标准做法是 **Linux 一台机跑服务**，云桌面只做访问与运维入口。

## 1. 架构

- **一台机**：Nginx（HTTPS、静态前端、反代 `/api`）→ Uvicorn（FastAPI）→ **PostgreSQL**（建议独立云数据库或与机同 VPC）。
- **两前端构建产物**：`frontend/dist`、`frontend/admin/dist` 由 Nginx `root` / `alias` 提供；API 仅后端域名或同域 `/api`。

## 2. Nginx（标准做法）

- **仓库模板**：`deploy/nginx/aisoul.conf`（含 HTTP→HTTPS、`/` 公开 SPA、`/admin/` 管理端 SPA、`/api/` 反代）。按你的域名与证书路径修改 `server_name`、`ssl_certificate*`、安装目录。
- **Ubuntu 惯例**：配置放在 **`/etc/nginx/sites-available/aisoul`**，仅在 **`/etc/nginx/sites-enabled/`** 里放指向它的 **符号链接**，不要在该目录放 `*.bak` 等裸文件（会被 `include sites-enabled/*` 当成第二份站点，触发 `conflicting server name`）。
- **管理端子路径**：`alias` 与 `try_files` 最后一项不能写成 URI `/admin/index.html`（会错误回落到 `root` 下的公开站 `index.html`）。模板使用 **`location = /admin/index.html` + 命名 `@admin_spa_fallback`**，与 [Nginx 对 alias 的语义](https://nginx.org/en/docs/http/ngx_http_core_module.html#alias) 一致。
- **一键应用**（本机已安装 `paramiko`、能 SSH 到云机）：

```text
AISOU_DEPLOY_HOST=你的公网IP AISOU_DEPLOY_USER=ubuntu AISOU_DEPLOY_SSH_PASSWORD=... py scripts/apply_nginx_cloud.py
```

## 3. 环境变量（示例）

```text
# 数据库（腾讯云 PostgreSQL 控制台复制连接串）
AISOU_DATABASE_URL=postgresql+psycopg://user:pass@内网或公网:5432/aisoul

# CORS：你的前端访问来源
AISOU_CORS_ORIGINS=https://你的域名,https://www.你的域名

# 管理端首次账号（生产务必改密）
AISOU_ADMIN_INIT_USERNAME=admin
AISOU_ADMIN_INIT_PASSWORD=强密码
AISOU_ENV=production
```

首次启动后，管理员密码即为上面的 **`AISOU_ADMIN_INIT_PASSWORD`**，与本地开发默认的 `admin123456` **无关**。若遗忘，可在服务器项目目录执行 **`py scripts/reset_admin_password.py`**（交互输入新密码，需与线上同一 `AISOU_DATABASE_URL`）。

已启用连接器由后端 **APScheduler 默认每 6 小时**自动同步；可用 **`AISOU_CONNECTOR_SYNC_INTERVAL_HOURS`**（1～168）调整，重启进程后生效。管理端 **「AI 资讯」→ 定时同步与数据清理」** 中，**管理员**可一键清空连接器入库相关表（文章、指标点、同步日志、热门快照、LLM 用量）并重置连接器上次同步时间。

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
