# Agent 趋势洞察平台

## 1. 文档目标

本文档定义一个面向全球 AI 开发者生态的 Agent 趋势洞察平台，核心目标是回答：

1. 开发者正在用 Agent 做什么（用途与场景）
2. 开发者做出了哪些应用（应用形态与交付物）
3. 哪些趋势是短期噪声，哪些是稳定变化（变与不变）

本方案覆盖完整功能需求与技术方案，支持持续迭代和上线运营。

---

## 2. 产品定位与范围

### 2.1 产品定位

平台定位为 **Agent 用途趋势雷达**，不是模型榜单站。  
模型和工具只作为趋势上下文，主分析对象为：

- 用途（Use Case）
- 能力组合（Capability Stack）
- 工作流模式（Workflow Pattern）
- 应用交付形态（Application Form）

### 2.2 MVP 范围（V1）

V1 聚焦公开、可合规获取的数据源：

- GitHub（主数据源）
- Hugging Face Spaces（应用补充）
- Hacker News / Product Hunt / Reddit（趋势辅助）
- MCP/Skills 生态索引仓库（生态侧证据）

V1 输出：

- 灵感墙（新增应用流）
- 趋势页（按日/周/月/季/年）
- 类别页（代码、工具、文生图、文生视频、skills、mcp 等）
- 证据链详情页

---

## 3. 用户角色与核心场景

### 3.1 用户角色

- 产品经理 / 创业者：寻找新方向与差异化机会
- 开发者 / 技术负责人：判断技术选型与场景热度
- 投资与研究人员：跟踪生态变化与阶段性拐点

### 3.2 核心场景

1. 发现过去 7/30 天新增的 Agent 应用类型  
2. 查看某用途在 12 周内是萌芽、爆发、成熟还是衰退  
3. 对比类别维度（代码、mcp、视频等）变化速度  
4. 查看趋势背后的证据（来源 URL、时间、项目）

---

## 4. 功能需求（FRD）

### 4.1 首页：趋势总览

- 时间切换：日、周、月、季、年
- 核心指标：
  - 活跃用途数
  - 新增应用数
  - 新兴趋势数
  - 衰退趋势数
- 趋势榜：
  - Top 增长用途
  - Top 新增能力组合
  - Top 应用形态

### 4.2 灵感墙（Inspiration Feed）

- 卡片字段：
  - `signal_id`（稳定主键，用于证据详情深链）
  - 应用标题
  - 用途标签
  - 工作流模式
  - 来源平台
  - 首次发现时间
- 支持筛选：
  - 类别（大模型、工具、代码、文生视频、文生图片、skills、mcp）
  - 时间窗口
  - 地区（可选，V2）

### 4.3 趋势分析页（Trend Explorer）

- 查看某个用途的时间序列
- 展示阶段标签：
  - 萌芽 / 爆发 / 成熟 / 衰退
- 展示趋势解释：
  - 增速
  - 持续性
  - 跨源共振
  - 证据置信度

### 4.4 证据链详情页

- 趋势的构成证据列表
- 每条证据显示：
  - 来源
  - URL
  - 抓取时间
  - 抽取字段
  - 质量分
- 支持“问题反馈/纠错”入口

### 4.5 管理后台（内部）

- Taxonomy 管理（用途分类、能力词典、别名映射）
- 数据源开关与抓取频率配置
- 趋势算法版本切换与回测结果对比
- 数据修正与下架处理（合规）

---

## 5. 非功能需求（NFR）

- 可用性（分阶段承诺）：
  - Beta/MVP（免费层）：不承诺公开 SLA，仅承诺可观测和故障告警
  - Growth（付费层）：站点与公开只读 API 月可用性目标 99.0%
  - Production（稳定层）：站点与公开只读 API 月可用性目标 99.5%
- 可追溯：每个趋势结果可回溯到原始证据
- 可扩展：支持新增数据源和新类别
- 可解释：每个趋势分数可解释
- 安全合规：遵守来源 ToS，支持删除请求
- 成本约束：MVP 阶段基础设施月成本目标控制在低预算区间，优先采用免费额度
- 公网访问：网站与公开 API 可通过 HTTPS 在公网访问，支持基础限流与防滥用

---

## 6. 趋势算法设计（可持续迭代）

### 6.1 设计原则

- 不追逐工具名，优先捕捉结构变化
- 快变层和慢变层分开建模
- 结果必须可解释、可回测、可版本化

### 6.2 五层抽象（变与不变）

1. 需求层（慢变，不变核心）  
2. 能力层（半稳定）  
3. 工作流层（慢变）  
4. 工具层（快变）  
5. 模型层（快变）

### 6.3 指标体系

- NoveltyScore：新词/新工具首次出现强度
- BurstScore：短周期爆发度
- AdoptionScore：用途占比增长
- PersistenceScore：连续周期出现率
- CrossSourceScore：跨源共振度
- EvidenceScore：证据质量

### 6.4 主评分公式（V1）

`TrendScore = 0.35*Adoption + 0.25*Persistence + 0.20*CrossSource + 0.10*Burst + 0.10*Novelty`

`Confidence = EvidenceScore * SourceDiversity * LabelStability`

### 6.5 生命周期状态机

- 萌芽：Novelty 高，Persistence 低
- 爆发：Burst 高且 Adoption 快速上升
- 成熟：Persistence 和 CrossSource 持续高
- 衰退：Adoption 与 CrossSource 连续下降

### 6.6 抗噪策略

- 新趋势至少连续 2-3 个窗口出现
- 至少 2 个来源共振才入榜
- 工具别名归一到能力层
- 去重（fork、镜像、转载）

### 6.7 迭代机制

