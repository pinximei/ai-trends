"""
LLM 润色结果入库修复：在丢弃前补齐 Tab / 字数 / replication_analysis（仅用于当次连接器润色）。
"""
from __future__ import annotations

import json
import re
from typing import Any

from .domain.articles import (
    FACET_ALL_LABELS,
    FEED_CARD_TAB_DATA,
    FEED_CARD_TAB_DESCRIPTION,
    canonical_feed_card_tab_label,
    mandatory_feed_card_tab_labels,
    optional_feed_card_tab_labels,
    primary_canonical_from_raw_labels,
    publish_polish_length_thresholds,
    required_feed_card_tab_labels,
    validate_llm_polish_for_publish,
)
from .domain.replication_analysis import (
    FEED_CARD_TAB_REPLICATION,
    normalize_replication_analysis,
    validate_replication_analysis_for_publish,
)


def _absorb_top_level_body_into_desc(out: dict) -> None:
    """模型常把正文写在 body_md 而不写 tabs：归入「描述」，避免 tabs_count=0 误判。"""
    body_md = str(out.get("body_md") or "").strip()
    summary = str(out.get("summary") or "").strip()
    tabs = out.get("tabs")
    by_desc: dict[str, str] = {"summary": "", "body_md": ""}
    if isinstance(tabs, list):
        for t in tabs:
            if isinstance(t, dict) and canonical_feed_card_tab_label(str(t.get("label") or "")) == FEED_CARD_TAB_DESCRIPTION:
                by_desc["summary"] = str(t.get("summary") or "").strip()
                by_desc["body_md"] = str(t.get("body_md") or "").strip()
                break
    if not by_desc["body_md"] and body_md:
        by_desc["body_md"] = body_md
    if not by_desc["summary"] and summary:
        by_desc["summary"] = summary
    if by_desc["body_md"] or by_desc["summary"]:
        if not isinstance(tabs, list):
            tabs = []
            out["tabs"] = tabs
        if not any(
            isinstance(t, dict) and canonical_feed_card_tab_label(str(t.get("label") or "")) == FEED_CARD_TAB_DESCRIPTION
            for t in tabs
        ):
            tabs.append({"label": FEED_CARD_TAB_DESCRIPTION, **by_desc})


