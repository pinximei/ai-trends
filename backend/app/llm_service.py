"""大模型调用：灵感生成、连接器文章润色；未配置 API 时回退模板。"""
from __future__ import annotations

import json
import re

import httpx
from sqlalchemy.orm import Session

from .domain.articles import (
    CONNECTOR_LLM_SNIPPET_MAX_CHARS,
    FACET_ALL_LABELS,
    required_feed_card_tab_labels,
    validate_llm_polish_for_publish,
)
from .llm_settings_service import resolve_llm_http_config
from .product_models import LlmUsageLog


def _log_usage(
    db: Session,
    scenario: str,
    model: str,
    input_tok: int,
    output_tok: int,
    success: bool,
    ref_type: str,
    ref_id: str,
    admin_user_id: int | None = None,
    err: str | None = None,
):
    db.add(
        LlmUsageLog(
            scenario=scenario,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            admin_user_id=admin_user_id,
            ref_type=ref_type,
            ref_id=ref_id,
            success=success,
            error_code=err,
        )
    )
    db.commit()


def chat_completion(
    db: Session,
    *,
    system: str,
    user: str,
    scenario: str,
    ref_type: str,
    ref_id: str,
    admin_user_id: int | None = None,
    response_json: bool = False,
    max_tokens: int | None = None,
) -> tuple[str, int, int]:
    """OpenAI 兼容 Chat Completions；仅使用库内「AI 资讯」LLM 配置（product_settings_kv.llm）。"""
    base, key, model = resolve_llm_http_config(db)
    if not key:
        raise RuntimeError(
            "LLM 未配置：请在管理端「AI 资讯配置」保存 API Key；或保留 backend/.env 中的 AITRENDS_LLM_API_KEY，启动时若库为空会自动迁入。"
        )

    url = base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.4,
    }
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = max_tokens
    if response_json:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=120.0) as client:
        r = client.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    it = int(usage.get("prompt_tokens") or 0)
    ot = int(usage.get("completion_tokens") or 0)
    _log_usage(db, scenario, model, it, ot, True, ref_type, ref_id, admin_user_id)
    return text, it, ot


def _extract_json_object(raw: str) -> dict | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


def _source_detail_structure_hint(admin_source_key: str) -> str:
    """按连接器数据源约束详情 tab 写法，便于前台分版式展示。"""
    k = (admin_source_key or "").strip().lower()
    if k == "github":
        return (
            "【GitHub 仓库稿】「描述」按：项目定位 → 核心能力 → 适用人群；"
            "「数据支撑」用中文表格，优先列：仓库名、Star 总数、今日 Star、主语言、许可证；"
            "凡片段含 html_url、homepage、full_name，必须在表内或文末用 Markdown 链接写出，例如 [GitHub 仓库](https://github.com/owner/repo)。"
        )
    if k == "product_hunt":
        return (
            "【Product Hunt 上架稿】「描述」按：产品是什么 → 解决什么问题 → 目标用户；"
            "「数据支撑」表格列：产品名、投票/热度、话题标签、官网、发布日期等可核对字段。"
        )
    if k == "huggingface_spaces":
        return (
            "【Hugging Face Space 稿】「描述」按：Space 用途 → 交互方式 → 典型场景；"
            "「数据支撑」列：Space 名、作者/组织、trendingScore、点赞、运行环境、外链等。"
        )
    if k == "hacker_news":
        return (
            "【Hacker News 社区帖】「描述」按：帖子主题 → 讨论背景 → 对 AI/技术读者的意义；"
            "「数据支撑」表格列：标题、票数 points、评论数、作者、讨论链接（url 或 item?id=objectID）。"
        )
    if k == "arxiv":
        return (
            "【arXiv 论文稿】「描述」按：研究问题 → 方法/贡献 → 对 AI 从业者的意义；"
            "「数据支撑」表格列：论文标题、arXiv ID、作者、发表/更新日期、abs 链接、PDF 链接、学科分类。"
        )
    if k in ("newsapi", "finnhub", "youtube_data", "mapbox"):
        return (
            "【资讯/API 快讯稿】「描述」按：谁 → 发生了什么 → 影响/结论；"
            "「数据支撑」表格列：报道主体、时间、来源、关键数字、原文链接。"
        )
    if k in ("openai", "google_gemini", "mcp_skills"):
        return (
            "【平台/API 动态稿】「描述」按：能力更新 → 对谁有用 → 使用注意；"
            "「数据支撑」列：产品/接口名、版本、配额或定价线索、文档链接。"
        )
    return ""


