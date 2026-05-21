# 本地临时配置（勿提交密钥）

| 文件 | 说明 |
|------|------|
| `product_hunt.credentials.example` | 模板，可提交 |
| `product_hunt.credentials` | 你的真实 Token，**已 gitignore** |

**Product Hunt 本地全流程：**

```powershell
copy local\product_hunt.credentials.example local\product_hunt.credentials
# 编辑 local\product_hunt.credentials 填入 Key / Secret 或 Access Token

py -3.12 scripts/run_product_hunt_sync_local.py --sqlite
```

验证通过后，在**云端管理后台 → 数据源 → Product Hunt** 填写相同凭据（生产勿依赖本目录文件）。

---

## 数据源逐个验收（必读）

当前内置 **5 路**：GitHub / Product Hunt / Hugging Face Spaces / Hacker News / arXiv（启动后连接器默认启用定时拉取）。  
**再增其它数据源前**，须先让现有源在本地通过门禁：

```powershell
# 配置 LLM（否则不会入库）
$env:AITRENDS_LLM_API_KEY = "sk-..."

py -3.12 scripts/verify_source_local.py --source github
py -3.12 scripts/verify_source_local.py --source product_hunt
py -3.12 scripts/verify_source_local.py --source huggingface_spaces
py -3.12 scripts/verify_source_local.py --source hacker_news
py -3.12 scripts/verify_source_local.py --source arxiv
```

分步脚本：

| 源 | 命令 |
|----|------|
| GitHub | `py -3.12 scripts/run_github_sync_local.py` |
| Product Hunt | `py -3.12 scripts/run_product_hunt_sync_local.py --sqlite` |
| HF Spaces | `py -3.12 scripts/run_huggingface_spaces_sync_local.py --sqlite` |
| Hacker News | `py -3.12 scripts/run_hacker_news_sync_local.py --sqlite` |
| arXiv | `py -3.12 scripts/run_arxiv_sync_local.py --sqlite` |

流程与接入新源的代码清单见 [docs/DATA_SOURCE_ONBOARDING.md](../docs/DATA_SOURCE_ONBOARDING.md)。