- 双周节奏：
  - 误差评估
  - 标签修正
  - 权重更新
  - 历史回测
  - 算法版本发布

---

## 7. 数据区设计（Data Zones）

### 7.1 分层架构

- Raw Zone：原始 API 响应与抓取元数据
- Clean Zone：字段标准化、去重、实体归一
- Feature Zone：趋势特征计算结果
- Serve Zone：前端与 API 可查询聚合表
- Label Zone：人工标注和反馈真值

### 7.2 核心表设计（示例）

1. `raw_events`
- id, source, fetched_at, payload_json, payload_hash, terms_version

2. `normalized_events`
- id, event_time, source, project_id, developer_id_hash
- use_case, capability_stack, workflow_pattern, application_form
- category, stable_tags, volatile_tags, evidence_url, evidence_score
- signal_id, raw_event_id, taxonomy_version, normalization_version, pipeline_run_id

3. `entity_alias_dict`
- alias, canonical_name, entity_type, version, active

4. `evidence_signals`
- signal_id, raw_event_id, normalized_event_id, source
- trend_key, evidence_url, evidence_score, source_diversity, label_stability
- status(active/flagged/removed), created_at

5. `trend_features_daily`
- date, trend_key, adoption, persistence, burst, novelty, cross_source
- source_diversity, label_stability, sample_size, feature_job_id

6. `trend_scores_periodic`
- period_type(day/week/month/quarter/year), period_start, trend_key
- trend_score, confidence, lifecycle_stage, algo_version
- score_components_json, sample_size

7. `human_feedback`
- signal_id, feedback_type, corrected_label, operator, created_at

8. `removal_requests`
- id, request_type(owner/privacy/correction), requester_contact
- target_signal_id, target_project_id, reason, status
- submitted_at, resolved_at, resolver, resolution_note

9. `pipeline_runs`
- run_id, job_type, window_start, window_end, status
- idempotency_key, retries, started_at, finished_at, error_summary

### 7.3 存储方案

- Raw：S3 / MinIO / R2（JSON）
- Structured：PostgreSQL（OLTP + 轻量分析）
- Cache：Redis（热点接口）

---

## 8. 数据获取方案

### 8.1 数据源接入策略

优先使用官方公开 API，禁止绕过机制抓取。

1. GitHub API（主）
- 关键词与 topic 搜索
- 仓库、README、提交、Release、Issue

2. Hugging Face Hub/Spaces API
- 新增 Space、标签、更新时间、描述

3. 社区源（HN/PH/Reddit 等）
- 采用第三方开源 API 获取数据，并按标准注明来源
- 发布帖和讨论热度作为辅助信号

4. MCP/Skills 生态索引
- 新增 server/skill 与用途映射

### 8.2 抓取频率

- 每小时：增量抓取新事件
- 每日：补抓更新与重算特征
- 每周：趋势计算、阶段判定、榜单刷新

### 8.3 数据质量控制

- 去重率监控
- 缺失字段率监控
- API 错误率与重试队列
- 抽取置信度阈值与人工复核队列

---

## 9. 前后端分离技术架构

### 9.1 总体架构

- Frontend：Next.js（展示层）
- Backend API：FastAPI（查询与权限）
- Pipeline：独立采集与计算服务（Python）
- Data：PostgreSQL + 对象存储 + Redis

### 9.2 前端模块

- Dashboard（总览）
- Trend Explorer（趋势分析）
- Inspiration Feed（灵感墙）
- Evidence（证据详情）
- Admin（内部管理）

### 9.3 后端 API（统一权威清单）

本章节是前台公开 API 的唯一权威清单；后台管理 API 与 internal API 的唯一权威清单在 `17.3`。

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/inspirations`
- `GET /api/v1/trends`
- `GET /api/v1/trends/{trend_key}`
- `GET /api/v1/trends/{trend_key}/timeline`
- `GET /api/v1/categories`
- `GET /api/v1/signals/new`
- `GET /api/v1/evidences/{signal_id}`
- `GET /api/v1/meta/taxonomy`
- `GET /api/v1/meta/methodology`
- `POST /api/v1/compliance/removal-requests`
- `GET /api/v1/compliance/removal-requests/{ticket_id}?token=...`

API 契约约束（V1）：
- 统一响应：`code`, `message`, `data`, `request_id`
- 分页：`cursor`, `limit`（默认 20，最大 100）
- 常用筛选：`period`, `category`, `source`, `workflow_pattern`
- 限流：匿名读接口按 IP 限流，返回 `429` + `Retry-After`
- 对前台公开 API，以本清单为唯一权威；管理与 internal API 以 `17.3` 为唯一权威

---

## 10. 合规与法律风险控制

### 10.1 原则

- 仅处理公开数据
- 遵守各来源 ToS 与频率限制
- 不采集敏感个人信息
- 提供数据删除/申诉入口
- 全链路可追溯与可下架

### 10.2 站点策略

- 发布隐私政策和数据来源说明
- 趋势结果声明为“公开数据统计估计”
- 提供 “Data Removal Request” 页面

---

## 11. 部署方案

### 11.1 MVP 上线（快速）

- Frontend：Vercel（Hobby，免费）
- Backend：Render / Railway（先用免费层，冷启动可接受）
- DB：Supabase Postgres（免费层，配额告警）
- Raw 存储：Cloudflare R2（优先，成本低）/ S3
- 调度：GitHub Actions Cron
- 调度安全模式（二选一）：
  - 模式 A（推荐）：自托管 runner 放在私网，调用内网 internal API
  - 模式 B（托管简化）：调用受保护的调度入口（非匿名公网），必须启用短期服务令牌 + IP allowlist + 幂等键

### 11.1.1 免费优先部署基线（推荐起步）

- 域名与公网：
  - 有域名时：使用自有域名 + Cloudflare（免费 DNS、HTTPS 证书、基础防护）
  - 无域名时：使用平台默认公网地址（如 `*.vercel.app`、`*.onrender.com`、`*.up.railway.app`）
  - 前端直接公网访问，后端 API 通过独立公网地址暴露
- 组件选择（免费优先）：
  - 前端：Vercel Hobby
  - 后端：Render Free Web Service（或 Railway 免费额度）
  - 数据库：Supabase Free Postgres
  - 对象存储：Cloudflare R2（免费额度内优先）
  - 任务调度：GitHub Actions Scheduled Workflow
  - 监控：Sentry Free + UptimeRobot 免费探活
- 能力边界：
  - 接受免费层休眠/冷启动
  - 非核心任务延迟执行（例如夜间批量重算）

### 11.1.4 无域名上线方案（必备）

- 目标：
  - 在没有购买域名的情况下，快速实现公网访问并验证产品价值
- 推荐地址形态：
  - 前端：`https://<project>.vercel.app`
  - 后端：`https://<project>.onrender.com` 或 `https://<project>.up.railway.app`
