# 本地凭据（单文件）

## 配置

```powershell
copy local\credentials.example local\credentials
# 编辑 local\credentials（已 gitignore，勿提交）
```

`local/credentials` 包含：

- **LLM**：`AITRENDS_LLM_API_KEY`（或 `AISOU_LLM_*`）
- **NewsAPI**：`NEWSAPI_KEY`
- **TheNewsAPI**：`THENEWSAPI_API_TOKEN`
- **Product Hunt**：`PRODUCT_HUNT_API_KEY` + `PRODUCT_HUNT_APP_SECRET`，或仅 `PRODUCT_HUNT_ACCESS_TOKEN`

从旧分散文件迁移：

```powershell
py -3.12 scripts/merge_local_credentials.py
```

写入数据库：

```powershell
$env:AITRENDS_DATABASE_URL = "sqlite:///D:/aisoul/backend/data/dev_local.db"
py -3.12 scripts/load_local_credentials.py
```

## 全源验收

```powershell
# 推荐：仅真实 LLM，独立库，避免 mock 阶段干扰
py -3.12 scripts/verify_all_sources_local.py --real-llm-only

# 或 mock + 真实 LLM 连续（真实阶段会先清空各源旧文章）
py -3.12 scripts/verify_all_sources_local.py --real-llm
```

覆盖：GitHub、Product Hunt、Hacker News、NewsAPI、TheNewsAPI、arXiv、Hugging Face Spaces（热度拉取 + 真实 LLM 入库 + 公开 feed）。
