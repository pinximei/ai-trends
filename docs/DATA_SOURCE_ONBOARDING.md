# 数据源逐个接入（本地验证门禁）

产品**默认定时拉取 7 个内置数据源**（含 2 路变现向，无 Key）。

| source_key | 名称 | 默认定时拉取 | 泳道 | 本地 Key |
|------------|------|--------------|------|----------|
| `github` | GitHub（客户端） | ✅ | 应用* | 可选 PAT |
| `product_hunt` | Product Hunt | ✅ | 应用 | `local/product_hunt.credentials` |
| `hacker_news` | Hacker News | ✅ | 资讯 | 无 |
| `newsapi` | NewsAPI | ✅ | 资讯 | `local/newsapi.credentials` |
| `thenewsapi` | TheNewsAPI | ✅ | 资讯 | `local/thenewsapi.credentials` |
| `taaft` | TAAFT（新工具） | ✅ | 应用* | 无 |
| `acquire` | Acquire（AI 资产） | ✅ | 应用* | 无 |

\* 公开 **应用** 列表还纳入：GitHub 客户端 S/A、变现类主类、TAAFT/Acquire 源（与资讯去重）。

```powershell
py -3.12 scripts/verify_all_sources_local.py
```

**NewsAPI 说明：** 免费 Developer 档约 100 次/天；默认 `v2/everything`（`top-headlines`+复杂筛选在免费档常返回 0 条，代码会自动回退 everything）。

---

## 单源验收

```powershell
py -3.12 scripts/verify_source_local.py --source newsapi
py -3.12 scripts/verify_source_local.py --source thenewsapi
```

默认 **mock LLM**；真实润色加 `--real-llm`。

---

## 排错

| 现象 | 原因 |
|------|------|
| NewsAPI packs=0 | 未配 Key；或 URL 仍是旧 top-headlines（重启后会修复为 everything） |
| NewsAPI 429 | 免费档日限额用尽 |
| TheNewsAPI 401 | token 无效 |