- 前后端联通配置：
  - 前端配置 `NEXT_PUBLIC_API_BASE_URL` 指向后端公网地址
  - 后端 CORS 白名单允许前端默认域名（`https://<project>.vercel.app`）
- 鉴权与安全建议：
  - MVP 阶段优先 token 方案，避免跨域 cookie 复杂度
  - API 增加基础限流和请求日志，防止公开地址被滥用
- 运维约束：
  - Preview 环境与 Production 环境使用不同 API 地址，禁止混用
  - 后端地址变更时必须更新 CORS 白名单与前端环境变量
- 适用阶段：
  - 0-1 阶段产品验证、内测和小规模公开访问
- 升级路径：
  - 后续购买域名后，仅需切换 DNS 与环境变量，不影响核心架构

### 11.1.2 成本控制策略（必须执行）

- 数据采集侧：
  - 只做增量抓取，限制全量回刷频率
  - 为每个来源配置配额和请求预算（小时/天）
  - 对重复资源使用 ETag/If-Modified-Since，减少无效请求
- 存储侧：
  - Raw 数据按天分区，超过保留期转冷或归档压缩
  - 聚合结果入库，避免前端高频查询扫描明细
- 计算侧：
  - 趋势计算按类别分批执行，错峰调度
  - 使用预计算表 + Redis 缓存热点接口
- 服务侧：
  - 接口分页 + 限流 + 防刷
  - 静态资源全量 CDN 缓存
- 预算闸门（触发即降级）：
  - 任一数据源日配额使用率 >= 85%：自动降频到日级采集
  - 月度任务运行时间使用率 >= 80%：关闭非核心回刷任务
  - 月预算预测超过档位上限：仅保留 P0 页面所需数据任务

### 11.1.3 月度预算建议（MVP）

- 预算档位 A（0 成本起步）：
  - 目标：先验证产品价值
  - 方案：全部免费层 + 日级任务为主（默认不启用小时级）
  - 成本上限：0 美元（超出即自动降级任务频率）
- 预算档位 B（小额低成本）：
  - 目标：降低冷启动、提高稳定性
  - 方案：后端/数据库升到入门付费层，保持对象存储低成本
  - 成本上限：50 美元/月
- 预算档位 C（增长期）：
  - 目标：支撑稳定公网访问与更高更新频率
  - 方案：托管 DB 升配 + 独立任务执行器 + 可观测性增强
  - 成本上限：200 美元/月

### 11.2 生产上线（稳定）

- Frontend：Vercel + CDN
- Backend：Kubernetes / ECS
- DB：托管 Postgres（主从 + 备份）
- Pipeline：Airflow / Prefect
- 监控：Sentry + Prometheus + Grafana

### 11.3 CI/CD

- PR 检查：lint/test/typecheck
- 主干自动部署
- 数据任务与应用任务分离部署

### 11.4 公网访问与安全基线

- 全站 HTTPS，强制 TLS 跳转
- API 网关限流（按 IP / token）
- 只暴露必要端口，数据库仅内网访问
- 管理后台仅允许受控账号（MFA 推荐）
- 关键密钥通过平台 Secret 管理，不落盘
- 无域名阶段同样执行以上安全基线，不因使用平台默认域名而降低标准

---

## 12. 开发计划与里程碑

### 12.1 Phase 1（2 周，MVP）

- 完成数据分层与 GitHub 采集器
- 完成标准化抽取与基础趋势评分
- 上线 P0 页面：
  - `/`、`/inspirations`、`/trends`、`/trend/[trendKey]`
  - `/categories`、`/methodology`、`/evidence/[signalId]`
  - `/legal/privacy`、`/legal/terms`、`/legal/data-sources`、`/legal/removal-request`
  - `/admin`、`/admin/review`

### 12.2 Phase 2（2-4 周）

- 接入 HF 与社区数据源
- 增加生命周期状态机与解释模块
- 上线证据链详情与反馈纠错

### 12.3 Phase 3（持续）

- 支持区域维度与行业维度
- 算法从规则版升级到学习版
- 开放 B2B API 与订阅能力

---

## 13. 验收标准（Definition of Done）

- 功能可用：
  - 时间维度（日/周/月/季/年）可切换
  - 类别维度可筛选，筛选状态可通过 URL 复现
  - 趋势结果可查看证据链，且每个趋势详情至少关联 1 条有效 evidence
- 数据可用：
  - 核心数据任务日运行成功率 >= 95%（按自然周统计）
  - 去重率与缺失率指标可见，且异常会触发告警
