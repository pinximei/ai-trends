# Agent 趋势洞察平台（定稿 v2）

## 1. 目标与边界

平台核心目标：

1. 发现全球开发者正在用 Agent 做什么（用途与能力组合）
2. 跟踪新兴与持续趋势（不是工具名热词榜）
3. 为用户提供可追溯证据链与可验证行动建议

产品边界（必须明确）：

- 本平台是「公开开发者生态趋势雷达」，不是行业采购建议系统
- 趋势结果是公开数据统计估计，不直接代表行业合规与商业结果
- 强监管行业（金融/医疗/政务/法律）默认需要二次验证

---

## 2. 版本策略与两轮审核

- Round 1（已完成）：文档预审（架构/后端/QA/合规/用户）
- Round 2（开发后）：实现复审（契约、E2E、用户复测）

发布条件：

- 文档与实现均满足 P0=0
- 通过 `13.1` 与 `22.3` 门禁
- 用户审核满足配额与通过率门槛

---

## 3. 用户与场景（定稿口径）

用户分层：

- 核心：产品经理、开发者、技术负责人、创业者、研究人员
- 扩展：12 类跨行业角色（用于“方向验证”而非直接上线决策）
- 反馈面板：岗位、公司规模、决策层级同时覆盖，避免单一视角

统一任务：

- A：5 分钟内找到 3 个增长方向（或 3 个可验证假设）
- B：完成「图表 -> 趋势详情 -> 证据」下钻
- C：输出 1 条可执行下一步（必须包含验证动作）

用户审核配额（Round 1 与 Round 2）：

- 总样本数 >= 24
- 行业角色覆盖 >= 12 类
- 岗位覆盖：产品/业务/运营/技术/管理
- 公司规模覆盖：小（<50）/中（50-500）/大（>500）
- 决策层级覆盖：执行层/负责人/决策层

24 人审核后新增刚性要求（必须实现）：

- 可理解性：
  - 首页必须明确“数据来源、统计口径、更新时间”
  - 关键图表必须展示样本量与置信度提示
- 可用性：
  - 全局筛选在首页/趋势/灵感墙之间保持一致
  - 下钻到证据页后，返回时保留筛选与时间上下文
  - 移动端可完成任务 A/B 主路径
- 可行动性：
  - 趋势详情新增“下一步建议模板”（假设、验证动作、风险）
  - 支持复制结构化建议用于评审会（文本复制即可）
- 行业适配：
  - 强监管行业显示“非合规结论”提示与二次验证建议
  - 术语提供简要解释（tooltips 或方法说明锚点）
- 合规可见性：
  - 删除/纠错入口在前台可直达
  - 每条趋势必须可追溯到至少 1 条公开证据

---

## 4. 信息架构与页面优先级

## 4.1 P0 页面（Phase 1 必须上线）

- `/`
- `/inspirations`
- `/trends`
- `/trend/[trendKey]`
- `/evidence/[signalId]`
- `/categories`
- `/methodology`
- `/legal/privacy`
- `/legal/terms`
- `/legal/data-sources`
- `/legal/removal-request`
- `/admin`
- `/admin/review`

## 4.2 P1 页面

- `/signals/new`
- `/admin/taxonomy`
- `/admin/sources`
- `/admin/compliance`

说明：

- `/signals/new` 在 API 已保留，若进入 P0 必须同步更新门禁分母

---

## 5. 指标与图表可用性（定稿）

每张图必须回答一个问题，且显示：

- 当前值
- 变化率
- 样本量
- 数据更新时间

KPI 词典（必须固化）：

- 活跃用途数
- 新增应用数
- 新兴趋势数
- 衰退趋势数

图表 P0 验收：

- 关键图元可下钻到详情页
- 筛选状态可通过 URL 复现
- 关键图表提供文本摘要或等价数据表
- 首屏关键图表缓存命中 P95 <= 3s
- 图表 tooltip 必须显示样本量与更新时间

---