def _describe_polish_reject(data: dict) -> str:
    """润色结果未通过发布校验时的可读原因（供同步诊断）。"""
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    body_md = str(data.get("body_md") or "").strip()
    if not title or not summary:
        return f"title_or_summary_empty title={bool(title)} summary_len={len(summary)}"
    if len(summary) < 36:
        return f"summary_too_short len={len(summary)} need>=36"
    cats = data.get("categories")
    clean_cats = [str(x).strip() for x in cats if str(x).strip()] if isinstance(cats, list) else []
    if len(clean_cats) != 1 or clean_cats[0] not in FACET_ALL_LABELS:
        return f"bad_categories got={clean_cats!r}"
    fk = str(data.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    need_desc, need_hi = required_feed_card_tab_labels(fk)
    tabs = data.get("tabs")
    if not isinstance(tabs, list) or len(tabs) != 2:
        return f"tabs_count={len(tabs) if isinstance(tabs, list) else 'not_list'} need=2"
    labels: list[str] = []
    for t in tabs:
        if not isinstance(t, dict):
            return "tab_not_object"
        lab = str(t.get("label") or "").strip()
        summ = str(t.get("summary") or "").strip()
        body = str(t.get("body_md") or "").strip()
        labels.append(lab)
        min_summ = 72 if lab == need_desc else 12
        min_body = 120 if lab == need_desc else 60
        if len(summ) < min_summ:
            return f"tab_{lab}_summary_short len={len(summ)} need>={min_summ}"
        if len(body) < min_body:
            return f"tab_{lab}_body_short len={len(body)} need>={min_body}"
    legacy_ok = labels == [need_desc, "功能亮点"] if fk == "apps" else labels == [need_desc, "要点"]
    if labels != [need_desc, need_hi] and not legacy_ok:
        return f"tab_labels={labels!r} need={[need_desc, need_hi]!r}"
    tab_body_total = sum(len(str(t.get("body_md") or "")) for t in tabs if isinstance(t, dict))
    if tab_body_total < 280:
        return f"tab_body_total_short len={tab_body_total} need>=280"
    if len(body_md) < 120 and tab_body_total < 500:
        return f"body_md_short body={len(body_md)} tabs_total={tab_body_total}"
    return "validate_unknown"


def polish_connector_article(
    db: Session,
    *,
    snippet: str,
    connector_name: str,
    admin_source_key: str,
    segment_label: str,
    rule_title: str,
    rule_summary: str,
    value_score: float,
    ref_id: str,
    feed_kind: str = "news",
) -> tuple[dict | None, str]:
    """
    仅在高价值已确认后调用：必须用模型重写全文并分类；输出含多 tab（概要 + 详情 Markdown）。
    feed_kind 为 news（资讯）或 apps（应用），决定文风与 categories 侧重。
    返回 (结果, 失败原因)；成功时原因为空串。未配置 Key / 校验失败时结果为 None。
    """
    _base, _key, _model = resolve_llm_http_config(db)
    if not (_key or "").strip():
        return None, "no_llm_key"
    fk = (feed_kind or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    # 指纹与解析在 article_ingest 使用完整片段；模型侧仅取前段以控制 token。
    snippet_cut = (snippet or "")[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]
    category_rule = (
        "categories **只能是包含恰好 1 个字符串的数组**，且该字符串必须从下列 **11** 个固定大类中选其一（禁止自造近义词）："
        "大模型、开源工具、应用产品、数据算力、安全合规、政策市场、论文研究、平台API、Agent、多模态、其他。"
        "选最能概括本条的那一个；不要输出多条。"
    )
    if fk == "apps":
        stream_hint = (
            "当前条目归类为 **AI 应用** 泳道：面向可运行产品、工具发布与能力更新；语气偏产品速递，让读者一眼知道「这是什么、能干什么」。"
            f"{category_rule}"
        )
        structure_hint = (
            "【应用稿结构】列表卡片只展示「描述」与「数据支撑」两段。"
            "tabs **必须恰好 2 个**，label 按顺序只能是「描述」「数据支撑」（禁止其它 tab 名）。"
            "「描述」：summary 写 5～7 句完整叙述（不少于 120 汉字）；body_md 写清背景与定位（不少于 180 汉字），"
            "段落之间用空行分隔，禁止粘贴 ```json 代码块或英文字段名堆砌。"
            "「数据支撑」：summary 宜短（1～2 句）；body_md 用 **中文表头** 的 Markdown 表格呈现可核对事实，"
            "表头建议为 | 指标 | 数值/事实 | 说明 |，行内写 star 数、版本、链接、发布时间等（字段名可译成中文列名）；"
            "若无表格数据则用 4～6 条中文列表。禁止输出英文 JSON 代码块。"
            "列表卡片以「描述」tab 的 summary 为主；「数据支撑」tab 的 summary 供卡片短摘要。"
        )
    else:
        stream_hint = (
            "当前条目归类为 **AI 资讯** 泳道：面向行业动态、论文、社区与技术新闻；语气偏信息报道，让读者一眼知道「发生了什么事」。"
            f"{category_rule}"
        )
        structure_hint = (
            "【资讯稿结构】列表卡片只展示「描述」与「数据支撑」两段。"
            "tabs **必须恰好 2 个**，label 按顺序只能是「描述」「数据支撑」。"
            "「描述」：5～7 句讲清主体、事件与结论（summary 不少于 120 汉字）；body_md 分段叙述（空行分段），禁止 ```json。"
            "「数据支撑」：summary 宜短；body_md 用中文表头 Markdown 表格或列表写关键数字、来源、时间线，禁止英文 JSON 块。"
            "body_md 总览区不少于 400 汉字，与 tabs 互补勿整段复制。"
        )
    system = (
        "你是 AI 行业「趋势雷达」资深编辑。只根据用户提供的原始 API 片段写稿，禁止编造片段中未出现的名称、数字、URL。"
        "若片段信息不足，用「原文未提供」说明缺口，但仍须把已有字段写全。"
        f"{stream_hint}"
        f"{structure_hint}"
        f"{_source_detail_structure_hint(admin_source_key)}"
        "输出一个 JSON 对象，键必须为：title, summary, body_md, categories, feed_kind, tabs。"
        "title：单行中文标题，含主体名，避免「同步资源·板块·连接器」类占位风格。"
        "summary：列表卡片与详情页首屏用，信息密度高，不可与 title 重复同一句。"
        "body_md：详情页「总览」区 Markdown，须含二级标题，与 tabs 内容互补（总览讲脉络，tabs 讲展开），勿整段复制 tabs。"
        "categories 为恰好 1 个元素的字符串数组，元素必须是上述 11 字面值之一；"
        'feed_kind 只能为 "news" 或 "apps"。'
        "tabs：恰好 2 个；label 见上文结构要求；每项含 summary、body_md（Markdown）。"
        "若片段为 JSON/数组，须翻译成中文叙述或表格/列表，保留 repo 名、版本号、star、链接等可核对信息；"
        "禁止在 body_md 或 tabs 中输出 ```json 代码块或整段原始 API 响应。"
        "禁止输出空洞 tab（仅重复 summary、无新信息）。"
    )
    user = (
        f"数据源规则推断的参考泳道 feed_hint={fk}（news=资讯 / apps=应用）。请阅读片段后在输出中给出 feed_kind，"
        f"仅允许 news 或 apps；允许与 feed_hint 不一致，但 title、summary、categories 必须与 feed_kind 自洽。\n"
        f"数据源: {admin_source_key} / 连接器: {connector_name} / 板块: {segment_label}\n"
        f"规则价值分(0-100): {value_score:.0f}\n"
        f"占位标题: {rule_title}\n"
        f"占位摘要: {rule_summary}\n\n"
        f"原始片段:\n```\n{snippet_cut}\n```"
    )
    model = _model or "deepseek-chat"
    try:
        try:
            raw, _, _ = chat_completion(
                db,
                system=system,
                user=user,
                scenario="article_ingest_polish",
                ref_type="connector_article",
                ref_id=ref_id[:64],
                response_json=True,
                max_tokens=8192,
            )
        except Exception as e1:
            try:
                raw, _, _ = chat_completion(
                    db,
                    system=system + " 请只输出一个 JSON 对象，不要其它文字。",
                    user=user,
                    scenario="article_ingest_polish",
                    ref_type="connector_article",
                    ref_id=ref_id[:64],
                    response_json=False,
                    max_tokens=8192,
                )
            except Exception as e2:
                err = f"{type(e2).__name__}: {str(e2)[:240]}"
                _log_usage(
                    db,
                    "article_ingest_polish",
                    model,
                    0,
                    0,
                    False,
                    "connector_article",
                    ref_id[:64],
                    err=err,
                )
                return None, f"llm_http_failed retry_after_json_mode failed={type(e1).__name__}; {err}"
        data = _extract_json_object(raw)
        if not data:
            preview = (raw or "").strip().replace("\n", " ")[:120]
            return None, f"json_parse_failed raw_preview={preview!r}"
        title = str(data.get("title") or "").strip()
        summary = str(data.get("summary") or "").strip()
        body_md = str(data.get("body_md") or "").strip()
        cats = data.get("categories")
        if not title or not summary:
            return None, f"empty_title_or_summary title={bool(title)} summary_len={len(summary)}"
        if not isinstance(cats, list):
            cats = []
        else:
            cats = [str(x).strip() for x in cats if str(x).strip()]
        fk_ai = str(data.get("feed_kind") or "").strip().lower()
        out_fk = fk if fk_ai not in ("news", "apps") else fk_ai
        raw_tabs = data.get("tabs")
        norm_tabs: list[dict[str, str]] = []
        if isinstance(raw_tabs, list):
            for t in raw_tabs[:6]:
                if not isinstance(t, dict):
                    continue
                lab = str(t.get("label") or "").strip()
                sm = str(t.get("summary") or "").strip()
                bd = str(t.get("body_md") or "").strip()
                if lab and sm and bd:
                    norm_tabs.append({"label": lab, "summary": sm, "body_md": bd})
        if len(norm_tabs) < 2:
            return None, f"tabs_incomplete parsed={len(norm_tabs)} raw_tabs={len(raw_tabs) if isinstance(raw_tabs, list) else 0}"
        out = {
            "title": title,
            "summary": summary,
            "body_md": body_md or summary,
            "categories": cats,
            "feed_kind": out_fk,
            "tabs": norm_tabs,
        }
        if not validate_llm_polish_for_publish(out):
            return None, _describe_polish_reject(out)
        return out, ""
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:240]}"
        try:
            _log_usage(
                db,
                "article_ingest_polish",
                model,
                0,
                0,
                False,
                "connector_article",
                ref_id[:64],
                err=err,
            )
        except Exception:
            pass
        return None, f"unexpected: {err}"


def generate_inspiration_body(
    db: Session,
    *,
    context_md: str,
    username: str,
    inspiration_id: int,
    version_no: int,
    admin_user_id: int | None = None,
) -> str:
    """生成灵感正文；无 API Key 时返回结构化占位。"""
    if not resolve_llm_http_config(db)[1]:
        return (
            f"## 灵感草稿（未配置 LLM，规则回退）\n\n"
            f"操作者：{username}\n\n### 上下文摘要\n\n{context_md[:4000]}\n"
        )
    system = "你是产业分析助手，根据给定数据摘要输出简洁的灵感要点（Markdown），不要编造未提供的数据。"
    user = f"请基于以下上下文输出 3～5 条可验证的灵感方向：\n\n{context_md}"
    text, _, _ = chat_completion(
        db,
        system=system,
        user=user,
        scenario="inspiration_generate",
        ref_type="inspiration",
        ref_id=f"{inspiration_id}:{version_no}",
        admin_user_id=admin_user_id,
    )
    return text
