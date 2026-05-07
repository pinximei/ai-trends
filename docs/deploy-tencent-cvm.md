# 腾讯云 CVM / 轻量：部署说明（学习向）

> 代码 **不绑定**腾讯云；任意 Linux 云主机同理。数据优先：**PostgreSQL 托管或自建 + 备份**（见 `requirements-master-v1.md` §4.1）。

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
