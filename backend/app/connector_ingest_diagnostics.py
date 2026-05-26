"""连接器拉取 / 入库失败原因：供同步诊断日志（仅 error 级）展示。"""
from __future__ import annotations

import re

from .domain.articles import publish_polish_length_thresholds

# 应用稿三 Tab 最低字数（默认阈值，与 publish_polish_length_thresholds 一致）
_APPS_TAB_HINT = (
    "应用稿须 3 个 Tab：「描述」「复刻评估」「数据支撑」，"
    "且含 replication_analysis（结论、工时、技术栈、实现步骤等）。"
)


def explain_polish_reject(reason: str, *, admin_source_key: str | None = None) -> str:
    """
    将 ``_describe_polish_reject`` / ``validate_failed*`` 的机器码转为可读的失败原因。
    字数不足通常不是业务逻辑 bug，而是 LLM 未按 prompt 写满或 repair 仍偏短。
    """
    r = (reason or "").strip()
    if r.startswith("validate_failed"):
        r = r.split(":", 1)[-1].strip()
    if r.startswith("validate_failed_after_retry"):
        r = r.split(":", 1)[-1].strip()
    th = publish_polish_length_thresholds(admin_source_key)
    sk = (admin_source_key or "").strip().lower()

    if not r or r == "validate_unknown":
        return "LLM 润色结果未通过发布校验（原因未分类，请查看机器码或重试同步）。"
    if r == "title_or_summary_empty title=False summary_len=0" or "title_or_summary_empty" in r:
        return "LLM 未返回有效标题或摘要。"
    if m := re.match(r"summary_too_short len=(\d+) need>=36", r):
        return f"卡片摘要过短（{m.group(1)} 字，至少 36 字）。多为模型输出过短。"
    if m := re.match(r"bad_categories got=(.+)", r):
        return f"分类不合法：{m.group(1)}。须为规范大类之一。"
    if m := re.match(r"tabs_count=(\S+) need=(\d+)", r):
        got = m.group(1)
        need = m.group(2)
        extra = _APPS_TAB_HINT if need == "3" else "资讯稿须 2 个 Tab：「描述」「数据支撑」。"
        return f"Tab 数量不对（实际 {got}，需要 {need}）。{extra}"
    if r == "tab_not_object":
        return "tabs 数组中存在非对象项。"
    if m := re.match(r"tab_(.+)_summary_short len=(\d+) need>=(\d+)", r):
        lab = m.group(1)
        got, need = m.group(2), m.group(3)
        hint = _tab_short_hint(lab, sk, th)
        return f"Tab「{lab}」摘要过短：实际 {got} 字，要求 ≥{need} 字。{hint}"
    if m := re.match(r"tab_(.+)_body_short len=(\d+) need>=(\d+)", r):
        lab = m.group(1)
        got, need = m.group(2), m.group(3)
        hint = _tab_short_hint(lab, sk, th)
        return f"Tab「{lab}」正文过短：实际 {got} 字，要求 ≥{need} 字。{hint}"
    if m := re.match(r"tab_labels=(.+) need=(.+)", r):
        return f"Tab 名称不匹配：实际 {m.group(1)}，需要 {m.group(2)}。"
    if r == "replication_analysis_invalid":
        return (
            "「复刻评估」结构化字段不完整：须含 tier_rationale、value_summary、"
            "estimated_hours（mvp_max≥8 或 prod_max≥40）、tech_stack、implementation_plan 等。"
        )
    if m := re.match(r"tab_body_total_short len=(\d+) need>=(\d+)", r):
        return (
            f"所有 Tab 正文总字数不足（合计 {m.group(1)} 字，要求 ≥{m.group(2)} 字）。"
            "请检查模型是否只写了短句。"
        )
    if m := re.match(r"body_md_short body=(\d+) tabs_total=(\d+)", r):
        return (
            f"总览 body_md 与各 Tab 合计均偏短（body={m.group(1)}，tabs 合计={m.group(2)}）。"
        )
    return f"LLM 校验未通过：{r}"


def _tab_short_hint(lab: str, source_key: str, th: dict[str, int]) -> str:
    if lab == "描述":
        return (
            "「描述」用于产品/事件说明，不是一句话带过。"
            f"当前门槛 summary≥{th['desc_summary']}、body≥{th['desc_body']}。"
        )
    if lab == "复刻评估":
        return (
            "「复刻评估」须写清是否值得复刻、技术栈与步骤。"
            f"当前门槛 summary≥{th.get('repl_summary', 52)}、body≥{th.get('repl_body', 180)}。"
            f"{' ' + _APPS_TAB_HINT if source_key != 'newsapi' and source_key != 'thenewsapi' else ''}"
        )
    if lab in ("数据支撑", "要点", "功能亮点"):
        return (
            "「数据支撑」须含可核对指标表格与链接（star、定价、链接等）。"
            f"当前门槛 summary≥{th['hi_summary']}、body≥{th['hi_body']}。"
        )
    return "请对照管理端 LLM 提示中的各 Tab 最低字数要求。"


def explain_polish_error(polish_err: str, *, admin_source_key: str | None = None) -> str:
    """润色调用失败或校验失败时的完整说明。"""
    err = (polish_err or "").strip()
    if err == "no_llm_key":
        return "未配置 LLM API Key：请在管理端「AI 资讯与数据」保存后重试。"
    if err.startswith("tabs_incomplete"):
        return f"LLM 返回的 tabs 不完整：{err}"
    if "validate_failed" in err:
        code = err.split(":", 1)[-1].strip() if ":" in err else err
        return explain_polish_reject(code, admin_source_key=admin_source_key)
    if err.startswith("llm_http_failed"):
        return f"调用 LLM 接口失败：{err[:400]}"
    return err[:800] if err else "LLM 润色失败（原因未知）"


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
