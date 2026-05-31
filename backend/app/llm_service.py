"""大模型调用：连接器文章润色等场景；未配置 API 时回退模板。"""
from __future__ import annotations

import json
import re

import httpx
from sqlalchemy.orm import Session

from .domain.articles import (
    CONNECTOR_LLM_SNIPPET_MAX_CHARS,
    FACET_ALL_LABELS,
    canonical_feed_card_tab_label,
    publish_polish_length_thresholds,
    required_feed_card_tab_labels,
    validate_llm_polish_for_publish,
)
from .polish_publish_compat import coerce_polish_output, ensure_publishable_polish
from .domain.replication_analysis import FEED_CARD_TAB_REPLICATION, normalize_replication_analysis
from .llm_settings_service import resolve_llm_http_config
from .llm_snippet_compact import compact_snippet_for_llm
from .product_models import LlmUsageLog

# 连接器润色：输出上限（4096 易截断长 JSON tabs，恢复 8192）
POLISH_MAX_OUTPUT_TOKENS = 8192
# 修复重试时仍送足量片段（曾压到 3500 导致字数校验反复失败）
POLISH_REPAIR_SNIPPET_MAX = 16_384


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
            error_code=(err or "")[:64] or None,
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
            "【资讯/API 快讯稿】原文 description 可能很短，须结合 title、url、source_name 扩写，禁止只复述一句。"
            "「描述」tab：summary 至少 80 汉字、body_md 至少 150 汉字（分 2～3 段）。"
            "「数据支撑」tab：用 Markdown 表格列：标题、来源、发布时间、原文链接(url)、摘要要点；"
            "categories 必须从系统给定大类中选 1 个（资讯类常用「政策市场」「应用产品」「模型层(谨慎)」「其他」）。"
        )
    if k in ("openai", "google_gemini", "mcp_skills"):
        return (
            "【平台/API 动态稿】「描述」按：能力更新 → 对谁有用 → 使用注意；"
            "「数据支撑」列：产品/接口名、版本、配额或定价线索、文档链接。"
        )
    return ""


def _build_polish_system(*, fk: str, admin_source_key: str, th_gate: dict[str, int]) -> str:
    """短 system：规则一次说明，避免每条重复超长模板。"""
    category_rule = (
        "categories 为恰好 1 个元素的数组，元素须为固定大类之一："
        "模型层(谨慎)、开源客户端(好抄)、应用产品、高价值复刻、已验证变现、变现案例、"
        "数据算力、安全合规、政策市场、Agent、多模态、其他。"
    )
    commercial = (
        "独立开发者变现向：写清谁付钱、定价/营收线索；star 多≠值得做；禁止 API 字段名与 ```json。"
    )
    src_hint = _source_detail_structure_hint(admin_source_key)
    if fk == "apps":
        tabs = (
            f"tabs 恰好 3 个：描述、变现评估、数据支撑。"
            f"描述 summary≥{th_gate['desc_summary']} body≥{th_gate['desc_body']}；"
            f"变现评估 summary≥{th_gate['repl_summary']} body≥{th_gate['repl_body']}（含变现+工时表）；"
            f"数据支撑 summary≥{th_gate['hi_summary']} body≥{th_gate['hi_body']}。"
            "另输出 replication_analysis：verdict、worth_score(1-10)、difficulty、phases≥3、"
            "estimated_hours、market_position.monetization_hypothesis、risks≥1、platform_fit 等，与 tabs 一致。"
        )
    else:
        tabs = (
            f"tabs 恰好 2 个：描述、数据支撑。"
            f"描述 summary≥{th_gate['desc_summary']} body≥{th_gate['desc_body']}；"
            f"数据支撑 summary≥{th_gate['hi_summary']} body≥{th_gate['hi_body']}。"
        )
    return (
        "只根据用户提供的压缩片段写稿，禁止编造片段外事实；不足处写「原文未提供」。"
        "全文必须使用简体中文：title、summary、body_md、各 tab 的 summary 与 body_md 均用中文撰写；"
        "专有名词/产品名/仓库名可保留英文，但说明句须为中文。"
        f"{commercial} {category_rule} "
        f"输出单个 JSON：title, summary, body_md, categories, feed_kind, replication_tier(S/A/B/C), tabs"
        + ("；apps 另含 replication_analysis。" if fk == "apps" else "")
        + f"。{tabs} "
        f"{src_hint}"
        "feed_kind 仅 news 或 apps；title/summary 信息密度高、勿重复。"
    )