- 算法可用：
  - 分数可解释（返回 score_components）
  - 阶段可判定（生命周期标签可追溯到规则阈值）
  - 历史可回测（至少保留最近 12 周对比结果）
- 合规可用：
  - 来源说明完整（每个数据源有 ToS 与使用说明）
  - 删除/下架请求流程可执行，工单状态可追踪，处理时限可统计
- 安全可用：
  - `/internal/*` 仅内网可达或采用强鉴权，不对匿名公网开放
  - Admin 操作全量审计，关键操作可追溯

### 13.1 上线门禁（与 22.3 一致）

- P0 缺陷数 = 0
- 核心 API 契约测试通过率 = 100%
- 核心页面端到端用例通过率 >= 95%
- 核心数据任务日运行成功率 >= 95%

### 13.2 核心范围清单（用于测试与发布）

- 核心页面（对应 13.1 的 E2E 统计）：
  - `/`、`/inspirations`、`/trends`、`/trend/[trendKey]`、`/evidence/[signalId]`、`/categories`、`/methodology`
- 关键合规页面（独立合规检查，不计入核心 E2E 通过率分母）：
  - `/legal/privacy`、`/legal/terms`、`/legal/data-sources`、`/legal/removal-request`
- 核心后台页面（独立后台回归）：
  - `/admin`、`/admin/review`
- 核心 API：
  - `GET /api/v1/dashboard/summary`
  - `GET /api/v1/inspirations`
  - `GET /api/v1/trends`
  - `GET /api/v1/trends/{trend_key}`
  - `GET /api/v1/trends/{trend_key}/timeline`
  - `GET /api/v1/categories`
  - `GET /api/v1/meta/methodology`
  - `GET /api/v1/meta/taxonomy`
  - `GET /api/v1/signals/new`
  - `GET /api/v1/evidences/{signal_id}`
  - `POST /api/v1/compliance/removal-requests`
  - `GET /api/v1/compliance/removal-requests/{ticket_id}?token=...`
- 核心任务：
  - `collect`, `normalize`, `feature`, `trend`
- 数据质量阈值（用于 13.1 与 22.3）：
  - 去重率异常告警阈值：单日重复事件占比 > 15%
  - 缺失字段告警阈值：关键字段缺失占比 > 10%
  - 首屏关键图表 P95 加载：<= 3 秒（缓存命中场景）

---

## 14. 风险与应对

- 数据源限流或政策变化：
  - 多源冗余 + 缓存 + 降级策略
- 标签体系漂移：
  - 双周 taxonomy 评审与版本化
- 误报趋势：
  - 增加跨源门槛 + 人工复核通道
- 成本不可控：
  - 冷热分层存储 + 任务分级频率

---

## 15. 附录：V1 分类建议

### 15.1 一级类别

- 大模型
- 工具
- 代码
- 文生视频
- 文生图片
- skills
- mcp

### 15.2 Agent 用途（建议初版）

- Coding Agent
- Workflow Automation Agent
- Customer Support Agent
- Research Agent
- Data Analyst Agent
- Content Agent（文案/多媒体）
- Video Production Agent
- Image Production Agent
- Personal Productivity Agent

### 15.3 工作流模式

- Single Agent
- Multi-Agent
- Human-in-the-Loop
- Tool-Orchestrated Agent

---

## 16. 结论

该方案通过“数据区分层 + 可解释趋势算法 + 前后端分离架构 + 合规治理”实现可持续演进。  
平台应长期坚持“关注 Agent 在做什么”而非“工具名称榜单”，从而稳定捕捉生态中的真实变化和可复用灵感。

---

## 17. 网站页面规划（前后端完整）

本章节定义可直接进入设计与开发的页面级规划，覆盖前台用户端、后台管理端和后端服务模块。

### 17.1 前台网站页面规划（用户可见）

1. 页面：`/`（首页总览）
- 目标：让用户 30 秒内看到“当前最重要趋势”
- 核心模块：
  - 顶部 KPI（新增应用数、活跃用途数、新兴趋势数、衰退趋势数）
  - 热门趋势榜（按周默认）
  - 趋势变化折线（支持日/周/月/季/年）
  - 快速筛选（类别、时间）
- 主要交互：
  - 点击趋势项进入详情页
  - 切换时间粒度联动所有图表

2. 页面：`/inspirations`（灵感墙）
- 目标：发现“最近谁在用 Agent 做了什么”
- 核心模块：
  - 卡片流（项目名、用途、模式、来源、首次出现时间）
  - 过滤器（类别、用途、工作流模式、来源平台、时间）
  - 排序（最新、增长快、证据强）
- 主要交互：
  - 卡片点击进入证据详情
  - 一键收藏或加入观察列表（V2）

3. 页面：`/trends`（趋势分析）
- 目标：分析某用途是否在真实增长
- 核心模块：
  - 趋势列表与搜索
  - 时间序列图（占比、增速、跨源共振）
  - 生命周期标签（萌芽/爆发/成熟/衰退）
  - 趋势解释面板（评分构成）
- 主要交互：
  - 多趋势对比（最多 3 条）
  - 导出图表（PNG/CSV，V2）

4. 页面：`/categories`（类别洞察）
- 目标：按大类看生态变化
- 核心模块：
  - 类别矩阵：大模型、工具、代码、文生视频、文生图片、skills、mcp
  - 每类 Top 用途与增长点
  - 类别间迁移趋势（例如从工具向 mcp 偏移）

5. 页面：`/signals/new`（新兴信号）
- 目标：优先发现“新出现但增速快”的方向
- 核心模块：
  - 新词榜（受控展示，去噪后）
  - 新用途榜
  - 新模式榜
  - 告警阈值说明（为什么入榜）

