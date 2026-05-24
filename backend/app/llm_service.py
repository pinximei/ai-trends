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
    if k in ("newsapi", "thenewsapi", "finnhub", "youtube_data", "mapbox"):
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
    from .domain.articles import FACET_ALL_LABELS, _LEGACY_CATEGORY_ALIASES

    if len(clean_cats) != 1:
        return f"bad_categories got={clean_cats!r}"
    rc = clean_cats[0]
    if rc not in FACET_ALL_LABELS and rc not in _LEGACY_CATEGORY_ALIASES:
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
        "categories **只能是包含恰好 1 个字符串的数组**，且该字符串必须从下列固定大类中选其一（禁止自造近义词）："
        "模型层(谨慎)、开源客户端(好抄)、应用产品、高可复刻、已验证变现、变现案例、"
        "数据算力、安全合规、政策市场、Agent、多模态、其他。"
        "独立开发者视角优先：高可复刻潜力的客户端/小工具选「开源客户端(好抄)」或「高可复刻」；明确营收/并购线索选「变现案例」或「已验证变现」。"
    )
    commercial_hint = (
        "你是「独立开发者高可复刻产品与商业灵感库」主编。读者要回答三件事：① 可复刻性有多高（产品边界、技术栈、人力）；"
        "② 怎么赚钱（定价、渠道、目标用户）；③ 风险与差异化。"
        "语气务实、可执行，避免空泛「颠覆行业」。"
    )
    if fk == "apps":
        stream_hint = (
            f"{commercial_hint}"
            "当前条目归类为 **应用/产品** 泳道：侧重可运行产品、上架工具与变现灵感。"
            f"{category_rule}"
        )
        structure_hint = (
            "【应用稿结构】tabs **必须恰好 2 个**，label 只能是「描述」「数据支撑」。"
            "「描述」summary≥120 字：产品是什么、解决谁的问题、为何值得抄；body_md≥180 字写复刻切入点（技术栈、MVP 范围）。"
            "「数据支撑」：用中文表格写可核对指标（链接、star、定价、ARR 等）；禁止 ```json。"
        )
    else:
        stream_hint = (
            f"{commercial_hint}"
            "当前条目归类为 **资讯/社区** 泳道：侧重动态、讨论与行业信号，仍须点出对独立开发者的行动启示。"
            f"{category_rule}"
        )
        structure_hint = (
            "【资讯稿结构】tabs 只能是「描述」「数据支撑」。"
            "「描述」summary≥120 字；body_md 分段写事件与启示。"
            "「数据支撑」用表格/列表写关键数字与链接。"
        )
    system = (
        "只根据用户提供的原始 API 片段写稿，禁止编造片段中未出现的名称、数字、URL。"
        "若片段信息不足，用「原文未提供」说明缺口，但仍须把已有字段写全。"
        f"{stream_hint}"
        f"{structure_hint}"
        f"{_source_detail_structure_hint(admin_source_key)}"
        "输出一个 JSON 对象，键必须为：title, summary, body_md, categories, feed_kind, replication_tier, tabs。"
        "replication_tier 只能是 S、A、B、C 之一，表示可复刻性（非「好不好抄」的口语）："
        "S=高可复刻（边界清晰、常见技术栈、1～2 周可演示 MVP、有明确用户与变现路径），"
        "A=较高可复刻（约 1 月内可验证），B=可复刻性中等，C=低可复刻（基础设施/闭源大模型依赖/团队规模化）。"
        "title：单行中文标题，含主体名，避免「同步资源·板块·连接器」类占位风格。"
        "summary：列表卡片与详情页首屏用，信息密度高，不可与 title 重复同一句。"
        "body_md：详情页「总览」区 Markdown，须含二级标题，与 tabs 内容互补（总览讲脉络，tabs 讲展开），勿整段复制 tabs。"
        "categories 为恰好 1 个元素的字符串数组，元素必须是上述规范大类之一；"
        'feed_kind 只能为 "news" 或 "apps"；replication_tier 必须为 S/A/B/C 之一。'
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
        from .domain.articles import normalize_replication_tier

        tier = normalize_replication_tier(data.get("replication_tier"))
        out = {
            "title": title,
            "summary": summary,
            "body_md": body_md or summary,
            "categories": cats,
            "feed_kind": out_fk,
            "replication_tier": tier,
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
