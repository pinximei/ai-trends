# 本地临时配置（勿提交密钥）

| 文件 | 说明 |
|------|------|
| `product_hunt.credentials.example` | 模板，可提交 |
| `product_hunt.credentials` | 你的真实 Token，**已 gitignore** |
| `newsapi.credentials.example` | NewsAPI 模板 |
| `newsapi.credentials` | `NEWSAPI_KEY`，**已 gitignore** |
| `thenewsapi.credentials.example` | TheNewsAPI 模板 |
| `thenewsapi.credentials` | `THENEWSAPI_API_TOKEN`，**已 gitignore** |

**Product Hunt 本地全流程：**

```powershell
copy local\product_hunt.credentials.example local\product_hunt.credentials
# 编辑 local\product_hunt.credentials

py -3.12 scripts/run_product_hunt_sync_local.py --sqlite
```

---

## 数据源逐个验收（必读）

当前内置 **5 路**：GitHub / Product Hunt / Hacker News / NewsAPI / TheNewsAPI。

```powershell
$env:AITRENDS_LLM_API_KEY = "sk-..."

py -3.12 scripts/verify_all_sources_local.py
# 或单源：
py -3.12 scripts/verify_source_local.py --source github
py -3.12 scripts/verify_source_local.py --source product_hunt
py -3.12 scripts/verify_source_local.py --source hacker_news
py -3.12 scripts/verify_source_local.py --source newsapi
py -3.12 scripts/verify_source_local.py --source thenewsapi
```

```powershell
copy local\newsapi.credentials.example local\newsapi.credentials
copy local\thenewsapi.credentials.example local\thenewsapi.credentials
# 分别填写 NEWSAPI_KEY、THENEWSAPI_API_TOKEN
```

分步脚本：

| 源 | 命令 |
|----|------|
| GitHub | `py -3.12 scripts/run_github_sync_local.py` |
| Product Hunt | `py -3.12 scripts/run_product_hunt_sync_local.py --sqlite` |
| Hacker News | `py -3.12 scripts/run_hacker_news_sync_local.py --sqlite` |

流程见 [docs/DATA_SOURCE_ONBOARDING.md](../docs/DATA_SOURCE_ONBOARDING.md)。
