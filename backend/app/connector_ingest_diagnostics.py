"""连接器拉取 / 入库 / LLM 润色失败：根因诊断（同步日志 error 行）。"""
from __future__ import annotations

import re

from .domain.articles import (
    TAB_LABEL_ALIASES,
    normalize_tab_label,
    publish_polish_length_thresholds,
    required_feed_card_tab_labels,
)
from .domain.replication_analysis import (
    FEED_CARD_TAB_REPLICATION,
    describe_replication_analysis_reject,
    normalize_replication_analysis,
)

_RE_REJECT_TAB_SUM = re.compile(r"tab_(.+)_summary_short len=(\d+) need>=(\d+)")
_RE_REJECT_TAB_BODY = re.compile(r"tab_(.+)_body_short len=(\d+) need>=(\d+)")


def _strip_reject_code(reason: str) -> str:
    r = (reason or "").strip()
    for prefix in ("validate_failed_after_retry:", "validate_failed:", "validate_failed"):
        if r.startswith(prefix):
            r = r.split(":", 1)[-1].strip()
    return r


def _phase_label(phase: str) -> str:
    p = (phase or "").strip().lower()
    if p == "first_pass":
        return "首次模型输出"
    if p in ("repair1", "repair"):
        return "第 1 次自动修复后"
    if p == "repair2":
        return "第 2 次自动修复后"
    if p == "final":
        return "最终入库前"
    if p == "compat_exhausted":
        return "规则兼容修复后仍无法入库"
    return phase or "校验"


def _tab_lengths(data: dict) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    tabs = data.get("tabs")
    if not isinstance(tabs, list):
        return out
    for t in tabs:
        if not isinstance(t, dict):
            continue
        lab = str(t.get("label") or "").strip()
        if not lab:
            continue
        out[lab] = {
            "summary": len(str(t.get("summary") or "").strip()),
            "body": len(str(t.get("body_md") or "").strip()),
        }
    return out


def _wrong_tab_label_warning(data: dict) -> str | None:
    """模型是否仍输出旧 Tab 名（入库前会自动改成规范名）。"""
    tabs = data.get("tabs")
    if not isinstance(tabs, list):
        return None
    wrong = [
        str(t.get("label") or "").strip()
        for t in tabs
        if isinstance(t, dict) and str(t.get("label") or "").strip() in TAB_LABEL_ALIASES
    ]
    if wrong:
        return f"模型使用了旧 Tab 名 {wrong!r}（入库前会改为规范名，若仍失败请看各 Tab 字数）"
    return None


