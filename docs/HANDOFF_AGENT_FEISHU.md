# 交接文档 · 供飞书 / 外部 Agent 接续开发

> **用途**：让未参与本仓库历史的自动化 Agent（含飞书机器人侧编排的 coding agent）快速理解 **业务目标、已实现功能、目录与接口约定**，减少反复探代码的时间。  
> **单一事实来源（需求）**：`docs/requirements-master-v1.md`；**目标态架构与 API 草案**：`docs/implementation-architecture-api-db-security-v1.md`。  
> **注意**：实现已多次迭代，**代码为准**；设计文档中的部分路径与当前仓库可能不一致，以下 **「实现现状」** 优先。

---

## 1. 产品与定位

- **品牌 / 线上站点**：公开体验站 **[https://www.ai-trends.news](https://www.ai-trends.news)**（README 亦有说明）。
- **领域**：AI 行业资讯与「可安装产品 / 应用」聚合展示（单站点 `industry_slug` 多为 `ai`）。
- **原则（来自需求文档）**：
  - 学习向项目，**不承诺**与旧版 API/表结构兼容。
  - 公开文章正文 **不以 LLM 实时生成**；**热门排序**依赖服务端周期性生成的 **热门快照**（落库），访客只读。
  - **连接器**拉取第三方数据；展示需可追溯来源；合规与免责声明见关于页。
- **明确不做（需求级）**：访客投稿、前台「灵感」、文章正文由 LLM 摘要、多站点等（见 `requirements-master-v1.md` §2.3）。

---

## 2. 技术架构（实现现状）

| 层级 | 路径 / 说明 |
|------|-------------|
| 公开前台 SPA | `frontend/`（Vite + React，端口本地 `5172`） |
| 管理端 SPA | `frontend/admin/`（`build` 后挂 `/admin/`） |
| 后端 | `backend/app/`（FastAPI + SQLAlchemy） |
| 数据库 | 默认 **PostgreSQL**（`backend/app/db.py`，连接串见 `backend/.env.example`） |
| 调度 | `backend/app/lifespan.py`：**APScheduler** — 约三天热门快照、异动扫描、连接器批量同步闸门（约 15 分钟检查一次间隔） |
| 部署 | Linux：`scripts/vm_deploy.sh`；本机 SSH：`scripts/deploy_ssh.py`；GitHub：**`push` 到 `main`** 触发 `.github/workflows/deploy-vm.yml`（pytest 通过后 SSH 部署；亦可手动 Run workflow） |

环境变量前缀统一为 **`AITRENDS_*`**（生产 systemd 勿再用已废弃的 `AISOU_*`）。

---

## 3. 前台功能与路由（对齐代码）

公开站路由见 `frontend/src/App.tsx`：

| 路径 | 含义 |
|------|------|
| `/` | 重定向到 `/apps` |
| `/apps` | **AI 应用**泳道（可安装产品等，`FeedRadarPage` `mode="apps"`） |
| `/news` | **AI 资讯**泳道（`mode="news"`） |
| `/resources/:id` | 文章 / 资源详情 |
| `/downloads` | 软件下载列表（公开安装包入口） |
| `/about` | 关于 / 免责（内容来自 CMS） |

顶栏展示 **UI 构建版本**（`package.json` + `VITE_GIT_SHA`）与 **API `/api/public/v1/version`** 返回的 release。

---

## 4. 公开 API（前缀 `/api/public/v1`）

路由聚合：`backend/app/api/public/router.py`。

**统一响应外壳**：多数为 `{ "code": 0, "message": "ok", "data": ... }`（见 `backend/app/core/envelope.py`）。

| 区域 | 路径要点 |
|------|-----------|
| 文章 | `GET /articles/categories` — 分类 facets（`feed=news|apps`） |
| 文章 | `GET /articles/feed` — 列表；`paginate_by=cursor|day`（按日分页为 UTC 整日） |
| 文章 | `GET /articles/{article_id}` — 详情 |
| 软件 | `GET /software/downloads`、`GET /software/categories`、`GET /software/downloads/{id}/file` |
| CMS | `GET /pages/{slug}` — 如 `about` / `about_en` |
| 系统 | `GET /health`、`GET /version` |

公开 JSON 接口 **不要求** HMAC 或客户端签名；传输安全由 HTTPS（及 `backend/app/security.py` 的 `enforce_https`）保障。

---

## 5. 管理端 API（概要）

- 前缀主要为 **`/api/admin/v1`**，另有 **`/api/admin/v1/data/*`**（数据浏览）。
- 路由模块：
  - `backend/app/routers/admin_product.py` — 产品域：CMS、热门快照重建入口、ingest 清理、`ThemeFetchPayload` 等。
  - `backend/app/routers/admin_extended.py` — 连接器同步、运行参数、LLM 设置、调度与导入等扩展能力。
  - `backend/app/routers/admin_data_browser.py` — 数据浏览/导出类接口。
- `backend/app/main.py` 挂载 **会话认证、用户与数据源、overview、设置、演示种子** 等基础管理路由；README「Admin API」一节有列表，新增功能优先走上述 `routers/` 模块。
- 认证：**Session Cookie**（`aitrends_admin_session`）+ RBAC（`viewer` / `operator` / `admin`）；生产须配置 `AITRENDS_JWT_SECRET`、`AITRENDS_SIGNING_KEY`、`AITRENDS_ADMIN_INIT_*` 等。

---

## 6. 核心业务模块（代码导航）

| 主题 | 建议入口 |
|------|-----------|
| 公开文章列表/详情应用层 | `backend/app/application/article_public.py`、`backend/app/domain/articles.py` |
| 热门快照 | `backend/app/hot_service.py`（定时任务在 `lifespan.py`） |
| 连接器批量同步 | `scheduler_settings_service`、`admin_extended.run_connector_sync`、闸门 `_job_connector_sync_gate` |
| 软件下载实体 | `backend/app/product_models.py`（`SoftwareDownload` 等）、`software_package_service.py` |
| CMS 页 | `product_models.CmsPage`，种子 `product_seed.ensure_public_about_page` |
| 运行时参数（CORS、HTTPS、演示种子等） | `runtime_settings_service.py` + 库表 `product_settings_kv.runtime` |
| 国际化前台 | `frontend/src/i18n/` |

---

## 7. 数据与合规

- **持久化**：生产强烈建议 **PostgreSQL + 备份**（需求 §4.1）。
- **清理**：管理端可对连接器入库数据做一键清理（见 `clear_product_ingest_data`、admin API），**高危操作**，需管理员权限。

---

## 8. 开发与约定（给 Agent）

1. **改代码前**：读相关 `application/`、`domain/`、`routers/`，避免在 `main.py` 堆路由。
2. **前端**：公开站与管理端 **两套** `package.json`；生产构建由 `scripts/vm_deploy.sh` 调用。
3. **环境**：复制 `backend/.env.example` → `backend/.env`；永远不要提交真实密钥。
4. **部署验证**：合并后若要走 GitHub 部署，需 **`git tag v… && git push origin v…`**；或本机 `py scripts/deploy_ssh.py`（`scripts/ssh_local.env`）。
5. **文档**：需求变更先更新 `requirements-master-v1.md` 再实现，或在 PR 说明中与文档对齐。

---

## 9. 推荐阅读顺序（30 分钟）

1. `README.md`（本地运行、API 分层）  
2. `docs/requirements-master-v1.md`（§1–§3）  
3. `docs/deploy-tencent-cvm.md`（GitHub Actions / SSH / Secrets-Variables）  
4. `frontend/src/App.tsx` + `backend/app/api/public/router.py`  
5. `backend/app/lifespan.py`（调度与启动顺序）

---

## 10. 修订

| 日期 | 说明 |
|------|------|
| 2026-05-11 | 初版：面向飞书等外部 Agent 的交接说明 |
