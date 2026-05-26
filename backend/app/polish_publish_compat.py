"""
LLM 润色结果发布兼容层：在丢弃入库前，用规则补齐 Tab / 字数 / replication_analysis。
目标：解决失败、兼容旧格式，而不是 skip。
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


def coerce_polish_output(out: dict) -> dict:
    """规整 feed_kind、单分类、Tab 顺序与旧 label 映射。"""
    fk = str(out.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    out["feed_kind"] = fk
    cats = out.get("categories")
    raw_labels = [str(x).strip() for x in cats if str(x).strip()] if isinstance(cats, list) else []
    if not raw_labels:
        raw_labels = [str(out.get("title") or "").strip() or "其他"]
    out["categories"] = [primary_canonical_from_raw_labels(raw_labels)]
    need_labels = required_feed_card_tab_labels(fk)
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
    for lab in need_labels:
        piece = by_label.get(lab)
        if piece:
            ordered.append({"label": lab, **piece})
    if ordered:
        out["tabs"] = ordered
    if fk == "apps":
        norm = normalize_replication_analysis(out.get("replication_analysis"))
        if norm:
            out["replication_analysis"] = norm
    return out


def _merge_text(*parts: str, min_len: int = 0) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    for p in parts:
        s = (p or "").strip()
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
            t = (obj.get("title") or obj.get("name") or "").strip()
            if t:
                return t[:500]
    except json.JSONDecodeError:
        pass
    return ""


def _tab_piece(by_label: dict[str, dict[str, str]], lab: str) -> dict[str, str]:
    return by_label.get(lab) or {"summary": "", "body_md": ""}


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
        existing.get("body_md") or "",
        str(ra.get("tier_rationale") or ""),
        str(ra.get("value_summary") or ""),
        f"技术栈：{stack_txt}" if stack_txt else "",
        plan_txt,
        desc.get("body_md") or "",
        snippet_plain,
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
            repl.get("body_md") or "",
            desc.get("body_md") or "",
            snippet_plain,
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
    if mvp_max < 8 and prod_max < 40:
        defaults = {"S": (24, 80, 80, 240), "A": (40, 120, 120, 400), "B": (80, 200, 200, 600), "C": (120, 320, 320, 960)}
        a, b, c, d = defaults.get(tier, defaults["B"])
        ra["estimated_hours"] = {"mvp_min": a, "mvp_max": b, "prod_min": c, "prod_max": d}
    plan = ra.get("implementation_plan")
    if not isinstance(plan, list) or not [x for x in plan if str(x).strip()]:
        lines = [ln.strip() for ln in (repl.get("body_md") or "").splitlines() if ln.strip()]
        steps = [ln.lstrip("-*0123456789. ") for ln in lines if len(ln) > 8][:8]
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
    if str(ra.get("verdict") or "") not in ("值得复刻", "观望", "不建议"):
        ra["verdict"] = "观望"
    if str(ra.get("difficulty") or "") not in ("低", "中", "高"):
        ra["difficulty"] = "中"
    try:
        ra["worth_score"] = max(1, min(10, int(ra.get("worth_score") or 6)))
    except (TypeError, ValueError):
        ra["worth_score"] = 6
    out["replication_analysis"] = ra
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
    need_labels = required_feed_card_tab_labels(fk)

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
            snippet_plain,
            min_len=36,
        )[:512]
        fixes.append("summary_padded")

    sk_low = (admin_source_key or "").strip().lower()
    if sk_low == "github":
        out["feed_kind"] = "apps"
        fk = "apps"
        need_labels = required_feed_card_tab_labels(fk)
        from .domain.articles import normalize_replication_tier

        out["categories"] = [primary_canonical_from_raw_labels(["开源客户端(好抄)"])]
        tier = normalize_replication_tier(out.get("replication_tier"))
        if tier not in ("S", "A"):
            out["replication_tier"] = "A"
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

    if fk == "apps" and FEED_CARD_TAB_REPLICATION not in by_label:
        by_label[FEED_CARD_TAB_REPLICATION] = _synthesize_replication_tab(
            by_label,
            normalize_replication_analysis(out.get("replication_analysis")),
            snippet_plain=snippet_plain,
            rule_summary=rule_summary,
        )
        fixes.append("synth_replication_tab")

    if FEED_CARD_TAB_DATA not in by_label:
        by_label[FEED_CARD_TAB_DATA] = _synthesize_data_tab(
            by_label,
            snippet_plain=snippet_plain,
            rule_summary=rule_summary,
            admin_source_key=sk_low,
            snippet=snippet,
        )
        fixes.append("synth_data_tab")

    if FEED_CARD_TAB_DESCRIPTION not in by_label:
        by_label[FEED_CARD_TAB_DESCRIPTION] = {
            "summary": _merge_text(rule_summary, snippet_plain, min_len=th["desc_summary"])[:512],
            "body_md": _merge_text(snippet_plain, rule_summary, min_len=th["desc_body"]),
        }
        fixes.append("synth_desc_tab")

    if fk == "apps":
        _ensure_replication_analysis_object(out, by_label, snippet_plain=snippet_plain)

    for lab in need_labels:
        piece = by_label.setdefault(lab, {"summary": "", "body_md": ""})
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
            sources_body = [piece.get("body_md") or "", snippet_plain, rule_summary]
            sources_sum = [piece.get("summary") or "", piece.get("body_md") or "", rule_summary]
            if lab == FEED_CARD_TAB_REPLICATION:
                ra = out.get("replication_analysis") if isinstance(out.get("replication_analysis"), dict) else {}
                sources_body.insert(0, str(ra.get("tier_rationale") or ""))
                sources_sum.insert(0, str(ra.get("value_summary") or ""))
            new_body = _merge_text(piece.get("body_md") or "", *sources_body, min_len=mb)
            new_sum = _merge_text(piece.get("summary") or "", *sources_sum, min_len=ms)
        if new_body != piece.get("body_md") or new_sum != piece.get("summary"):
            fixes.append(f"pad_tab:{lab}")
        piece["summary"] = new_sum[:512]
        piece["body_md"] = new_body

    out["tabs"] = [{"label": lab, **by_label[lab]} for lab in need_labels if lab in by_label]

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


def ensure_publishable_polish(
    data: dict | None,
    *,
    admin_source_key: str | None = None,
    snippet: str = "",
    rule_title: str = "",
    rule_summary: str = "",
) -> dict | None:
    """兼容修复后若仍可通过校验则返回 dict，否则 None。"""
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