6. 页面：`/trend/[trendKey]`（趋势详情）
- 目标：做深度验证和决策
- 核心模块：
  - 趋势画像（定义、所属类别、相关能力）
  - 历史轨迹图
  - 证据链列表（可追溯 URL）
  - 相似趋势推荐

7. 页面：`/evidence/[signalId]`（证据详情）
- 目标：让用户信任结果
- 核心模块：
  - 原始来源信息
  - 抽取结果与置信度
  - 归类结果与分类版本
  - 问题反馈入口（纠错/下架申请）

8. 页面：`/methodology`（方法说明）
- 目标：透明化算法与数据来源
- 核心模块：
  - 数据来源清单
  - 趋势评分公式
  - 更新频率说明
  - 已知偏差与限制

9. 页面：`/legal`（合规与数据说明）
- 子页：
  - `/legal/privacy`
  - `/legal/terms`
  - `/legal/data-sources`
  - `/legal/removal-request`

### 17.2 后台页面规划（内部运营）

1. 页面：`/admin`（后台首页）
- 采集健康状态、任务成功率、昨日新增事件数、告警摘要

2. 页面：`/admin/sources`
- 数据源开关、抓取频率、配额预算、错误重试策略

3. 页面：`/admin/taxonomy`
- 用途分类、能力标签、工作流模式维护
- 支持版本发布与回滚

4. 页面：`/admin/alias`
- 工具/模型别名映射管理（OpenClaw/Hermes 等）
- 支持批量导入和冲突处理

5. 页面：`/admin/review`
- 低置信度记录人工复核
- 纠错流转（待处理、已处理、驳回）

6. 页面：`/admin/trend-lab`
- 趋势算法参数管理（权重、阈值）
- 版本对比与回测看板

7. 页面：`/admin/compliance`
- 下架请求处理
- 数据删除申请处理
- 操作审计日志

### 17.3 后端服务模块规划（API 与任务）

1. 公共查询 API（给前台）
- `GET /api/v1/dashboard/summary`
- `GET /api/v1/inspirations`
- `GET /api/v1/trends`
- `GET /api/v1/trends/{trend_key}`
- `GET /api/v1/trends/{trend_key}/timeline`
- `GET /api/v1/categories`
- `GET /api/v1/signals/new`
- `GET /api/v1/evidences/{signal_id}`
- `GET /api/v1/meta/taxonomy`
- `GET /api/v1/meta/methodology`
- `POST /api/v1/compliance/removal-requests`
- `GET /api/v1/compliance/removal-requests/{ticket_id}?token=...`

2. 后台管理 API（给 admin）
- `GET /api/v1/admin/overview`
- `GET /api/v1/admin/sources`
- `POST /api/v1/admin/sources/{id}/toggle`
- `GET /api/v1/admin/taxonomy`
- `POST /api/v1/admin/taxonomy/publish`
- `GET /api/v1/admin/alias`
- `POST /api/v1/admin/alias/import`
- `GET /api/v1/admin/review/queue`
- `POST /api/v1/admin/review/{id}/resolve`
- `GET /api/v1/admin/trend-lab/experiments`
- `POST /api/v1/admin/trend-lab/experiments/{id}/run`
- `POST /api/v1/admin/trend-lab/experiments/{id}/publish`
- `GET /api/v1/admin/compliance/removal-requests`
- `POST /api/v1/admin/compliance/removal-requests/{id}/resolve`
- `GET /api/v1/admin/audit-logs`

3. 数据任务 API（内部）
- `POST /internal/collect/run`
- `POST /internal/normalize/run`
- `POST /internal/feature/run`
- `POST /internal/trend/run`
- `POST /internal/reindex/run`
- 安全要求：
  - 默认仅内网访问（模式 A）
  - 若采用模式 B，对公网不可匿名访问，必须服务鉴权
  - 自托管 runner 场景启用 IP allowlist；托管 runner 场景使用 OIDC + 短期令牌替代固定 IP
  - 必须携带短期服务令牌和 `idempotency_key`
  - 每次触发返回 `run_id`，可查询执行状态
  - 若使用 GitHub Actions，优先使用 OIDC 换取短期令牌，禁止长期明文密钥
- 运行状态 API：
  - `GET /internal/runs/{run_id}`
  - 响应必须包含：`run_id`, `job_type`, `status`, `retries`, `started_at`, `finished_at`
  - `status` 枚举：`queued|running|success|failed|cancelled`
- 失败处理：
  - 指数退避重试，超过阈值进入失败队列并告警
  - 相同 `idempotency_key` 的重复请求必须幂等
  - 重复请求返回同一 `run_id`（若任务未过期）

### 17.4 页面与权限模型

- Visitor（匿名用户）：
  - 可访问前台洞察页面、方法和合规页面
- Analyst（登录用户，V2）：
  - 额外使用收藏、对比、导出能力
- Admin（内部）：
  - 访问 `/admin/*`，可进行配置、复核、发布和合规处理

### 17.5 前后端交互原则

- 前端仅调用公开 API 与管理 API，不直接访问数据库
- 所有图表默认读取预聚合数据，避免实时重计算
- 大查询分页返回，控制响应体积
- API 响应统一结构：`code`、`message`、`data`、`request_id`

### 17.6 页面开发优先级（MVP）

- P0（必须）：
  - `/`、`/inspirations`、`/trends`、`/trend/[trendKey]`
  - `/categories`、`/methodology`
  - `/legal/privacy`、`/legal/terms`、`/legal/data-sources`
  - `/legal/removal-request`
  - `/evidence/[signalId]`（可独立页或趋势详情内嵌完整证据视图）
  - `/admin`、`/admin/review`
- P1（建议）：
  - `/signals/new`
  - `/admin/taxonomy`、`/admin/sources`
