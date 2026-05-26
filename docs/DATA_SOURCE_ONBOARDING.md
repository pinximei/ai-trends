# 数据源逐个接入（本地验证门禁）

产品**默认定时拉取 6 个内置数据源**（5 路主流 + Acquire 变现向）。

| source_key | 名称 | 默认定时拉取 | 泳道 | 本地 Key |
|------------|------|--------------|------|----------|
| `github` | GitHub（客户端） | ✅ | 应用* | 可选 PAT |
| `product_hunt` | Product Hunt | ✅ | 应用 | `local/product_hunt.credentials` |
| `hacker_news` | Hacker News | ✅ | 资讯 | 无 |
| `newsapi` | NewsAPI | ✅ | 资讯 | `local/newsapi.credentials` |
| `thenewsapi` | TheNewsAPI | ✅ | 资讯 | `local/thenewsapi.credentials` |
| `acquire` | Acquire（AI 资产） | ✅ | 应用* | 无 |

\* 公开 **应用** 列表还纳入：GitHub 客户端 S/A 或「开源客户端(好抄)」、Acquire 变现源（与资讯去重）。

**已下架（启动时自动删库配置与连接器）**：`taaft`（Cloudflare 403）、`arxiv`、`huggingface_spaces` 等，见 `DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES`。

```powershell
py -3.12 scripts/verify_all_sources_local.py
```

**NewsAPI 说明：** 免费 Developer 档约 100 次/天；默认 `top-headlines`；若条数偏少请检查 Key 与配额。

---

## 单源验收

```powershell
py -3.12 scripts/verify_source_local.py --source github
py -3.12 scripts/verify_source_local.py --source newsapi
```

默认 **mock LLM**；真实润色加 `--real-llm`。

---

## 排错

| 现象 | 原因 |
|------|------|
| NewsAPI packs=0 | 未配 Key；或配额用尽 |
| GitHub packs=0 | Trending 解析失败或未配 `GITHUB_TOKEN`（建议配置 PAT 提高 API 限额） |
| 后台仍看到 TAAFT 卡片 | 需重启后端执行 `prune_discontinued_bootstrap_admin_sources` |
