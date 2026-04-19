# 实现方案：架构、API、数据库与安全（v1）

> 对应需求：`requirements-master-v1.md`。

### 实现原则（与需求一致）

- **个人学习项目**：本方案为 **目标态**，**不要求**与当前仓库旧接口、旧表、旧前端路由兼容。  
- **可整体推翻重写**：后端可新目录/新包；前端可换路由与组件；**仅当**你想复用某段代码时再谈「兼容」，**不作为文档义务**。  
- **部署**：Docker、反代、环境变量清单等 **需要上线时再写**；下文安全中的 TLS/CORS 仍以「将来要部署」为参考，本地可放宽。

---

## 1. 总体架构

```
                    ┌─────────────────┐
                    │  CDN / 反向代理  │  TLS 终止、限流
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐
  │ 公开 SPA     │   │ 管理 SPA     │   │ FastAPI 应用      │
  │ (趋势/资源/  │   │ (登录后)     │   │ /api/public/v1    │
  │  关于页)     │   │              │   │ /api/admin/v1     │
  └──────────────┘   └──────────────┘   └─────────┬─────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
             ┌────────────┐                ┌────────────┐                 ┌──────────┐
             │ SQLite/    │                │ 任务调度    │                 │ 外部      │
             │ Postgres   │                │ (约三天热门) │                 │ 第三方 API │
             │            │                │ APScheduler │                 │ LLM API   │
             └────────────┘                └────────────┘                 └──────────┘
```

- **统一拉数出口**：实现为 **环境变量 `DATA_FETCH_BASE_URL`** + 连接器相对 path，或由 **独立 Sidecar/网关** 转发；应用内 **禁止**写死直连外网域名散落多处。
- **大模型**：仅服务端调用；场景：`hot_rank_weekly`（历史命名，**含**定时热门快照重建）、`hot_rank_manual`、`inspiration_generate`。

---

## 2. API 设计

### 2.1 约定

- **公开 API** 前缀：`/api/public/v1`（唯一约定，**不**保留历史别名除非你自己要）。
- **管理 API** 前缀：`/api/admin/v1`。
- **响应**：JSON；统一 `{"data": ..., "error": null}` 或 Problem Details（4xx/5xx）。
- **分页**：`?page=1&page_size=20`；列表默认 `page_size` 上限 100。
- **时间**：ISO 8601 UTC 或带 `Z`；业务可按配置展示东八区。

### 2.2 公开 API（匿名可读）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/public/v1/meta/industries` | 行业列表（首期仅 `ai`） |
| GET | `/api/public/v1/meta/segments` | `?industry_id=` 板块列表 |
| GET | `/api/public/v1/meta/metrics` | `?segment_id=` 可选；指标字典（公开字段） |
| GET | `/api/public/v1/hot/current` | 当前生效 **热门快照**（趋势项 ID 列表 + 文章 ID 列表 + `generated_at`） |
| GET | `/api/public/v1/trends/summary` | `?industry_id=&segment_id=&period=` 或 `from=&to=` 聚合摘要（服务端预聚合） |
| GET | `/api/public/v1/trends/series` | `?metric_key=&segment_id=&from=&to=` 时序点列 |
| GET | `/api/public/v1/articles` | 筛选：`segment_id`、`from`、`to`、`content_type`、`sort=hot\|latest` 等 |
| GET | `/api/public/v1/articles/{id}` | 文章详情（含来源字段，按类型脱敏） |
| GET | `/api/public/v1/pages/{slug}` | 静态页：`about` 等，返回 HTML 块或 Markdown 渲染后 JSON |
| GET | `/api/public/v1/health` | 存活检查（可选公开） |

**说明**：`sort=hot` 时顺序以 **当前热门快照** 中文章顺序为准；无快照则回退 `latest`（配置化）。

### 2.3 管理 API（需会话或 Bearer）