- P2（后续）：
  - 收藏、导出、订阅告警、多语言

### 17.7 页面验收标准（补充）

- 任意趋势详情必须可追溯到至少 1 条来源证据
- 时间粒度切换在关键页面响应一致（方向不矛盾且可解释）
- 后台修改 taxonomy 后，版本发布可在前台生效
- 无域名部署下（平台默认域名）前后端可正常联通
- 筛选条件可通过 URL 分享并复现同一视图

---

## 18. 可视化与图表设计方案（必须好用）

本平台不以“图表数量”取胜，而以“可读、可比较、可行动”取胜。  
所有图表设计遵循：先回答问题，再选择图形。

### 18.1 图表设计原则

- 一图一问题：每张图只回答一个核心问题
- 默认可读：首次打开无需培训即可理解
- 支持比较：至少支持时间对比或类别对比
- 支持追溯：图上点选可下钻到证据链
- 低干扰：避免过度动画、3D、花哨配色

### 18.2 图表矩阵（问题 -> 图表类型）

1. 趋势变化（随时间）
- 图表：折线图 / 面积图
- 用途：展示 use_case、capability、category 的变化轨迹
- 交互：时间粒度切换（日/周/月/季/年）、同比/环比切换

2. 占比结构（某时点）
- 图表：堆叠条形图 / 树图（Treemap）
- 用途：展示类别占比、用途占比
- 交互：点击某块筛选全局视图

3. 增长对比（多个对象）
- 图表：分组柱状图 / 排行榜条形图
- 用途：Top 增长用途、Top 新增模式
- 交互：切换“绝对增长/相对增长”

4. 生命周期判断
- 图表：阶段泳道图 / 状态时间线
- 用途：展示趋势从萌芽到衰退的状态变化
- 交互：悬浮显示阶段判定依据

5. 关联关系（用途与能力）
- 图表：桑基图 / 网络关系图（V2）
- 用途：展示 use_case 与 capability 组合关系
- 交互：点击节点高亮上下游

6. 地区分布（V2）
- 图表：地图热力图
- 用途：显示地区活跃度
- 交互：地图点击联动趋势列表

7. 证据可信度
- 图表：箱线图 / 分布柱状图
- 用途：展示 evidence_score 分布与异常值
- 交互：过滤低质量证据

### 18.3 页面图表清单（MVP）

- `/` 首页：
  - KPI 数字卡（4 个）
  - Top 趋势条形图
  - 总体趋势折线图
- `/inspirations`：
  - 新增应用时间柱状图
  - 来源平台占比图
- `/trends`：
  - 多趋势对比折线图
  - 生命周期状态图
  - 评分构成雷达图（可选）
- `/trend/[trendKey]`：
  - 单趋势历史轨迹图
  - 证据质量分布图
  - 相关趋势关联图（V2）

### 18.4 图表交互规范（可用性关键）

- 全局统一筛选器：
  - 时间窗口、类别、来源平台、工作流模式
- 图表联动：
  - 在任意图表点击一项，刷新同页其他图表
- 悬浮信息：
  - 必含“当前值、变化率、样本量、更新时间”
- 下钻路径：
  - 图表点选 -> 趋势详情 -> 证据详情
- 导出能力（V2）：
  - 图片导出、CSV 导出

### 18.5 视觉与可访问性规范

- 色彩：
  - 采用色盲友好配色，避免红绿冲突
- 字体与标注：
  - 轴标签简洁，单位明确（%/数量）
- 响应式：
  - 桌面优先，移动端保留核心图表与筛选
- 可访问性：
  - 图表需提供文本摘要（屏幕阅读器可读）

### 18.6 技术实现建议

- 图表库：
  - 首选 ECharts（功能完整，适合复杂交互）
  - 轻量场景可用 Recharts（简单组件化）
- 前端状态管理：
  - 统一查询参数状态（URL Query）确保可分享链接
- 性能优化：
  - 预聚合数据优先
  - 大数据量图表按需抽样
  - 图表懒加载与骨架屏

### 18.7 图表可用性验收标准

- 用户在 30 秒内可回答“最近增长最快的 3 个用途”
- 同一趋势在不同时间粒度下表现一致且可解释
- 点击任一关键图形元素可进入对应详情页
- 关键页面首屏图表加载时间可控（依赖缓存和预计算）
- 不使用仅靠颜色区分语义的关键图表
- 关键图表均提供文本摘要或等价数据表视图

---

## 19. 多角色文档评审机制（架构/开发/测试）

为保证方案可实施、可交付、可上线，本项目采用三类技术角色联合评审。每类角色都有独立“通过标准”，任一关键项不通过则不进入下一阶段。

### 19.1 架构评审（Architecture Review）

- 评审角色：
  - 技术架构师（Owner）
  - 数据架构师
  - 安全/合规负责人
- 评审目标：
  - 验证整体架构可扩展、可追溯、可控成本
- 核心检查项：
  - 前后端分离边界是否清晰（页面层/API 层/数据任务层）
  - 数据分层（Raw/Clean/Feature/Serve/Label）是否闭环
  - 趋势算法是否可解释、可版本化、可回测
  - 公网访问与安全基线是否满足（HTTPS、限流、密钥管理）
  - 无域名部署与后续有域名升级路径是否清晰
  - 成本控制策略是否可执行（免费层边界与升级阈值）
- 通过标准：
  - 关键架构风险项均有应对策略
  - 至少完成一次“从抓取到展示”的端到端链路走查

### 19.2 开发评审（Engineering Review）

- 评审角色：
  - 前端负责人
  - 后端负责人
  - 数据工程负责人
- 评审目标：
  - 验证需求可拆分、接口可实现、交付节奏可达成
