# aitrends

单仓双目录架构：

- `frontend/`：前端应用目录
  - `frontend/`（公开前台，默认端口 `5172`）
  - `frontend/admin/`（后台管理端，端口 `5174`）
- `backend/`：后端 API（FastAPI，端口 `8000`）

## 线上体验

公开站点可直接访问：**[https://www.ai-trends.news](https://www.ai-trends.news)**（同域 `/api` 提供公开 JSON API）。页面内容为 AI 趋势资讯与学习向演示，不构成采购或合规结论；欢迎试用与反馈 Issue。

后台管理路径为 **`/admin/`**，不向访客开放账号；如需自建实例见下文「本地运行」与 `docs/deploy-tencent-cvm.md`。

**外部 Agent（含飞书机器人）接续开发**：请先阅读 **`docs/HANDOFF_AGENT_FEISHU.md`**（业务、路由、API、调度与部署导航）。

## 产品需求与实现设计

- 需求主文档：`docs/requirements-master-v1.md`（含 **项目定位**：学习向、可全量重写、部署后议）
- API / 数据库 / 安全：`docs/implementation-architecture-api-db-security-v1.md`

当前仓库中的运行方式与旧 API 可能随重写调整；以 `docs/` 中目标设计为准。

### 新版公开 API（已实现）

- 前缀：`/api/public/v1`（免登录 JSON：`{ code, message, data }`）
- 前台路由：`/`、`/trends`、`/resources`、`/resources/:id`、`/about`
- 腾讯云部署参考：`docs/deploy-tencent-cvm.md`

## 本地运行

**0) Docker 一键预览（在你自己的电脑上执行；无需单独安装 Python / Node）**

安装并启动 [Docker Desktop](https://www.docker.com/products/docker-desktop/)，在仓库根目录执行：

```text
docker compose -f docker-compose.local.yml up --build
```

- 公开站：<http://127.0.0.1:5172>
- 管理端：<http://127.0.0.1:5174>
- API 文档：<http://127.0.0.1:8000/docs>

停止（保留数据库卷）：`docker compose -f docker-compose.local.yml down`  
若本机已在运行其它占用 `5432` / `8000` / `5172` / `5174` 的服务，请先停止或修改 `docker-compose.local.yml` 中的端口映射。

**1) PostgreSQL（默认，必需）**

```text
docker compose up -d
```

默认账号库：`postgresql+psycopg://aitrends:aitrends@127.0.0.1:5432/aitrends`（见 `backend/.env.example`）。

**2) 后端 API**

```text
py -m pip install -e .
py -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 文档：<http://127.0.0.1:8000/docs>

**3) 公开前台（另开终端）**

```text
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5172
```

- 打开：<http://127.0.0.1:5172>
- 新增事实文章页：<http://127.0.0.1:5172/briefing>

**4) 后台前端（再开一个终端）**

```text
cd frontend/admin
npm install
npm run dev -- --host 127.0.0.1 --port 5174
```

- 打开：<http://127.0.0.1:5174>
- 默认管理员（首次自动种子）：
  - `username: admin`
  - `password: admin123456`
  - 建议上线前立即修改

## 测试/正式数据库切换

- **默认使用 PostgreSQL**，不再默认 SQLite。本地推荐 `docker compose up -d`。
- 默认使用测试库模式：`AITRENDS_DB_MODE=test`
- 切到正式库模式：`AITRENDS_DB_MODE=prod`
- 一条 URL 覆盖：`AITRENDS_DATABASE_URL=postgresql+psycopg://用户:密码@主机:5432/库名`
- 或分别指定：`AITRENDS_DB_URL_TEST` / `AITRENDS_DB_URL_PROD`（默认见 `backend/app/db.py`）
- 仅在明确需要时可通过 `AITRENDS_DATABASE_URL=sqlite:///...` 使用 SQLite（不推荐）
- 修改后需重启后端生效

## API 分层与鉴权

### Public API（公开业务接口）

- 前缀：`/api/public/v1/*`
- 鉴权：`Bearer + X-TS + X-Signature`（HMAC）

兼容旧前缀：`/api/v1/*` 仍可访问（迁移期）。

### Admin API（后台管理接口）

- 前缀：`/api/admin/v1/*`
- 鉴权：`Session/Cookie + RBAC`
- 登录接口：
  - `POST /api/admin/v1/auth/login`
  - `GET /api/admin/v1/auth/me`
  - `POST /api/admin/v1/auth/logout`
- 核心管理接口：
  - `GET /api/admin/v1/overview`
  - `GET/POST /api/admin/v1/sources`
  - `GET /api/admin/v1/compliance/removal-requests`
  - `POST /api/admin/v1/compliance/removal-requests/{ticket_id}/resolve`
  - `GET /api/admin/v1/audit-logs`
  - `GET/POST /api/admin/v1/settings`
  - `GET/POST /api/admin/v1/users` / `POST /api/admin/v1/users/{username}`
  - `GET /api/admin/v1/health`
  - `GET /api/admin/v1/system/db-info`（查看当前数据库模式）
  - `POST /api/admin/v1/bootstrap/seed-demo`（初始化模拟数据）
  - `POST /api/admin/v1/bootstrap/clear-demo`（清空业务测试数据，仅 admin 可调用）

### AI 事实文章接口（前台）

- `GET /api/v1/content/briefing?period=day|week|month|quarter|year`
- `GET /api/public/v1/content/briefing?period=...`
- 说明：文章内容基于趋势与信号事实拼装，返回章节、引用、事实列表、媒体链接，避免无依据生成。

### 数据库访问统一收口

- 所有 DB 访问集中在 `backend/app/data_api_service.py`（Data API 服务层）
- 对外接口通过 `main.py` 调用该服务层，不允许前端直连数据库
- 轻量兼容迁移（PostgreSQL / 可选 SQLite）：`backend/app/db.py::ensure_schema_compatibility`

## HTTPS 强制要求

- 默认强制 HTTPS：`AITRENDS_REQUIRE_HTTPS=true`
- 本地允许 HTTP：`AITRENDS_ALLOW_INSECURE_LOCALHOST=true`
- 生产建议：
  - `AITRENDS_REQUIRE_HTTPS=true`
  - `AITRENDS_ALLOW_INSECURE_LOCALHOST=false`

## 验证

- 后端测试（需本机 PostgreSQL 已启动，连接串与默认一致或已设 `AITRENDS_DATABASE_URL`）：`py -m pytest tests/ -q`
- 后端语法：`py -m py_compile backend/app/main.py backend/app/admin_auth.py backend/app/data_api_service.py`
- 公开前台构建：`cd frontend && npm run build`
- 后台前端构建：`cd frontend/admin && npm run build`
- 后台链路冒烟（登录+会话+管理接口）：
  - `POST /api/admin/v1/auth/login`
  - `GET /api/admin/v1/auth/me`
  - `GET /api/admin/v1/overview`
  - `GET /api/admin/v1/users`
  - `GET /api/admin/v1/settings`
  - `GET /api/admin/v1/health`