def _build_polish_user(
    *,
    snippet_cut: str,
    admin_source_key: str,
    connector_name: str,
    segment_label: str,
    rule_title: str,
    rule_summary: str,
    value_score: float,
    fk: str,
    repair_note: str = "",
) -> str:
    base = (
        f"feed_hint={fk}（news=资讯/apps=应用，输出 feed_kind 须自洽）。\n"
        f"数据源: {admin_source_key} / 连接器: {connector_name} / 板块: {segment_label}\n"
        f"规则价值分(0-100): {value_score:.0f}\n"
        f"占位标题: {rule_title}\n"
        f"占位摘要: {rule_summary}\n\n"
        f"压缩原文（仅此一份，勿要求更多上下文）:\n```\n{snippet_cut}\n```"
    )
    if repair_note:
        return f"{base}\n\n{repair_note}"
    return base


def _polish_llm_call(
    db: Session,
    *,
    system: str,
    user: str,
    ref_id: str,
    response_json: bool,
    max_tokens: int = POLISH_MAX_OUTPUT_TOKENS,
) -> str:
    raw, _, _ = chat_completion(
        db,
        system=system,
        user=user,
        scenario="article_ingest_polish",
        ref_type="connector_article",
        ref_id=ref_id[:64],
        response_json=response_json,
        max_tokens=max_tokens,
    )
    return raw


def _parse_polish_response(raw: str, *, default_feed_kind: str) -> tuple[dict | None, str]:
    """从模型原文解析润色 JSON；失败时返回 (None, 原因)。"""
    data = _extract_json_object(raw)
    if not data:
        preview = (raw or "").strip().replace("\n", " ")[:120]
        return None, f"json_parse_failed raw_preview={preview!r}"
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    body_md = str(data.get("body_md") or "").strip()
    if not title or not summary:
        return None, f"empty_title_or_summary title={bool(title)} summary_len={len(summary)}"
    cats = data.get("categories")
    if not isinstance(cats, list):
        cats = []
    else:
        cats = [str(x).strip() for x in cats if str(x).strip()]
    fk_ai = str(data.get("feed_kind") or "").strip().lower()
    fk = default_feed_kind if fk_ai not in ("news", "apps") else fk_ai
    raw_tabs = data.get("tabs")
    norm_tabs: list[dict[str, str]] = []
    if isinstance(raw_tabs, list):
        for t in raw_tabs[:6]:
            if not isinstance(t, dict):
                continue
            lab = canonical_feed_card_tab_label(str(t.get("label") or ""))
            sm = str(t.get("summary") or "").strip()
            bd = str(t.get("body_md") or "").strip()
            if lab and (sm or bd):
                norm_tabs.append({"label": lab, "summary": sm, "body_md": bd})
    need_n = len(required_feed_card_tab_labels(fk))
    if len(norm_tabs) == 0 and not body_md:
        n_raw = len(raw_tabs) if isinstance(raw_tabs, list) else 0
        return None, f"tabs_incomplete parsed=0 need={need_n} raw_tabs={n_raw}"
    from .domain.articles import normalize_replication_tier

    tier = normalize_replication_tier(data.get("replication_tier"))
    repl_analysis = normalize_replication_analysis(data.get("replication_analysis"))
    out = {
        "title": title,
        "summary": summary,
        "body_md": body_md or summary,
        "categories": cats,
        "feed_kind": fk,
        "replication_tier": tier,
        "tabs": norm_tabs,
    }
    if repl_analysis:
        out["replication_analysis"] = repl_analysis
    return coerce_polish_output(out), ""