- 核心检查项：
  - 页面路由、组件模块和 API 契约是否一一对应
  - 查询接口是否优先使用预聚合数据
  - 抓取任务、清洗任务、计算任务是否可独立部署
  - 错误处理、重试机制、幂等机制是否定义
  - 环境变量与密钥是否统一管理
  - 日志、追踪、监控埋点是否预留
- 通过标准：
  - 完成 P0 功能的任务拆解（含工时估算）
  - 完成接口 Mock 与至少一条页面联调验证

### 19.3 测试评审（QA Review）

- 评审角色：
  - 测试负责人
  - 自动化测试工程师
  - 业务验收代表
- 评审目标：
  - 验证核心链路正确、稳定、可回归
- 核心检查项：
  - 功能测试：筛选、对比、下钻、证据追溯
  - 数据测试：去重、归类、时间窗口聚合正确性
  - 接口测试：鉴权、分页、限流、异常码
  - 性能测试：首页与趋势页核心图表加载时延
  - 安全测试：越权访问、公开 API 滥用、敏感信息泄露
  - 回归策略：taxonomy 或算法版本更新后的回归范围
- 通过标准：
  - 通过标准与 `13.1`、`22.3` 完全一致
  - 阻断级缺陷（P0）为 0，关键缺陷有明确修复计划

---

## 20. 用户角色验收（跨行业，至少 10 类）

本章节用于“用户视角验收”，不按 AI 熟练度分层，而按行业与岗位目标分层。每个角色均需要定义其关键任务与成功判定。

### 20.1 用户角色清单（12 类）

1. 电商行业产品经理
- 目标：发现可提升转化和客服效率的 Agent 用例
- 关注页面：首页、灵感墙、趋势详情

2. 金融行业业务分析师
- 目标：识别合规前提下可落地的自动化场景
- 关注页面：趋势分析、证据详情、方法说明

3. 教育行业教学产品负责人
- 目标：寻找学习辅导、课程生成、批改助理类 Agent 机会
- 关注页面：类别洞察、灵感墙

4. 医疗健康行业运营负责人
- 目标：观察问答分诊、流程协同等应用趋势
- 关注页面：趋势分析、合规说明

5. 制造业数字化经理
- 目标：跟踪质检、运维、知识库助手等 Agent 方向
- 关注页面：趋势页、新兴信号页

6. 媒体内容平台主管
- 目标：判断文生图/文生视频相关 Agent 的应用机会
- 关注页面：类别页、灵感墙

7. 游戏行业制作人
- 目标：跟踪剧情生成、资产生产、运营助手趋势
- 关注页面：趋势页、证据详情

8. 物流行业运营经理
- 目标：发现调度、异常处理、客服自动化 Agent 场景
- 关注页面：首页、趋势分析

9. 法律行业知识管理负责人
- 目标：观察检索、归档、起草辅助 Agent 的可行方向
- 关注页面：趋势详情、方法说明、证据链

10. 人力资源负责人
- 目标：评估招聘筛选、培训支持、员工服务 Agent 机会
- 关注页面：灵感墙、类别洞察

11. 政务数字化项目经理
- 目标：识别公共服务流程中的 Agent 试点方向
- 关注页面：趋势分析、合规页面

12. 初创公司创始人
- 目标：快速找到高增长、低竞争的 Agent 创业方向
- 关注页面：首页、新兴信号、趋势详情

### 20.2 用户验收任务（统一）

每类用户至少完成以下任务并记录反馈：

- 任务 A：在 5 分钟内找到本行业相关的 3 个增长方向
- 任务 B：对 1 条趋势完成“图表 -> 详情 -> 证据”的下钻验证
- 任务 C：基于平台信息形成 1 条可执行行动建议

### 20.3 用户验收通过标准

- 至少 10 类角色完成验收任务且成功率 >= 80%
- 大多数角色可独立完成下钻，不依赖培训
- 反馈中的高频问题形成版本修复清单
- 关键页面在不同行业角色中均具备可解释性

---

## 21. 合规落地附录（P0）

### 21.1 数据源 ToS 合规矩阵（V1）

每个数据源都必须记录以下字段：`terms_url`、`terms_version`、`allowed_usage`、`prohibited_usage`、`attribution_rule`、`retention_limit_days`、`commercial_use`、`last_reviewed_at`。

- GitHub API：
  - terms_url：https://docs.github.com/en/site-policy
  - terms_version：以审核当日记录为准
  - allowed_usage：公开仓库元数据与公开文本统计
  - prohibited_usage：绕过鉴权抓取、违反速率限制、私有数据抓取
  - attribution_rule：展示仓库链接、抓取时间
  - retention_limit_days：365（Raw 可归档）
  - commercial_use：按条款允许范围执行
  - last_reviewed_at：每季度复审
- Hugging Face Hub/Spaces API：
  - terms_url：https://huggingface.co/terms-of-service
  - terms_version：以审核当日记录为准
  - allowed_usage：公开模型/Space 元数据趋势统计
  - prohibited_usage：绕过权限机制、违反平台条款
  - attribution_rule：展示来源 URL、更新时间
  - retention_limit_days：365
  - commercial_use：按条款允许范围执行
  - last_reviewed_at：每季度复审
- Hacker News：
  - terms_url：https://www.ycombinator.com/legal/
  - terms_version：以审核当日记录为准
  - allowed_usage：公开帖子趋势辅助信号
  - prohibited_usage：未经授权的批量内容再分发
  - attribution_rule：展示帖子来源链接
  - retention_limit_days：180
  - commercial_use：按条款允许范围执行
  - last_reviewed_at：每月复审