认证：**Session Cookie**（`HttpOnly`、`Secure`、`SameSite=Lax`）或 **短期 Bearer**（任选其一，不要混用两套给前端增加复杂度）。以下假设 Cookie 会话。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/v1/auth/login` | body: username, password |
| POST | `/api/admin/v1/auth/logout` | |
| GET | `/api/admin/v1/auth/me` | 当前用户、角色 |
| **连接器** | | |
| GET/POST | `/api/admin/v1/connectors` | 列表、创建（body 不含明文密钥回显） |
| GET/PATCH/DELETE | `/api/admin/v1/connectors/{id}` | |
| POST | `/api/admin/v1/connectors/{id}/sync` | 手动同步（频控） |
| POST | `/api/admin/v1/connectors/{id}/test` | 测试连接 |
| **板块 / 指标** | | |
| CRUD | `/api/admin/v1/segments` | |
| CRUD | `/api/admin/v1/metrics` | |
| **文章** | | |
| CRUD | `/api/admin/v1/articles` | 含 `status=draft|published` |
| **热门** | | |
| GET | `/api/admin/v1/hot/snapshots` | 历史快照列表 |
| GET | `/api/admin/v1/hot/snapshots/{id}` | 详情 |
| POST | `/api/admin/v1/hot/rebuild` | 手动重跑（频控；operator+） |
| GET/PATCH | `/api/admin/v1/hot/settings` | Cron 表达式、模型名、Top N、兜底策略 |
| **异动** | | |
| GET/PATCH | `/api/admin/v1/anomaly/settings` | 阈值、窗口、冷却 |
| GET | `/api/admin/v1/anomaly/events` | 列表 |
| PATCH | `/api/admin/v1/anomaly/events/{id}/read` | 已读 |
| **灵感** | | |
| GET/POST | `/api/admin/v1/inspirations` | 列表、创建草稿 |
| GET | `/api/admin/v1/inspirations/{id}/versions` | 版本历史 |
| POST | `/api/admin/v1/inspirations/{id}/generate` | 手动触发生成（body：上下文片段） |
| **LLM** | | |
| GET | `/api/admin/v1/llm/usage` | `?from=&to=&scenario=` 汇总 |
| **静态页** | | |
| GET/PUT | `/api/admin/v1/cms/pages/{slug}` | 草稿/发布 |
| **审计** | | |
| GET | `/api/admin/v1/audit-logs` | 筛选 |

**权限中间件**：`viewer` 只读；`operator` 无用户/安全策略写；`admin` 全部。

---

## 3. 数据库设计

> 命名：`snake_case`；主键 `id` UUID 或 自增整型（二选一全库统一）。以下为逻辑模型，实现可用 SQLAlchemy。

### 3.1 核心实体

**`industries`**  
- `id`, `slug`（`ai`）, `name`, `enabled`, `sort_order`

**`segments`**（板块）  
- `id`, `industry_id` FK, `slug`, `name`, `enabled`, `sort_order`, `show_on_public`

**`connectors`**  
- `id`, `type`（`api`/`crawler` 预留）, `name`, `provider_name`  
- `base_path` 或相对 path 模板  
- `auth_type`（`none`/`api_key`/…）  
- **`secret_ref`**（不在 DB 存明文：存 KMS key id 或应用内加密串）  
- `config_json`（映射规则、频率、超时）  
- `enabled`, `last_sync_at`, `last_error`

**`connector_sync_logs`**  
- `id`, `connector_id`, `started_at`, `finished_at`, `status`, `rows_ingested`, `error_message`（截断）

**`metric_definitions`**  
- `id`, `key`, `name`, `unit`, `aggregation`（sum/mean/…）, `segment_id` nullable, `connector_id` nullable  
- `participates_in_anomaly` bool, `value_kind`（`absolute`/`delta`）

**`metric_points`**（时序；大表可考虑按日分区或专用 TSDB）  
- `id`, `metric_id`, `segment_id`, `bucket_start`（datetime）, `value`（float）, `source_ref`（可追溯）

**`articles`**  
- `id`, `slug` optional, `title`, `summary`（短，非 LLM）, `body`（结构化 JSON 或 Markdown）  
- `segment_id`, `industry_id`  
- `content_type`（`third_party_derived`/`self_tool`/`self_model`/`application`）  
- `third_party_source`（nullable；**application 必填**）  
- `status`（`draft`/`published`）, `published_at`, `is_featured`  
- `created_at`, `updated_at`

**`hot_snapshots`**  
- `id`, `industry_id`  
- `generated_at`, `valid_until` optional  
- `payload_json`：`{ "trend_items": [...], "article_ids": [...], "model": "...", "prompt_version": "..." }`  
- `status`（`success`/`failed`）, `error_message`  
- `trigger`（`three_day_cron`/`weekly_cron`/`manual`/`system`；新调度以 `three_day_cron` 为准）

**`hot_settings`**（单行或 key-value）  
- `cron`, `top_n_trends`, `top_n_articles`, `fallback_strategy`, `llm_model_id`, `rate_limit_manual_rebuild`（分钟）

**`anomaly_settings`**  
- JSON 或列：窗口、阈值 L1/L2、冷却秒、板块 K 等

**`anomaly_events`**  
- `id`, `segment_id`, `metric_id` nullable, `score`, `level`（1/2）, `detail_json`, `created_at`, `read_at` nullable

**`inspirations`**  
- `id`, `segment_id`, `title`（当前版本可冗余）, `current_version_id` FK nullable

**`inspiration_versions`**  
- `id`, `inspiration_id`, `version_no`, `body`（Markdown/JSON）, `context_snapshot_json`  
- `created_by` FK `admin_users`, `created_at`, `status`（`draft`/`published`）

**`llm_usage_logs`**  
- `id`, `scenario`（enum）, `model`, `input_tokens`, `output_tokens`, `cost_usd` nullable  
- `admin_user_id` nullable（系统任务为空）, `ref_type`/`ref_id`（快照或灵感版本）  
- `created_at`, `success`, `error_code`

**`cms_pages`**  
- `slug` PK, `title`, `body_md`, `status`, `updated_at`, `published_at`

**`admin_users`**, **`admin_sessions`**, **`audit_logs`**, **`admin_settings`**（密码策略等）  
- 按本设计 **新建**；不必对齐旧项目字段名。

### 3.2 索引建议

- `metric_points (metric_id, bucket_start)`  
- `articles (industry_id, status, published_at DESC)`  
- `articles (segment_id, status)`  
- `hot_snapshots (industry_id, generated_at DESC)`  
- `llm_usage_logs (scenario, created_at)`  
- `anomaly_events (created_at DESC, read_at)`

### 3.3 库表落地

- **Greenfield**：空库执行迁移脚本一次性建表即可；**无**旧数据迁移义务。  
- 工具任选：Alembic / SQLAlchemy `create_all`（学习阶段可接受）。  

**引擎与「数据不可丢」（对齐需求 Master §4.1）**

- **上线/长期存数据**：优先 **PostgreSQL**（托管库自带备份最佳）；连接串走环境变量。  
- **SQLite**：仅用于 **本机学习**，或 **单机 VPS + 持久数据盘 + 你自己的备份脚本**；**不要**把 SQLite 文件放在无持久存储的免费 Serverless 实例上。  
- **备份**：生产路径下配置 **定期 dump** 或云厂商自动备份；发版前人工导出亦可作为兜底。

---

## 4. 安全设计

### 4.1 传输与边界

- **HTTPS**：真正部署到公网时再强制 TLS；本地 HTTP 即可。  
- **CORS**：仅允许自有前端源（5173/5174 开发、生产域）。  
- **管理 API**：**不得**挂在公网无鉴权路径；与公开 API **路由分离**，便于 WAF/限流策略不同。

### 4.2 认证与授权

- **管理端**：Session 或 JWT（短 TTL）；**密码** bcrypt/argon2；**登录失败锁定**（策略存 `admin_settings` 或环境变量）。  
- **RBAC**：`viewer`/`operator`/`admin` 声明式装饰器校验。  
- **公开 API**：只读；**禁止**任何写操作与 LLM 触发。

### 4.3 密钥与秘密

- **第三方 API Key、LLM Key**：仅环境变量或密钥管理服务；**数据库只存 `secret_ref` 或应用层加密**（AES-GCM + 主密钥在 env）。  
- **禁止**：日志打印密钥、响应体返回明文 Key、前端存储 Key。

### 4.4 大模型与提示

- **灵感 / 热门**：输入仅 **聚合摘要与 ID 列表**；禁止把原始第三方响应全文、PII、内部 DB 连接串写入 prompt。  
- **输出**：热门结果落库前做 **schema 校验**（文章 ID、指标 key 必须存在于 DB）。

### 4.5 限流与滥用

- **登录接口**：IP + 用户名维度限流。  
- **手动同步 / 手动重跑热门**：每用户 + 全局限流。  
- **公开 GET**：按 IP 轻量限流，防爬。

### 4.6 审计与日志

- 管理端敏感操作写 **`audit_logs`**（actor、action、target、diff 摘要）。  
- 应用日志 **脱敏**（Authorization、Cookie、query token）。

### 4.7 依赖与供应链

- 锁定依赖版本；CI 跑 `pip-audit` / `npm audit`（可选）。

---

## 5. 关键后台任务

| 任务 | 周期 | 行为 |
|------|------|------|
| `sync_connectors` | 按连接器 `min_interval` | 拉数 → 写 `metric_points` / `articles` |
| `compute_anomalies` | 每小时或每日 | 读时序 → 写 `anomaly_events` |
| `hot_rank_weekly` | 约每 3 天（APScheduler `IntervalTrigger(days=3)`） | 组装上下文 → LLM → 校验 → 写 `hot_snapshots`；`trigger` 字段为 `three_day_cron` |
| `inspiration_stale_flags` | 每日 | 根据异动与灵感绑定时间更新「环境可能已变」标记（若建字段） |

---

## 6. 文档修订

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 | 2026-04-18 | 首版：API + DB + 安全 + 任务 |
| v1.1 | 2026-04-18 | 学习项目：不兼容旧版、可全量重写；删「与现有代码映射」 |
| v1.2 | 2026-04-18 | §3.3：数据不可丢 → 优先 Postgres；SQLite 仅限持久盘+备份 |
| v1.3 | 2026-04-18 | 热门快照调度改为约每 3 天；`trigger` 增补 `three_day_cron`；LLM 场景名 `hot_rank_weekly` 仍用于非手动重建 |
