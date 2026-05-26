# AI Trends · 资讯与应用聚合

[![Live site](https://img.shields.io/badge/站点-ai--trends.news-violet?style=flat-square)](https://www.ai-trends.news)
[![GitHub](https://img.shields.io/badge/GitHub-pinximei%2Faisoul-181717?style=flat-square&logo=github)](https://github.com/pinximei/aisoul)

从 Product Hunt、GitHub Trending、Hacker News、NewsAPI 等连接器拉取内容，经规则与 LLM 润色后，在公开站展示 **AI 应用** 与 **AI 资讯** 双泳道；后台可配置数据源与调度。

---

## 在线访问

| 入口 | 地址 |
|------|------|
| 公开站 | **[https://www.ai-trends.news](https://www.ai-trends.news)** |
| 开源仓库 | **[github.com/pinximei/aisoul](https://github.com/pinximei/aisoul)** |
| 后台管理 | 同域 **`/admin/`**（不向访客开放，自建见下文） |

欢迎试用与反馈 [Issue](https://github.com/pinximei/aisoul/issues)。

**搜索引擎收录**：站点提供 [`/robots.txt`](https://www.ai-trends.news/robots.txt) 与动态 [`/sitemap.xml`](https://www.ai-trends.news/sitemap.xml)（含已发布文章）。请在 [Google Search Console](https://search.google.com/search-console) 验证域名并提交站点地图；环境变量 `AITRENDS_PUBLIC_BASE_URL` 与前台 `VITE_PUBLIC_SITE_URL` 建议设为 `https://www.ai-trends.news`。

---

## 仓库结构

```
aisoul/
├── frontend/          # 公开站（Vite + React，默认 :5172）
│   └── admin/         # 管理端（:5174）
├── backend/           # API（FastAPI，:8000）
├── docs/              # 需求、部署、Agent 交接文档
└── docker-compose*.yml
```

---

## 本地快速启动

### 方式 A · Docker 一键（推荐预览）

安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/) 后，在仓库根目录：

```bash
docker compose -f docker-compose.local.yml up --build
```

| 服务 | 地址 |
|------|------|
| 公开站 | http://127.0.0.1:5172 |
| 管理端 | http://127.0.0.1:5174 |
| API | http://127.0.0.1:8000 |

停止：`docker compose -f docker-compose.local.yml down`

### 方式 B · 本机开发

**1. 数据库（PostgreSQL）**

```bash
docker compose up -d
```

默认连接串见 `backend/.env.example`。

**2. 后端**

```bash
pip install -e .
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

**3. 公开前台**

```bash
cd frontend && npm install && npm run dev -- --host 127.0.0.1 --port 5172
```

**4. 管理端**（另开终端）

```bash
cd frontend/admin && npm install && npm run dev -- --host 127.0.0.1 --port 5174
```

首次种子管理员：`admin` / `admin123456`（上线前请修改）。

---

## 配置说明

| 变量 | 说明 |
|------|------|
| `AITRENDS_DATABASE_URL` | 数据库连接（默认 PostgreSQL） |
| `AITRENDS_DB_MODE` | `test` / `prod` 库切换 |
| `AITRENDS_ALLOW_INSECURE_LOCALHOST` | 本地允许 HTTP |

更多环境项见 `backend/.env.example`。

---

## 文档

- 产品需求：`docs/requirements-master-v1.md`
- 腾讯云部署：`docs/deploy-tencent-cvm.md`
- 飞书 / 外部 Agent 接续：`docs/HANDOFF_AGENT_FEISHU.md`
- 架构与安全（开发参考）：`docs/implementation-architecture-api-db-security-v1.md`

---

## 验证

```bash
pytest tests/ -q
cd frontend && npm run build
cd frontend/admin && npm run build
```

---

## 许可与说明

本项目用于 **学习参考与信息聚合演示**。连接器内容版权归各平台所有；部署生产环境请自行完成备案与合规配置。