- Product Hunt：
  - terms_url：https://www.producthunt.com/terms
  - terms_version：以审核当日记录为准
  - allowed_usage：公开发布趋势辅助信号
  - prohibited_usage：未经授权的批量内容再分发
  - attribution_rule：展示来源链接
  - retention_limit_days：180
  - commercial_use：按条款允许范围执行
  - last_reviewed_at：每月复审
- Reddit：
  - terms_url：https://www.redditinc.com/policies
  - terms_version：以审核当日记录为准
  - allowed_usage：公开帖子趋势辅助信号
  - prohibited_usage：违反 API/内容条款的再分发
  - attribution_rule：展示来源链接
  - retention_limit_days：180
  - commercial_use：按条款允许范围执行
  - last_reviewed_at：每月复审
- MCP/Skills 索引仓库：
  - terms_url：对应仓库许可证与平台条款
  - terms_version：以审核当日记录为准
  - allowed_usage：公开索引变化统计
  - prohibited_usage：违反开源许可证条款的再利用
  - attribution_rule：展示仓库与提交链接
  - retention_limit_days：365
  - commercial_use：按许可证允许范围执行
  - last_reviewed_at：每季度复审

### 21.2 删除/下架处理状态机

- 状态：`submitted -> reviewing -> approved/rejected -> executed -> notified`
- 处理流程：
  - 提交工单（`removal_requests`）
  - 校验目标对象（signal/project）
  - 审核并记录处理意见
  - 执行级联操作：
    - `evidence_signals.status` 更新为 `removed`
    - Serve 层相关聚合标记待重算
    - 触发受影响 `trend_key` 重算任务
  - 通知申请方并记录完成时间
- SLA：
  - 普通纠错请求：7 个自然日内处理
  - 隐私相关请求：3 个自然日内优先处理
- 申请人可追踪：
  - 提交后返回 `ticket_id` 与查询令牌
  - 申请人可通过 `GET /api/v1/compliance/removal-requests/{ticket_id}?token=...` 查看状态
  - 状态变更必须触发通知（邮件或站内消息）

### 21.3 审计与可追溯要求

- Admin 关键操作必须写入审计日志（操作者、时间、对象、动作、原因）
- 审计日志默认保留 180 天（可按法务要求延长）
- 所有趋势分数应可追溯至：
  - `trend_scores_periodic` -> `trend_features_daily` -> `evidence_signals` -> `normalized_events` -> `raw_events`

### 21.4 隐私与法域说明（V1）

- 面向全球公开访问场景，默认按“公开数据统计用途”处理
- 默认运营主体、联系邮箱、法务联系地址必须在隐私页固定展示
- 默认主适用法域与争议处理路径需在隐私页和条款页一致声明
- MVP 默认法域基线：
  - 运营主体：AISoul Project Operator（上线前替换为实际法定主体名称）
  - 主适用法：运营主体注册地法律
  - 争议处理方式：运营主体注册地有管辖权法院
- 必须在 `/legal/privacy` 明确：
  - 数据控制方主体与联系方式
  - 子处理者（托管平台）列表
  - 数据保留策略与删除请求入口
  - 跨区域传输说明与适用法域声明

---

## 22. 测试策略与发布门禁（P0）

### 22.1 测试分层

- 功能测试：筛选、排序、下钻、证据查看、反馈提交
- 数据测试：去重、聚合、时间窗计算、生命周期阶段判定
- 接口测试：参数校验、分页、错误码、限流
- 性能测试：核心页面首屏与关键 API 响应
- 安全测试：匿名访问限制、admin 越权、internal API 暴露检查

### 22.2 回归触发条件

以下变更必须触发回归：
- taxonomy 版本发布
- 算法权重或阈值调整
- 新数据源上线
- 删除/下架流程逻辑变更
- 数据模型字段或聚合口径变更
- 公开 API 契约变更
- internal 任务幂等或调度安全策略变更
- CORS/鉴权/环境变量策略变更

### 22.3 发布门禁

- P0 缺陷数必须为 0
- 核心 API 契约测试通过率 100%
- 核心页面端到端用例通过率 >= 95%
- 数据任务日运行成功率 >= 95%
- 以上门禁口径以 `13.1` 与 `13.2` 为唯一统计基准

---

## 23. 运维与升级触发条件（P0）

### 23.1 监控最小集合

- 站点可用性、API 错误率、P95 响应时间
- 任务成功率、任务延迟（lag）
- 数据源配额使用率
- 月度成本预测
- 合规处理监控：删除工单超时率、通知发送成功率

### 23.4 页面到 API 映射矩阵（P0 页面）

- `/` -> `GET /api/v1/dashboard/summary`, `GET /api/v1/trends`
- `/inspirations` -> `GET /api/v1/inspirations`
- `/trends` -> `GET /api/v1/trends`, `GET /api/v1/meta/taxonomy`
- `/trend/[trendKey]` -> `GET /api/v1/trends/{trend_key}`, `GET /api/v1/trends/{trend_key}/timeline`
- `/evidence/[signalId]` -> `GET /api/v1/evidences/{signal_id}`
- `/categories` -> `GET /api/v1/categories`
- `/methodology` -> `GET /api/v1/meta/methodology`

### 23.2 档位升级触发

- 从档位 A 升 B：
  - 连续 7 天出现冷启动导致核心接口失败，或
  - 日均活跃访问超过免费层稳定阈值
- 从档位 B 升 C：
  - 月度成本接近档位 B 上限且业务持续增长，或
  - 需要小时级稳定更新且现有调度无法满足

### 23.3 降级策略

- 优先关闭非核心数据源和非核心重算任务
- 保留首页、趋势页、证据页核心查询能力
- 页面显式提示“数据更新时间与降级状态”