def _describe_polish_reject(data: dict, *, admin_source_key: str | None = None) -> str:
    """润色结果未通过发布校验时的可读原因（供同步诊断）。"""
    th = publish_polish_length_thresholds(admin_source_key)
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
    need_labels = required_feed_card_tab_labels(fk)
    tabs = data.get("tabs")
    need_n = len(need_labels)
    if not isinstance(tabs, list) or len(tabs) != need_n:
        return f"tabs_count={len(tabs) if isinstance(tabs, list) else 'not_list'} need={need_n}"
    labels: list[str] = []
    for t in tabs:
        if not isinstance(t, dict):
            return "tab_not_object"
        lab = str(t.get("label") or "").strip()
        summ = str(t.get("summary") or "").strip()
        body = str(t.get("body_md") or "").strip()
        labels.append(lab)
        if lab == need_labels[0]:
            min_summ, min_body = th["desc_summary"], th["desc_body"]
        elif lab == FEED_CARD_TAB_REPLICATION:
            min_summ, min_body = th.get("repl_summary", 64), th.get("repl_body", 180)
        else:
            min_summ, min_body = th["hi_summary"], th["hi_body"]
        if len(summ) < min_summ:
            return f"tab_{lab}_summary_short len={len(summ)} need>={min_summ}"
        if len(body) < min_body:
            return f"tab_{lab}_body_short len={len(body)} need>={min_body}"
        from .text_display import polish_content_has_connector_api_leak

        if polish_content_has_connector_api_leak(summ) or polish_content_has_connector_api_leak(body):
            return f"tab_{lab}_api_json_leak"
    if labels != list(need_labels):
        return f"tab_labels={labels!r} need={list(need_labels)!r}"
    if fk == "apps" and len(need_labels) == 3:
        from .domain.replication_analysis import (
            describe_replication_analysis_reject,
            normalize_replication_analysis,
            validate_replication_analysis_for_publish,
        )

        norm_ra = normalize_replication_analysis(data.get("replication_analysis"))
        if not validate_replication_analysis_for_publish(norm_ra):
            detail = describe_replication_analysis_reject(norm_ra)
            return f"replication_analysis_invalid:{detail}"
    tab_body_total = sum(len(str(t.get("body_md") or "")) for t in tabs if isinstance(t, dict))
    if tab_body_total < th["tab_body_total"]:
        return f"tab_body_total_short len={tab_body_total} need>={th['tab_body_total']}"
    if len(body_md) < th["body_md_min"] and tab_body_total < th["body_md_short_tabs_total"]:
        return f"body_md_short body={len(body_md)} tabs_total={tab_body_total}"
    from .text_display import polish_content_has_connector_api_leak

    if polish_content_has_connector_api_leak(body_md):
        return "body_md_api_json_leak"
    from .domain.articles import (
        collect_polish_text_blob,
        polish_payload_has_substantive_content,
        polish_substantive_char_count,
    )

    if not polish_payload_has_substantive_content(data):
        from .domain.articles import (
            collect_polish_text_blob,
            polish_substantive_cjk_count,
            strip_urls_and_markdown_links,
        )

        stripped = strip_urls_and_markdown_links(collect_polish_text_blob(data))
        got = polish_substantive_char_count(stripped)
        cjk = polish_substantive_cjk_count(stripped)
        fk = str(data.get("feed_kind") or "news").strip().lower()
        if fk == "news" and cjk < 48:
            return f"no_content_substantive_cjk got_cjk={cjk} need>=48"
        return f"no_content_substantive got={got} need>=80"
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
    if (admin_source_key or "").strip().lower() == "github":
        fk = "apps"
    elif fk not in ("news", "apps"):
        fk = "news"
    th_gate = publish_polish_length_thresholds(admin_source_key)
    # 指纹/去重仍用完整 snippet；送模型前压成编辑摘要（无对话历史）。
    snippet_compact = compact_snippet_for_llm(snippet, admin_source_key=admin_source_key)
    snippet_cut = snippet_compact[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]
    system = _build_polish_system(fk=fk, admin_source_key=admin_source_key, th_gate=th_gate)
    system_json = system + " 只输出一个 JSON 对象，不要其它文字。"
    user = _build_polish_user(
        snippet_cut=snippet_cut,
        admin_source_key=admin_source_key,
        connector_name=connector_name,
        segment_label=segment_label,
        rule_title=rule_title,
        rule_summary=rule_summary,
        value_score=value_score,
        fk=fk,
    )
    snippet_for_compat = snippet_cut

    def _try_publish(data: dict | None) -> tuple[dict | None, str]:
        if not data:
            return None, ""
        fixed = ensure_publishable_polish(
            data,
            admin_source_key=admin_source_key,
            snippet=snippet_for_compat,
            rule_title=rule_title,
            rule_summary=rule_summary,
        )
        return (fixed, "") if fixed else (None, _describe_polish_reject(data, admin_source_key=admin_source_key))

    try:
        try:
            raw = _polish_llm_call(db, system=system, user=user, ref_id=ref_id, response_json=True)
        except Exception as e1:
            try:
                raw = _polish_llm_call(
                    db, system=system_json, user=user, ref_id=ref_id, response_json=False
                )
            except Exception as e2:
                err = f"{type(e2).__name__}: {str(e2)[:240]}"
                _log_usage(
                    db,
                    "article_ingest_polish",
                    _model,
                    0,
                    0,
                    False,
                    "connector_article",
                    ref_id[:64],
                    err=err,
                )
                return None, f"llm_http_failed retry_after_json_mode failed={type(e1).__name__}; {err}"
        out, parse_err = _parse_polish_response(raw, default_feed_kind=fk)
        if not out:
            return None, parse_err
        published, reject = _try_publish(out)
        if published:
            return published, ""

        try:
            from .connector_ingest_diagnostics import diagnose_polish_failure
            from .sync_diagnostic_log import commit_diagnostics, get_current_run_id, write as diag_write

            diag_write(
                db,
                level="error",
                step="llm_polish_retry",
                message=(
                    f"source={admin_source_key} ref={ref_id[:32]} 首次校验未通过，修复重试 1 次："
                    f"{diagnose_polish_failure(out, reject, admin_source_key=admin_source_key, phase='first_pass')}"
                ),
                source_key=(admin_source_key or "").strip().lower() or None,
                run_id=get_current_run_id(),
            )
            commit_diagnostics(db)
        except Exception:
            pass

        repair_snip = snippet_cut[:POLISH_REPAIR_SNIPPET_MAX]
        repair_note = (
            f"【校验未通过】{reject}\n"
            f"请重新输出完整 JSON，满足字数门槛与 tab 结构；全文简体中文。"
            f"categories 须为 1 个元素，取自：{', '.join(sorted(FACET_ALL_LABELS))}。"
        )
        repair_user = _build_polish_user(
            snippet_cut=repair_snip,
            admin_source_key=admin_source_key,
            connector_name=connector_name,
            segment_label=segment_label,
            rule_title=rule_title,
            rule_summary=rule_summary,
            value_score=value_score,
            fk=fk,
            repair_note=repair_note,
        )
        try:
            raw2 = _polish_llm_call(
                db,
                system=system_json,
                user=repair_user,
                ref_id=(ref_id[:60] + ":r1")[:64],
                response_json=False,
            )
        except Exception as e2:
            return None, f"validate_failed: {reject}; repair_http={type(e2).__name__}: {str(e2)[:180]}"
        out2, parse_err2 = _parse_polish_response(raw2, default_feed_kind=fk)
        if not out2:
            return None, f"validate_failed: {reject}; repair_parse={parse_err2}"
        published2, reject2 = _try_publish(out2)
        if published2:
            return published2, ""
        out3 = None
        if "_short" in reject2:
            repair2_note = (
                f"【第二次修复】{reject2}\n"
                f"请在「描述」summary 写满≥{th_gate['desc_summary']} 字、body_md≥{th_gate['desc_body']} 字；"
                f"「变现评估」summary≥{th_gate['repl_summary']}、body≥{th_gate['repl_body']}；"
                f"「数据支撑」summary≥{th_gate['hi_summary']}、body≥{th_gate['hi_body']}（含表格与链接）。"
                "全文简体中文。只输出 JSON。"
            )
            repair2_user = _build_polish_user(
                snippet_cut=snippet_cut[:POLISH_REPAIR_SNIPPET_MAX],
                admin_source_key=admin_source_key,
                connector_name=connector_name,
                segment_label=segment_label,
                rule_title=rule_title,
                rule_summary=rule_summary,
                value_score=value_score,
                fk=fk,
                repair_note=repair2_note,
            )
            try:
                raw3 = _polish_llm_call(
                    db,
                    system=system_json,
                    user=repair2_user,
                    ref_id=(ref_id[:60] + ":r2")[:64],
                    response_json=False,
                )
                out3, _ = _parse_polish_response(raw3, default_feed_kind=fk)
                if out3:
                    published3, reject2 = _try_publish(out3)
                    if published3:
                        return published3, ""
            except Exception:
                pass
        for candidate in (out3, out2, out):
            if not candidate:
                continue
            fixed = ensure_publishable_polish(
                candidate,
                admin_source_key=admin_source_key,
                snippet=snippet_for_compat,
                rule_title=rule_title,
                rule_summary=rule_summary,
            )
            if fixed:
                return fixed, ""
        return None, f"validate_failed_after_retry: {reject2}"
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
