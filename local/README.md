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
