# 数据源逐个接入（本地验证门禁）

产品当前**内置 5 个数据源**，其它历史预置已标记为 discontinued，不会自动写入库。

| source_key | 名称 | 默认定时拉取 | 泳道 | 本地脚本 |
|------------|------|--------------|------|----------|
| `github` | GitHub Trending | ✅ 定时拉取 | 资讯 `news` | `scripts/run_github_sync_local.py` |
| `product_hunt` | Product Hunt | ✅ 定时拉取 | 应用 `apps` | `scripts/run_product_hunt_sync_local.py` |
| `huggingface_spaces` | Hugging Face Spaces | ✅ 定时拉取 | 应用 `apps` | `scripts/run_huggingface_spaces_sync_local.py` |
| `hacker_news` | Hacker News | ✅ 定时拉取 | 资讯 `news` | `scripts/run_hacker_news_sync_local.py` |
| `arxiv` | arXiv | ✅ 定时拉取 | 资讯 `news` | `scripts/run_arxiv_sync_local.py` |

**原则：一次只接一个源；本地门禁通过后再接下一个；未通过不得加入 `MAINSTREAM_ADMIN_SOURCE_PRESETS` 或 `AUTO_ENABLE_PULL_SOURCE_KEYS`。**

---

## 一、环境准备（每个源验证前）

1. Python 3.12+，仓库根目录执行。
2. 本地库（推荐 SQLite）：

   ```powershell
   # 使用 backend/data/dev_local.db（若存在则自动）
   $env:AITRENDS_DATABASE_URL = "sqlite:///D:/aisoul/backend/data/dev_local.db"
   ```

3. **LLM Key（必配，否则不会入库）**  
   管理端配置 DeepSeek，或环境变量：

   ```powershell
   $env:AITRENDS_LLM_API_KEY = "sk-..."
   ```

4. 启动前台（可选，用于肉眼验收详情/列表）：

   ```powershell
   cd frontend; npm run dev
   ```

---

## 二、单源本地门禁（推荐）

对**某一个** `source_key` 跑统一验收（拉取 → 入库 → 公开 API）：

```powershell
py -3.12 scripts/verify_source_local.py --source github
py -3.12 scripts/verify_source_local.py --source product_hunt
py -3.12 scripts/verify_source_local.py --source huggingface_spaces
py -3.12 scripts/verify_source_local.py --source hacker_news
py -3.12 scripts/verify_source_local.py --source arxiv
```

通过标准（脚本 exit 0）：

- 连接器同步无 `error`，且 `articles_created >= 1`（或文章总数增加）
- 最新文章：`tabs` 含「描述」+「数据支撑」（或兼容旧 label）
- 公开 `feed` 能查到该文，且泳道与源一致
- Product Hunt / HF：最新文尽量有 `cover_image_url`（无图不失败，仅 WARN）

也可先跑各源专用脚本做分步排查（见上表）。

---

## 三、人工 UI 验收（门禁通过后）

在本地站逐条确认：

1. **列表** `/news` 或 `/apps`：卡片有描述、数据支撑摘要；PH/HF 有封面或渐变回退。
2. **详情** `/resources/{id}`：版式符合数据源 profile；无大段英文 JSON；表格可读。
3. **后台** 连接器日志：`rows_ingested` / 新建文章数合理，无持续 `skip_llm`。

三项 OK 后，该源记为 **已验收**，才可讨论接入下一个源。

---

## 四、新增第 6 个源时的代码清单（勿跳步）

1. **拉取**：`backend/app/connector_heat_fetch.py` 实现 `sync_<source>_...`。
2. **路由**：`data_api_service.py`、`admin_extended.py` 按 `admin_source_key` 分支调用。
3. **泳道**：`domain/articles.py` 中 `FEED_NEWS_KEYS` / `FEED_APPS_KEYS`（如需）。
4. **详情版式**：`article_detail_profile` + 前端 `articleDetailLayout.ts`。
5. **封面（若有图）**：`extract_cover_image_url` + `cover_image_url` 列。
6. **LLM 提示**：`llm_service._source_detail_structure_hint`。
7. **预置**：仅当本地门禁 + UI 通过后，才在 `services.MAINSTREAM_ADMIN_SOURCE_PRESETS` 增加一行。
8. **定时拉取**：确认稳定后再加入 `AUTO_ENABLE_PULL_SOURCE_KEYS`（避免多源同时暴量）。
9. **脚本**：`scripts/run_<source>_sync_local.py` + `verify_source_local.py` 注册该 key。
10. **文档**：更新本文「当前 N 个源」表格，并写明验收日期。

---

## 五、当前禁止事项

- 不要一次性从 `DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES` 恢复多个历史源。
- 不要在未跑 `verify_source_local.py` 的情况下改生产 `AUTO_ENABLE_PULL_SOURCE_KEYS`。
- 不要把 `local/*.credentials`、样例 JSON、测试 sqlite 提交进 git。

---

## 六、快速排错

| 现象 | 常见原因 |
|------|----------|
| `articles_created = 0` | 未配 LLM Key；或 `rule_value_score` 过低；或重复指纹/上游 id |
| `skip_llm` | Key 无效、超时、或模型输出未通过 `validate_llm_polish_for_publish` |
| GitHub 无文 | `api_base` 仍为 `/zen` 或过短；跑 `run_github_sync_local.py` 会修复 Trending URL |
| PH 无文 | 凭据未写入 `local/product_hunt.credentials` 或未同步到连接器 `config_json` |
| HF 无文 | 连接器未 **启用**；或 LLM 把稿判为 `news` 且被泳道规则筛掉 |

验收记录（运营填写）：

| source_key | 本地门禁日期 | 验收人 | 备注 |
|------------|--------------|--------|------|
| github | | | |
| product_hunt | | | |
| huggingface_spaces | | | |
| hacker_news | | | |
| arxiv | | | |