def diagnose_polish_failure(
    data: dict | None,
    reject: str,
    *,
    admin_source_key: str | None = None,
    phase: str = "final",
    polish_err: str = "",
) -> str:
    """
    结合校验码、实测字数与结构化字段，给出可操作的根因说明。
    不笼统归因于「模型能力差」，区分：解析/HTTP、Tab 结构、字数门槛、replication_analysis、修复轮次耗尽等。
    """
    code = _strip_reject_code(reject)
    err = (polish_err or "").strip()
    th = publish_polish_length_thresholds(admin_source_key)
    sk = (admin_source_key or "").strip().lower()
    lines: list[str] = [f"【{_phase_label(phase)}】"]

    if err.startswith("json_parse_failed"):
        lines.append("根因=JSON 解析失败：模型返回不是合法 JSON 或含多余说明文字。")
        if "raw_preview=" in err:
            lines.append(err[:400])
        return " ".join(lines)

    if err.startswith("tabs_incomplete"):
        lines.append(
            "根因=Tab 数量不足：解析后有效 Tab 少于要求（空 label/summary/body 的项会被丢弃）。"
            f" {err[:300]}"
        )
        return " ".join(lines)

    if err.startswith("llm_http_failed"):
        lines.append(f"根因=LLM HTTP 调用失败（非字数问题）。{err[:350]}")
        return " ".join(lines)

    if err and not code:
        lines.append(_diagnose_polish_err_only(err, admin_source_key=admin_source_key))
        return " ".join(lines)

    if "repair_http=" in err or "repair_parse=" in err:
        lines.append(f"根因=自动修复轮失败。{err[:400]}")
        return " ".join(lines)

    if err.startswith("validate_failed_after_retry"):
        lines.append("根因=已进行 1～2 轮自动修复仍不满足发布校验（见下方分项）。")

    fk = "news"
    if isinstance(data, dict):
        fk = str(data.get("feed_kind") or "news").strip().lower()
        if fk not in ("news", "apps"):
            fk = "news"
    need = required_feed_card_tab_labels(fk)

    if isinstance(data, dict):
        leg = _wrong_tab_label_warning(data)
        if leg:
            lines.append(leg)
        measured = _tab_lengths(data)
        if measured:
            parts = [f"{k}(summary={v['summary']},body={v['body']})" for k, v in measured.items()]
            lines.append(f"实测 Tab 字数：{'；'.join(parts)}。")
        labels = [str(t.get("label") or "").strip() for t in (data.get("tabs") or []) if isinstance(t, dict)]
        if labels and list(labels) != list(need) and fk == "apps":
            canon = [normalize_tab_label(x) for x in labels]
            if canon != list(need):
                lines.append(f"Tab 名称不符：模型={labels!r}，要求={list(need)!r}。")

    if code.startswith("replication_analysis_invalid"):
        detail = code.split(":", 1)[-1].strip() if ":" in code else ""
        if not detail and isinstance(data, dict):
            norm = normalize_replication_analysis(data.get("replication_analysis"))
            detail = describe_replication_analysis_reject(norm)
        lines.append(
            f"根因=replication_analysis 结构化字段不达标（非 Tab 字数）：{detail or '见校验码'}。"
            "常见：工时 mvp_max/prod_max 过小、tech_stack 空、implementation_plan 空。"
        )
        return " ".join(lines)

    m = _RE_REJECT_TAB_SUM.match(code) or _RE_REJECT_TAB_BODY.match(code)
    if m:
        lab, got_s, need_s = m.group(1), int(m.group(2)), int(m.group(3))
        field = "summary" if "_summary_" in code else "body_md"
        gap = need_s - got_s
        th_key = _threshold_key_for_tab(lab, field, th)
        lines.append(
            f"根因=Tab「{lab}」的 {field} 未达发布门槛：实测 {got_s} 字，门槛 ≥{need_s} 字（差 {gap} 字）。"
            f"门槛来自代码校验 publish_polish_length_thresholds（{sk or 'default'}/{th_key}={need_s}）。"
        )
        lines.append(_length_failure_hints(lab, field, got_s, need_s, data))
        if "after_retry" in err or phase in ("repair2", "repair1", "repair"):
            lines.append("已触发自动修复仍不足：请核对 LlmUsageLog scenario=article_ingest_polish 同 ref 的 r1/r2 记录。")
        return " ".join(lines)

    if code.startswith("link_only_substantive"):
        lines.append(
            "根因=正文几乎只有链接或占位摘要（去 URL 后不足 80 字），已拒绝入库。"
            "请确认：① Product Hunt / GitHub 数据源 api_base 为预设 GraphQL / Trending 地址；"
            "② 连接器已绑定 admin_source_key；③ LLM Key 有效且润色未失败。"
            f" {code}"
        )
        return " ".join(lines)

    if code.startswith("tab_labels="):
        lines.append(f"根因=Tab 名称/顺序不符合规范。{code}")
        return " ".join(lines)

    if code.startswith("tabs_count="):
        lines.append(f"根因=Tab 个数不对。{code} 要求={list(need)!r}。")
        return " ".join(lines)

    if code.startswith("bad_categories"):
        lines.append(f"根因=分类字段不合法。{code} 须为规范大类之一。")
        return " ".join(lines)

    if "title_or_summary_empty" in code or code.startswith("summary_too_short"):
        lines.append(f"根因=标题或卡片摘要缺失/过短。{code}")
        return " ".join(lines)

    if code.startswith("tab_body_total_short"):
        lines.append(
            f"根因=所有 Tab 正文合计偏短。{code}（门槛 tab_body_total={th['tab_body_total']}）。"
        )
        return " ".join(lines)

    if code.startswith("body_md_short"):
        lines.append(
            f"根因=总览 body_md 与 Tab 合计均未达兜底长度。{code} "
            f"(body_md_min={th['body_md_min']}, tabs_total 兜底={th['body_md_short_tabs_total']})。"
        )
        return " ".join(lines)

    # 回退：仍带校验码
    brief = explain_polish_reject(code, admin_source_key=admin_source_key)
    lines.append(brief)
    if code:
        lines.append(f"校验码:{code}")
    return " ".join(lines)