def coerce_polish_output(out: dict) -> dict:
    """规整 feed_kind、单分类、Tab 顺序；将模型误用的 Tab 名映射为规范名。"""
    fk = str(out.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    out["feed_kind"] = fk
    cats = out.get("categories")
    raw_labels = [str(x).strip() for x in cats if str(x).strip()] if isinstance(cats, list) else []
    if not raw_labels:
        raw_labels = [str(out.get("title") or "").strip() or "其他"]
    out["categories"] = [primary_canonical_from_raw_labels(raw_labels)]
    _absorb_top_level_body_into_desc(out)
    display_order = required_feed_card_tab_labels(fk)
    tabs = out.get("tabs")
    by_label: dict[str, dict[str, str]] = {}
    if isinstance(tabs, list):
        for t in tabs:
            if not isinstance(t, dict):
                continue
            lab = canonical_feed_card_tab_label(str(t.get("label") or ""))
            sm = str(t.get("summary") or "").strip()
            bd = str(t.get("body_md") or "").strip()
            if not lab:
                continue
            if not sm and not bd:
                continue
            piece = {"summary": sm, "body_md": bd}
            prev = by_label.get(lab)
            if prev:
                if len(bd) > len(prev.get("body_md") or ""):
                    prev["body_md"] = bd
                if len(sm) > len(prev.get("summary") or ""):
                    prev["summary"] = sm
            else:
                by_label[lab] = piece
    ordered: list[dict[str, str]] = []
    for lab in display_order:
        piece = by_label.get(lab)
        if piece:
            ordered.append({"label": lab, **piece})
    if not ordered and FEED_CARD_TAB_DESCRIPTION in by_label:
        ordered.append({"label": FEED_CARD_TAB_DESCRIPTION, **by_label[FEED_CARD_TAB_DESCRIPTION]})
    if ordered:
        out["tabs"] = ordered
    if fk == "apps":
        norm = normalize_replication_analysis(out.get("replication_analysis"))
        if norm:
            out["replication_analysis"] = norm
    return out


def _merge_text(*parts: str, min_len: int = 0) -> str:
    from .text_display import sanitize_polish_tab_text

    chunks: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = sanitize_polish_tab_text(p)
        if not s or s in seen:
            continue
        seen.add(s)
        chunks.append(s)
    out = "\n\n".join(chunks).strip()
    if min_len > 0 and len(out) < min_len and chunks:
        pad_src = chunks[-1]
        while len(out) < min_len and pad_src:
            out = (out + "\n\n" + pad_src).strip()
            if len(out) > min_len + 400:
                break
    return out[:12000]


def _snippet_plain(snippet: str, *, max_len: int = 4000, admin_source_key: str = "") -> str:
    from .text_display import format_connector_snippet_plain

    return format_connector_snippet_plain(
        snippet,
        admin_source_key=admin_source_key,
        max_len=max_len,
    )


def _title_from_snippet(snippet: str) -> str:
    try:
        obj = json.loads((snippet or "").strip()[:8000])
        if isinstance(obj, dict):
            t = (obj.get("title") or obj.get("name") or obj.get("listingHeadline") or "").strip()
            if t:
                return t[:500]
    except json.JSONDecodeError:
        pass
    raw = (snippet or "")[:8000]
    m = re.search(r'"(?:title|name)"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if m:
        return m.group(1).replace('\\"', '"')[:500]
    return ""


def _tab_piece(by_label: dict[str, dict[str, str]], lab: str) -> dict[str, str]:
    return by_label.get(lab) or {"summary": "", "body_md": ""}


def _narrative_sources(*parts: str) -> list[str]:
    """合并叙述用片段：去掉连接器 KV 行，禁止字段表垫字。"""
    from .text_display import is_connector_kv_field_line, strip_connector_kv_lines

    out: list[str] = []
    for p in parts:
        s = strip_connector_kv_lines(p)
        if not s:
            continue
        if all(is_connector_kv_field_line(ln) for ln in s.splitlines() if ln.strip()):
            continue
        out.append(s)
    return out


def _usable_plan_line(ln: str) -> bool:
    from .text_display import is_connector_kv_field_line

    s = ln.strip().lstrip("-*0123456789. ").strip()
    return len(s) > 8 and not is_connector_kv_field_line(s)


def _synthesize_replication_tab(
    by_label: dict[str, dict[str, str]],
    ra: dict[str, Any] | None,
    *,
    snippet_plain: str,
    rule_summary: str,
) -> dict[str, str]:
    desc = _tab_piece(by_label, FEED_CARD_TAB_DESCRIPTION)
    existing = _tab_piece(by_label, FEED_CARD_TAB_REPLICATION)
    if existing.get("body_md") and len(existing["body_md"]) >= 80:
        return existing
    ra = ra or {}
    plan = ra.get("implementation_plan") or []
    plan_txt = "\n".join(f"- {p}" for p in plan if str(p).strip()) if isinstance(plan, list) else ""
    stack = ra.get("tech_stack") or []
    stack_txt = "、".join(str(x) for x in stack if str(x).strip()) if isinstance(stack, list) else ""
    body = _merge_text(
        *_narrative_sources(
            existing.get("body_md") or "",
            str(ra.get("tier_rationale") or ""),
            str(ra.get("value_summary") or ""),
            f"技术栈：{stack_txt}" if stack_txt else "",
            plan_txt,
            desc.get("body_md") or "",
        ),
        min_len=180,
    )
    summary = _merge_text(
        existing.get("summary") or "",
        str(ra.get("value_summary") or ""),
        desc.get("summary") or "",
        rule_summary,
        min_len=52,
    )
    return {"summary": summary[:512], "body_md": body}


def _synthesize_data_tab(
    by_label: dict[str, dict[str, str]],
    *,
    snippet_plain: str,
    rule_summary: str,
    admin_source_key: str = "",
    snippet: str = "",
) -> dict[str, str]:
    from .domain.articles import build_connector_data_tab_markdown
    from .text_display import markdown_to_plain_preview

    existing = _tab_piece(by_label, FEED_CARD_TAB_DATA)
    desc = _tab_piece(by_label, FEED_CARD_TAB_DESCRIPTION)
    table_md = ""
    if snippet.strip():
        table_md = build_connector_data_tab_markdown(admin_source_key, snippet)
    if table_md.strip():
        body = table_md
    else:
        from .text_display import prepare_detail_data_tab_body

        body = prepare_detail_data_tab_body(
            _merge_text(existing.get("body_md") or "", desc.get("body_md") or "", min_len=60),
            admin_source_key=admin_source_key,
            snippet=snippet,
        )
    summary = _merge_text(
        existing.get("summary") or "",
        markdown_to_plain_preview(table_md or snippet_plain, max_len=200),
        "关键指标与链接见下表。",
        rule_summary,
        min_len=12,
    )
    return {"summary": summary[:512], "body_md": body}


def _ensure_replication_analysis_object(
    out: dict,
    by_label: dict[str, dict[str, str]],
    *,
    snippet_plain: str,
) -> None:
    repl = _tab_piece(by_label, FEED_CARD_TAB_REPLICATION)
    desc = _tab_piece(by_label, FEED_CARD_TAB_DESCRIPTION)
    ra = normalize_replication_analysis(out.get("replication_analysis")) or {}
    tier = str(out.get("replication_tier") or "B").strip().upper()[:1] or "B"
    if tier not in ("S", "A", "B", "C"):
        tier = "B"
    if len(str(ra.get("tier_rationale") or "")) < 20:
        ra["tier_rationale"] = _merge_text(
            *_narrative_sources(repl.get("body_md") or "", desc.get("body_md") or ""),
            min_len=20,
        )[:1200]
    if len(str(ra.get("value_summary") or "")) < 16:
        ra["value_summary"] = _merge_text(
            repl.get("summary") or "",
            desc.get("summary") or "",
            str(out.get("summary") or ""),
            min_len=16,
        )[:1200]
    hours = ra.get("estimated_hours")
    if not isinstance(hours, dict):
        hours = {}
    mvp_max = int(hours.get("mvp_max") or 0)
    prod_max = int(hours.get("prod_max") or 0)
    phases = ra.get("phases")
    if not isinstance(phases, list) or len(phases) < 3:
        plan_lines = [
            ln.strip()
            for ln in (repl.get("body_md") or "").splitlines()
            if _usable_plan_line(ln)
        ][:6]
        synth_phases = []
        defaults_h = [(16, 24), (20, 32), (24, 40)]
        for i, (lo, hi) in enumerate(defaults_h):
            title = (
                plan_lines[i].lstrip("-*0123456789. ")[:40]
                if i < len(plan_lines)
                else f"阶段 {i + 1}"
            )
            synth_phases.append(
                {
                    "name": title or f"阶段 {i + 1}",
                    "hours_min": lo,
                    "hours_max": hi,
                    "deliverable": "可演示交付物（需结合正文核对）",
                }
            )
        ra["phases"] = synth_phases
    if mvp_max < 8 and prod_max < 40:
        from .domain.replication_analysis import _normalize_phases, _sync_hours_from_phases

        ra["estimated_hours"] = _sync_hours_from_phases(
            _normalize_phases(ra.get("phases")),
            {"mvp_min": 0, "mvp_max": 0, "prod_min": 0, "prod_max": 0},
        )
    plan = ra.get("implementation_plan")
    if not isinstance(plan, list) or not [x for x in plan if str(x).strip()]:
        lines = [ln.strip() for ln in (repl.get("body_md") or "").splitlines() if _usable_plan_line(ln)]
        steps = [ln.lstrip("-*0123456789. ") for ln in lines][:8]
        ra["implementation_plan"] = steps or ["梳理产品边界与核心用户", "搭建 MVP 并验证留存", "补齐数据支撑与变现路径"]
    stack = ra.get("tech_stack")
    if not isinstance(stack, list) or not [x for x in stack if str(x).strip()]:
        found = re.findall(
            r"\b(Python|TypeScript|JavaScript|React|Next\.js|Vue|Go|Rust|Docker|Kubernetes|"
            r"FastAPI|Flask|PostgreSQL|Redis|OpenAI|LLM|API)\b",
            repl.get("body_md") or desc.get("body_md") or "",
            flags=re.I,
        )
        ra["tech_stack"] = list(dict.fromkeys(found))[:8] or ["Web", "API"]
    if str(ra.get("verdict") or "") not in ("高价值", "观望", "不建议"):
        ra["verdict"] = "观望"
    if str(ra.get("difficulty") or "") not in ("低", "中", "高"):
        ra["difficulty"] = "中"
    try:
        ra["worth_score"] = max(1, min(10, int(ra.get("worth_score") or 4)))
    except (TypeError, ValueError):
        ra["worth_score"] = 4
    mp = ra.get("market_position")
    if not isinstance(mp, dict):
        mp = {}
    title_guess = str(out.get("title") or "该产品").strip()[:80]
    if len(str(mp.get("target_user") or "")) < 10:
        mp["target_user"] = f"关注 {title_guess} 所解决场景的小型团队与个人开发者"
    if len(str(mp.get("vertical_niche") or "")) < 10:
        mp["vertical_niche"] = f"围绕「{title_guess}」的垂直场景，需结合原文核对是否够窄"
    if str(mp.get("market_saturation") or "") not in ("红海", "竞争适中", "细分蓝海"):
        mp["market_saturation"] = "竞争适中"
    if not isinstance(mp.get("competitors"), list) or not [c for c in mp.get("competitors") if isinstance(c, dict)]:
        mp["competitors"] = [{"name": "同类 Web/SaaS 竞品（需自行检索）", "note": "差异化见 differentiation 字段"}]
    if len(str(mp.get("differentiation") or "")) < 12:
        mp["differentiation"] = _merge_text(repl.get("summary") or "", str(ra.get("value_summary") or ""), min_len=12)[:800]
    if len(str(mp.get("monetization_hypothesis") or "")) < 16:
        from .domain.replication_analysis import monetization_hypothesis_is_substantive

        vs = str(ra.get("value_summary") or "").strip()
        if monetization_hypothesis_is_substantive(vs):
            mp["monetization_hypothesis"] = vs[:800]
        else:
            mp["monetization_hypothesis"] = (
                f"「{title_guess}」类 SaaS/工具产品：可先对照 Product Hunt 页与官网验证订阅、买断或用量计费，"
                "再小范围试投放（需人工核对，非自动定价结论）"
            )[:800]
    ra["market_position"] = mp
    risks = ra.get("risks")
    if not isinstance(risks, list) or not [x for x in risks if str(x).strip()]:
        ra["risks"] = ["竞争与获客成本需自行验证"]
    if not str(ra.get("platform_fit") or "").strip():
        ra["platform_fit"] = "unknown"
    ai_steps = ra.get("ai_usage_steps")
    if not isinstance(ai_steps, list) or len([x for x in ai_steps if str(x).strip()]) < 2:
        ra["ai_usage_steps"] = [
            "用 LLM 根据原文生成 MVP 功能清单与文案草稿（人工删减）",
            "编码阶段：核心数据流用确定性逻辑，仅辅助环节调用模型 API",
        ]
    out["replication_analysis"] = normalize_replication_analysis(ra) or ra
    out["replication_tier"] = tier


def repair_polish_for_publish(
    data: dict,
    *,
    admin_source_key: str | None = None,
    snippet: str = "",
    rule_title: str = "",
    rule_summary: str = "",
) -> tuple[dict, list[str]]:
    """规则修复润色 JSON，返回 (修复后, 已执行的修复动作列表)。"""
    out = dict(data)
    fixes: list[str] = []
    th = publish_polish_length_thresholds(admin_source_key)
    snippet_plain = _snippet_plain(snippet, admin_source_key=admin_source_key or "")
    fk = str(out.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    out["feed_kind"] = fk
    mandatory = mandatory_feed_card_tab_labels(fk)
    optional = optional_feed_card_tab_labels(fk)

    title = str(out.get("title") or "").strip()
    if (not title or ("同步资源" in title and "·" in title)) and _title_from_snippet(snippet):
        out["title"] = _title_from_snippet(snippet)
        fixes.append("title_from_snippet")
    elif not title and rule_title:
        out["title"] = rule_title.replace("同步资源 ·", "").strip()[:500]
        fixes.append("title_from_rule")

    summary = str(out.get("summary") or "").strip()
    if len(summary) < 36:
        out["summary"] = _merge_text(
            summary,
            rule_summary,
            str(out.get("body_md") or ""),
            min_len=36,
        )[:512]
        fixes.append("summary_padded")

    sk_low = (admin_source_key or "").strip().lower()
    if sk_low == "github":
        out["feed_kind"] = "apps"
        fk = "apps"
        mandatory = mandatory_feed_card_tab_labels(fk)
        optional = optional_feed_card_tab_labels(fk)
        from .domain.articles import normalize_replication_tier

        out["categories"] = [primary_canonical_from_raw_labels(["开源客户端(好抄)"])]
        tier = normalize_replication_tier(out.get("replication_tier"))
        if tier not in ("S", "A", "B", "C"):
            out["replication_tier"] = "B"
        fixes.append("github_apps_defaults")

    cats = out.get("categories")
    if not isinstance(cats, list) or len([c for c in cats if str(c).strip()]) != 1:
        default_cat = "应用产品" if fk == "apps" else "其他"
        out["categories"] = [primary_canonical_from_raw_labels([default_cat])]
        fixes.append("categories_fixed")

    by_label: dict[str, dict[str, str]] = {}
    tabs = out.get("tabs")
    if isinstance(tabs, list):
        for t in tabs:
            if not isinstance(t, dict):
                continue
            lab = canonical_feed_card_tab_label(str(t.get("label") or ""))
            if lab:
                by_label[lab] = {
                    "summary": str(t.get("summary") or "").strip(),
                    "body_md": str(t.get("body_md") or "").strip(),
                }

    if FEED_CARD_TAB_DESCRIPTION not in by_label:
        by_label[FEED_CARD_TAB_DESCRIPTION] = {
            "summary": _merge_text(rule_summary, min_len=th["desc_summary"])[:512],
            "body_md": _merge_text(rule_summary, min_len=th["desc_body"]),
        }
        fixes.append("synth_desc_tab")

    if fk == "apps":
        _ensure_replication_analysis_object(out, by_label, snippet_plain=snippet_plain)

    for lab in mandatory + optional:
        if lab not in by_label:
            continue
        piece = by_label[lab]
        if lab == FEED_CARD_TAB_DESCRIPTION:
            ms, mb = th["desc_summary"], th["desc_body"]
        elif lab == FEED_CARD_TAB_REPLICATION:
            ms, mb = th.get("repl_summary", 52), th.get("repl_body", 180)
        else:
            ms, mb = th["hi_summary"], th["hi_body"]
        if lab == FEED_CARD_TAB_DATA:
            from .text_display import markdown_to_plain_preview, prepare_detail_data_tab_body

            new_body = prepare_detail_data_tab_body(
                _merge_text(piece.get("body_md") or "", rule_summary, min_len=mb),
                admin_source_key=sk_low,
                snippet=snippet,
            )
            new_sum = _merge_text(
                piece.get("summary") or "",
                markdown_to_plain_preview(new_body, max_len=200),
                min_len=ms,
            )
        else:
            narr_body = _narrative_sources(piece.get("body_md") or "")
            sources_body: list[str] = list(narr_body)
            sources_body.append(rule_summary)
            sources_sum = [piece.get("summary") or "", *(narr_body or [piece.get("body_md") or ""]), rule_summary]
            if lab == FEED_CARD_TAB_REPLICATION:
                ra = out.get("replication_analysis") if isinstance(out.get("replication_analysis"), dict) else {}
                tier = str(ra.get("tier_rationale") or "").strip()
                val = str(ra.get("value_summary") or "").strip()
                if tier:
                    sources_body.insert(0, tier)
                if val:
                    sources_sum.insert(0, val)
            new_body = _merge_text(*sources_body, min_len=mb)
            new_sum = _merge_text(*sources_sum, min_len=ms)
        if new_body != piece.get("body_md") or new_sum != piece.get("summary"):
            fixes.append(f"pad_tab:{lab}")
        piece["summary"] = new_sum[:512]
        piece["body_md"] = new_body

    from .text_display import normalize_article_tabs_for_display

    tabs_list = []
    for lab in required_feed_card_tab_labels(fk):
        piece = by_label.get(lab)
        if piece and (piece.get("summary") or piece.get("body_md")):
            tabs_list.append({"label": lab, **piece})
    out["tabs"] = normalize_article_tabs_for_display(
        tabs_list,
        admin_source_key=sk_low,
        snippet=snippet,
    )

    body_md = str(out.get("body_md") or "").strip()
    joined = "\n\n".join(
        f"## {t['label']}\n\n{t.get('body_md', '')}"
        for t in out["tabs"]
        if isinstance(t, dict)
    )
    if len(body_md) < th["body_md_min"]:
        out["body_md"] = _merge_text(body_md, joined, min_len=th["body_md_min"])[:50000]
        fixes.append("body_md_padded")

    return coerce_polish_output(out), fixes


def build_rule_fallback_polish_from_snippet(
    *,
    admin_source_key: str,
    snippet: str,
    rule_title: str = "",
    rule_summary: str = "",
    feed_kind: str = "news",
) -> dict | None:
    """
    连接器入库兜底：不调用 LLM，从上游 JSON + 规则摘要合成 Tab 并走 repair/校验。
    用于模型 JSON 损坏、tabs 为空或多次修复仍失败时，避免整批 0 入库。
    """
    sk = (admin_source_key or "").strip()
    fk = (feed_kind or "news").strip().lower()
    if sk.lower() == "github":
        fk = "apps"
    elif fk not in ("news", "apps"):
        fk = "news"

    title = _title_from_snippet(snippet)
    if not title or ("同步资源" in title and "·" in title):
        rt = (rule_title or "").strip()
        if "·" in rt:
            title = rt.rsplit("·", 1)[-1].strip()
        elif rt:
            title = rt.replace("同步资源 ·", "").strip()
    if not title:
        title = "未命名条目"

    plain = _snippet_plain(snippet, admin_source_key=sk)
    summary = (rule_summary or "").strip()
    if len(summary) < 36:
        summary = _merge_text(summary, plain, min_len=36)[:512]
    if not summary:
        return None

    default_cat = "应用产品" if fk == "apps" else "其他"
    if sk.lower() == "product_hunt":
        fk = "apps"
        default_cat = "应用产品"
    raw: dict[str, Any] = {
        "title": title[:500],
        "summary": summary[:512],
        "body_md": summary,
        "feed_kind": fk,
        "categories": [default_cat],
        "tabs": [],
    }
    if fk == "apps":
        raw["replication_tier"] = "B"
    return ensure_publishable_polish(
        raw,
        admin_source_key=sk,
        snippet=snippet,
        rule_title=rule_title,
        rule_summary=rule_summary,
    )


def ensure_publishable_polish(
    data: dict | None,
    *,
    admin_source_key: str | None = None,
    snippet: str = "",
    rule_title: str = "",
    rule_summary: str = "",
) -> dict | None:
    """规则修复后若仍可通过校验则返回 dict，否则 None。"""
    if not data or not isinstance(data, dict):
        return None
    sk = admin_source_key
    kw = dict(
        admin_source_key=sk,
        snippet=snippet,
        rule_title=rule_title,
        rule_summary=rule_summary,
    )
    d = coerce_polish_output(dict(data))
    if validate_llm_polish_for_publish(d, admin_source_key=sk):
        return d
    d, _ = repair_polish_for_publish(d, **kw)
    if validate_llm_polish_for_publish(d, admin_source_key=sk):
        return d
    return None
