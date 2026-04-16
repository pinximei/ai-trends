# 任务列表（基于 v2 方案）

来源文档：`docs/agent-trend-platform-prd-tech-spec-v2.md`

## 1. 执行原则

- 按 P0 -> P1 -> P2 递进
- 每项任务必须有负责人、产出物、验收标准
- 开发前先完成 Round 1 预审问题关闭
- 开发完成后必须执行 Round 2 终审

---

## 2. P0 任务（必须）

## 2.1 架构与契约

1. 冻结 API 权威清单
- 产出：`openapi/public-v1.yaml`、`openapi/admin-internal-v1.yaml`
- 验收：与 `v2` 文档路径 100% 一致

2. 页面到 API 映射落表
- 产出：`docs/page-api-mapping.md`
- 验收：P0 页面均有对应 API 与参数说明

3. internal 安全方案定版
- 产出：`docs/internal-security-runbook.md`
- 验收：明确模式 A/B、OIDC、幂等、run 状态接口

## 2.2 数据与算法

4. 建立核心表结构
- 产出：`db/schema-v1.sql`
- 验收：含 `raw_events`、`normalized_events`、`evidence_signals`、`trend_features_daily`、`trend_scores_periodic`、`removal_requests`、`pipeline_runs`

5. 实现追溯链查询
- 产出：`GET /api/v1/evidences/{signal_id}` 可回溯字段
- 验收：可从趋势详情下钻到 raw 证据信息

6. 实现趋势评分最小版本
- 产出：日/周聚合任务 + score_components
- 验收：`/trends` 返回 `trend_score` + 解释字段

## 2.3 前端页面

7. 上线 P0 页面
- 产出：P0 路由全部可访问
- 验收：与 `v2` 文档 P0 清单一致

8. 筛选与 URL 同步
- 产出：全局筛选 query 状态
- 验收：刷新/分享 URL 后视图一致

9. 下钻闭环
- 产出：图表 -> 趋势详情 -> 证据详情
- 验收：关键图元可点击，证据页可返回原上下文

9.1 24人审核要求落地（交互）
- 产出：筛选跨页一致、返回保留上下文、移动端 A/B 任务可完成
- 验收：24人审核中可用性类问题 P0=0

## 2.4 合规与法务

10. 完成 ToS 矩阵配置
- 产出：`docs/tos-matrix-v1.csv` 或数据库配置表
- 验收：每个源 8 个必填字段齐全

11. 删除请求闭环
- 产出：提交、查询、处理、通知全链路
- 验收：工单状态机可跑通，日志可追踪

12. 法域与主体信息落地
- 产出：`/legal/privacy`、`/legal/terms` 实际主体文本
- 验收：无占位文本

12.1 删除/纠错入口前台直达
- 产出：页面导航可进入 `removal-request` 与反馈入口
- 验收：用户 2 步内可找到入口

## 2.5 QA 与发布

13. 契约测试接入 CI
- 产出：`ci-contract-test.yml`
- 验收：核心 API 契约测试 100% 通过

14. 核心 E2E 套件
- 产出：`tests/e2e/core/*`
- 验收：核心页面 E2E >= 95%

15. 数据任务门禁
- 产出：数据任务成功率监控脚本
- 验收：日成功率 >= 95%，异常告警可达

16. 24 人审核整改闭环
- 产出：`docs/review-log-p0-closure.md` 中 24 人反馈条目与修复状态
- 验收：
  - 总通过率 >= 80%
  - 任务 B >= 90%
  - 任务 C >= 75%
  - 遗留 P0 = 0

---

## 3. P1 任务（建议紧随 P0）

1. 接入 Hugging Face / 社区源  
2. 上线 `/signals/new`  
3. 完成 admin taxonomy/sources 页面  
4. 增强回测报告（12 周对比）  
5. 图表可访问性增强（数据表视图、键盘可达）  

---

## 4. P2 任务（增长期）

1. 行业/区域透镜增强  
2. 学习型趋势模型  
3. 订阅告警与导出  
4. B2B API 输出  

---

## 5. 依赖与顺序

先后顺序（必须）：

1. API/数据契约冻结  
2. 数据层与任务链路  
3. 前端 P0 页面  
4. 合规闭环  
5. QA 门禁  
6. Round 2 复审

---

## 6. 完成定义（项目级）

- P0 任务全部完成且验收通过
- Round 2 通过（技术、QA、合规、用户审核）
- 无 P0 缺陷
- 可对外发布 Beta