def _threshold_key_for_tab(lab: str, field: str, th: dict[str, int]) -> str:
    if lab == "描述":
        return "desc_summary" if field == "summary" else "desc_body"
    if lab == FEED_CARD_TAB_REPLICATION:
        return "repl_summary" if field == "summary" else "repl_body"
    return "hi_summary" if field == "summary" else "hi_body"


def _length_failure_hints(lab: str, field: str, got: int, need: int, data: dict | None) -> str:
    hints: list[str] = []
    if isinstance(data, dict) and lab == FEED_CARD_TAB_REPLICATION and field == "body_md":
        norm = normalize_replication_analysis(data.get("replication_analysis"))
        if norm:
            plan = norm.get("implementation_plan") or []
            stack = norm.get("tech_stack") or []
            if plan or stack:
                hints.append(
                    "replication_analysis 对象有内容但 Tab「变现评估」body 偏短："
                    "须把技术栈/步骤写进 Tab 正文，不能只在 JSON 对象里。"
                )
    if got > 0 and got >= need - 8:
        hints.append("接近门槛：多为修复 prompt 未把字数写满，而非分类/Tab 名错误。")
    if got == 0:
        hints.append("该 Tab 正文为空：检查 JSON 是否把内容写在别的键或 Tab 名下。")
    return " ".join(hints)


def _diagnose_polish_err_only(err: str, *, admin_source_key: str | None) -> str:
    if err == "no_llm_key":
        return "根因=未配置 LLM API Key。"
    if "validate_failed" in err:
        code = _strip_reject_code(err)
        return diagnose_polish_failure(None, code, admin_source_key=admin_source_key, polish_err="")
    return err[:500]


def explain_polish_reject(reason: str, *, admin_source_key: str | None = None) -> str:
    """兼容旧调用：无 data 时仅根据校验码生成简短说明。"""
    return diagnose_polish_failure(None, _strip_reject_code(reason), admin_source_key=admin_source_key)


def explain_polish_error(polish_err: str, *, admin_source_key: str | None = None) -> str:
    """润色调用失败时的完整说明（含解析/HTTP/多轮修复）。"""
    err = (polish_err or "").strip()
    if not err:
        return "根因=润色失败（无错误码）"
    if err == "no_llm_key":
        return "根因=未配置 LLM API Key：请在管理端「AI 资讯与数据」保存后重试。"
    if err.startswith("tabs_incomplete") or err.startswith("json_parse_failed") or err.startswith("llm_http_failed"):
        return diagnose_polish_failure(None, "", admin_source_key=admin_source_key, polish_err=err)
    if "validate_failed" in err:
        code = _strip_reject_code(err)
        phase = "repair2" if ":r2" in err else ("repair1" if "repair" in err else "final")
        if err.startswith("validate_failed_after_retry"):
            phase = "repair_exhausted"
        return diagnose_polish_failure(
            None, code, admin_source_key=admin_source_key, phase=phase, polish_err=err
        )
    return f"根因=润色管线异常。{err[:600]}"


def format_fetch_empty_message(snippet_diag: str, *, source_key: str) -> str:
    """HTTP 200 但 pack 内 0 条时的说明。"""
    d = (snippet_diag or "").strip()
    sk = (source_key or "").strip().lower()
    if "note=no_posts" in d or "note=no_slugs" in d:
        return f"[{sk}] API 返回成功但当日无上榜产品（no_posts）。"
    if "note=detail_fetch_empty" in d:
        return f"[{sk}] 拉到列表但详情接口均未返回内容（detail_fetch_empty），常见：限流 429 或 slug 失效。"
    if "note=acquire_parse_empty" in d or "note=taaft_parse_empty" in d:
        return f"[{sk}] 页面/API 解析结果为空（{d}）。"
    if "not_json" in d:
        return f"[{sk}] 上游响应不是合法 JSON，无法解析 pack。"
    return f"[{sk}] HTTP 200 但 pack_items=0（{d or '无 note'}）。"
