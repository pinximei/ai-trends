"""
AI 资讯「Agent」——刻意保持为线性流水线（非多智能体），便于审计与替换。

实现落点（单一事实来源）：
1. 连接器拉取：`routers.admin_extended` / 连接器 `config_json`。
2. 入库前 HTTP 正文批去重：`domain.articles.ingest_fingerprint` + `ingest_duplicate_exists`（`article_ingest`）。
3. 规则门槛：`domain.articles.rule_value_score` 与 `VALUE_SCORE_MIN`（`article_ingest`）。
4. 结构化润色：OpenAI 兼容 `POST {base}/chat/completions`（`llm_service.polish_connector_article`），
   base/model/key 由 `llm_settings_service.resolve_llm_http_config` 解析（后台可配 DeepSeek）。
5. 展示层去重：`domain.articles.display_fingerprint` 对比近期已发布（`article_ingest`）。
6. 持久化：`product_articles.feed_kind`（news/apps）与 `ai_categories_json`（LLM categories）。
7. 列表跨页去重：`application.article_public.list_articles_feed` 指纹 + `exclude_fp` 游标；可选 `category` 与 `GET .../articles/categories` 筛选项对齐。

若后续要扩展，仅增加步骤函数并保持顺序调用即可。
"""
from __future__ import annotations

# 显式步骤常量：供日志、监控或管理端文档引用
STEP_CONNECTOR_FETCH = "connector_fetch"
STEP_INGEST_FINGERPRINT_DEDUPE = "ingest_fingerprint_dedupe"
STEP_RULE_VALUE_GATE = "rule_value_gate"
STEP_LLM_POLISH = "llm_polish_json"
STEP_DISPLAY_FINGERPRINT_DEDUPE = "display_fingerprint_dedupe"
STEP_PERSIST = "persist_article"

PIPELINE_ORDER: tuple[str, ...] = (
    STEP_CONNECTOR_FETCH,
    STEP_INGEST_FINGERPRINT_DEDUPE,
    STEP_RULE_VALUE_GATE,
    STEP_LLM_POLISH,
    STEP_DISPLAY_FINGERPRINT_DEDUPE,
    STEP_PERSIST,
)


def pipeline_steps() -> list[dict[str, str]]:
    labels = {
        STEP_CONNECTOR_FETCH: "连接器拉取原始片段",
        STEP_INGEST_FINGERPRINT_DEDUPE: "同正文指纹去重（防重复入库）",
        STEP_RULE_VALUE_GATE: "规则价值分门槛（低质整批丢弃）",
        STEP_LLM_POLISH: "大模型结构化输出（标题/摘要/Markdown/标签）",
        STEP_DISPLAY_FINGERPRINT_DEDUPE: "标题+摘要展示指纹去重（近期稿）",
        STEP_PERSIST: "写入已发布文章（feed_kind + ai_categories_json）",
    }
    return [{"id": k, "label": labels[k]} for k in PIPELINE_ORDER]