## 6. 数据与算法架构

## 6.1 数据区（Raw/Clean/Feature/Serve/Label）

- Raw：原始事件
- Clean：标准化事件
- Feature：趋势特征
- Serve：前端/API 只读聚合
- Label：人工反馈与纠错

关键表：

- `raw_events`
- `normalized_events`（含 `signal_id`, `raw_event_id`）
- `evidence_signals`
- `trend_features_daily`
- `trend_scores_periodic`
- `removal_requests`
- `pipeline_runs`

追溯链（必须成立）：

`trend_scores_periodic -> trend_features_daily -> evidence_signals -> normalized_events -> raw_events`

## 6.2 趋势算法

`TrendScore = 0.35*Adoption + 0.25*Persistence + 0.20*CrossSource + 0.10*Burst + 0.10*Novelty`

`Confidence = EvidenceScore * SourceDiversity * LabelStability`

输出必须包含：

- `trend_score`
- `score_components`
- `algo_version`
- `taxonomy_version`

---

## 7. API 契约（定稿）

权威规则：

- 前台公开 API：以 `9.3` 为唯一权威
- 管理与 internal API：以 `17.3` 为唯一权威

公开 API 核心：

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

统一响应：

- `code`, `message`, `data`, `request_id`

分页与限流：

- `cursor`, `limit`
- 429 + `Retry-After`

---

## 8. internal 调度与安全

调度模式：

- 模式 A：私网 runner + 内网 internal API（优先）
- 模式 B：公网保护入口 + OIDC 短期令牌 + 服务鉴权

internal 约束：

- 必须携带 `idempotency_key`
- 相同幂等键在窗口期返回同一 `run_id`
- 可通过 `GET /internal/runs/{run_id}` 查询状态
- 状态枚举：`queued|running|success|failed|cancelled`

---

## 9. 合规定稿

## 9.1 ToS 矩阵

每个数据源必须维护：

- `terms_url`
- `terms_version`
- `allowed_usage`
- `prohibited_usage`
- `attribution_rule`
- `retention_limit_days`
- `commercial_use`
- `last_reviewed_at`

## 9.2 删除/下架闭环

状态机：

`submitted -> reviewing -> approved/rejected -> executed -> notified`

申请人追踪：

- 提交返回 `ticket_id` + token
- 可查询工单状态
- 状态变更触发通知

## 9.3 法域与主体

- 必须在隐私与条款页明确运营主体、联系信息、主适用法与争议处理
- 未填主体信息不得对外发布

---

## 10. 非功能与成本

可用性分层：

- Beta：不承诺外部 SLA（要求可观测与告警）
- Growth：99.0%
- Production：99.5%

预算档位：

- A：$0（超预算自动降级）
- B：$50/月
- C：$200/月

预算闸门：

- 数据源日配额 >= 85% 自动降频
- 任务分钟使用 >= 80% 关闭非核心任务

---

## 11. 验收与发布门禁（定稿）

必须全部满足：

- P0 缺陷 = 0
- 核心 API 契约测试通过率 = 100%
- 核心页面 E2E 通过率 >= 95%
- 核心数据任务日运行成功率 >= 95%
- 用户审核总体通过率 >= 80%
- 任务 B（下钻证据）通过率 >= 90%
- 任务 C（可执行建议）通过率 >= 75%
- 24 人审核中遗留 P0 问题 = 0

数据质量阈值：

- 重复事件占比 > 15% 告警
- 关键字段缺失占比 > 10% 告警

---

## 12. 里程碑（定稿）

### Phase 1（2-3 周）

- GitHub 主链路（采集、清洗、聚合、展示）
- P0 页面上线
- 删除请求最小闭环
- QA 门禁跑通

### Phase 2（2-4 周）

- 接入 HF + 社区源
- `/signals/new` 与后台配置页
- 反馈纠错与回测增强

### Phase 3（持续）

- 区域/行业视角增强
- 学习型趋势模型
- 对外 API 与订阅能力

