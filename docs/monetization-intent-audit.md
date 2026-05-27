# 变现价值优先 — 意图符合性审核记录

## 产品初衷（验收标准）

| ID | 要求 |
|----|------|
| 1 | 公开应用列表：`worth≥7` + 实质 `monetization_hypothesis` + 产品池门槛；**不要求** phases/工时 |
| 2 | 高价值：`worth≥8` 且 `verdict=高价值` |
| 3 | 应用价值视图按 `worth_score` 降序（无分排后） |
| 4 | GitHub 进应用池：仅 `开源客户端(好抄)` + 价值达标；**不能**仅凭 S/A 档位 |
| 5 | 工时不参与筛选/排序；列表卡片不展示工时 |
| 6 | 无「仅 tier / 仅分类 / 旧稿兼容」绕过价值门槛 |
| 7 | 首页/雷达/摘要与列表同门槛；变现线索须价值≥7 |
| 8 | 邮件摘要应用栏价值优先，非纯热度 |
| 9 | 新稿发布仍要完整 phases；compat 不得用泛化变现文案过关 |
| 10 | Tab 旧名入库前别名替换，非双轨体系 |

## 审核循环

1. **Agent 初审**（2026-05-24）：6 个 blocker（tier 绕过、摘要变现栏、digest 热度池等）
2. **修复 + 自动化测试**：`tests/test_monetization_intent_gates.py` 等
3. **Agent 复审**：**PASS**，无 blocker；3 个 minor（cursor 分页、digest 预取窗口、详情旧 Tab 展示兼容）

## 自动化证明（本地可复现）

```bash
py -3.12 -m pytest tests/test_monetization_intent_gates.py \
  tests/test_replication_analysis.py \
  tests/test_replication_tier_feed_filter.py \
  tests/test_home_highlight_replicable_apps.py \
  tests/test_home_highlight_monetization_apps.py \
  tests/test_polish_publish_compat.py \
  tests/test_connector_ingest_diagnostics.py \
  tests/test_newsletter_digest_format.py \
  tests/test_newsletter_digest_prioritize.py \
  tests/test_article_public_shape.py -q
```

**结果：84 passed**（审核轮次末次运行）

## 关键代码锚点

- 应用泳道强制价值门槛：`article_public._feed_row_matches_list_filters`（`feed == "apps"` 分支）
- 价值筛选逻辑：`replication_analysis.article_value_filter_eligible`
- GitHub 泳道：`article_public._github_counts_as_apps_feed`
- 首页变现线索：`home_public._eligible_monetization_highlight`
- 摘要应用栏：`newsletter_daily_digest` + `article_value_assessed`
- Tab 别名：`articles.TAB_LABEL_ALIASES`

## 已知 minor（不阻挡初衷）

- `paginate_by=cursor` 的 apps 仍按时间序（前台主用 heat/day）
- 摘要先按热度取候选窗口再过滤（池内已按价值排序）
- 详情 Markdown 仍识别旧 Tab 标题（只读兼容，不入库双轨）
