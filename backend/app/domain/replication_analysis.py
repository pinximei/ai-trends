"""应用泳道：变现价值 + 实施工时拆解（入库 JSON + 公开 API；字段名保留 replication_* 兼容）。"""
from __future__ import annotations

import json
import math
import re
from typing import Any

# compat 兜底文案：不得视为真实变现信号
_GENERIC_MONETIZATION_HYPOTHESES: frozenset[str] = frozenset(
    {
        "订阅或买断；优先验证 20 个目标用户付费意愿后再扩功能",
    }
)

_PRICING_SIGNAL_RE = re.compile(
    r"(?:\$\s?\d+|\d+\s*(?:元|美元|USD|usd)|"
    r"\d+\s*/\s*(?:月|mo|month)|"
    r"(?:MRR|ARR|营收|收入|定价|订阅费|买断价|freemium|pricing))",
    re.I,
)

FEED_CARD_TAB_REPLICATION = "变现评估"

_VERDICT_VALUES = frozenset({"高价值", "观望", "不建议"})
_VERDICT_ALIASES: dict[str, str] = {
    "值得复刻": "高价值",
    "值得做": "高价值",
    "高变现": "高价值",
    "不建议复刻": "不建议",
}
_DIFFICULTY_VALUES = frozenset({"低", "中", "高"})
_MARKET_SATURATION_VALUES = frozenset({"红海", "竞争适中", "细分蓝海"})
_PLATFORM_FIT_VALUES = frozenset({"windows", "mac_only", "web", "extension", "cli", "cross_platform", "unknown"})
_MIN_PHASES = 3
_MIN_MVP_HOURS = 8
_PROJECT_PICK_MIN_WORTH = 7
_HIGH_VALUE_MIN_WORTH = 8


def _clip(s: object, n: int) -> str:
    return str(s or "").strip()[:n]


def _as_int(v: object, *, default: int = 0, lo: int = 0, hi: int = 10_000) -> int:
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _as_str_list(raw: object, *, max_items: int = 12, item_max: int = 400) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        s = _clip(x, item_max)
        if s:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_hours_block(raw: object) -> dict[str, int]:
    """MVP / 完整产品预估工时（小时）。"""
    base = {"mvp_min": 0, "mvp_max": 0, "prod_min": 0, "prod_max": 0}
    if not isinstance(raw, dict):
        return base
    for k in base:
        base[k] = _as_int(raw.get(k), default=0, hi=20_000)
    if base["mvp_max"] and base["mvp_min"] > base["mvp_max"]:
        base["mvp_min"], base["mvp_max"] = base["mvp_max"], base["mvp_min"]
    if base["prod_max"] and base["prod_min"] > base["prod_max"]:
        base["prod_min"], base["prod_max"] = base["prod_max"], base["prod_min"]
    return base


def _normalize_phases(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name"), 120)
        if not name:
            continue
        hmin = _as_int(item.get("hours_min"), default=0)
        hmax = _as_int(item.get("hours_max"), default=hmin)
        if hmax and hmin > hmax:
            hmin, hmax = hmax, hmin
        out.append(
            {
                "name": name,
                "hours_min": hmin,
                "hours_max": hmax,
                "deliverable": _clip(item.get("deliverable"), 400),
                "depends_on": _clip(item.get("depends_on"), 120),
            }
        )
        if len(out) >= 8:
            break
    return out


def _sync_hours_from_phases(phases: list[dict[str, Any]], hours: dict[str, int]) -> dict[str, int]:
    if not phases:
        return hours
    pmin = sum(int(p.get("hours_min") or 0) for p in phases)
    pmax = sum(int(p.get("hours_max") or 0) for p in phases)
    if pmax <= 0:
        return hours
    hours = dict(hours)
    hours["mvp_min"] = pmin
    hours["mvp_max"] = pmax
    if hours.get("prod_max", 0) < pmax:
        hours["prod_min"] = max(pmax, int(hours.get("prod_min") or 0))
        hours["prod_max"] = max(int(hours["prod_max"] or 0), int(math.ceil(pmax * 2.5)))
    return hours


def _normalize_platform_fit(raw: object) -> str:
    s = _clip(raw, 32).lower().replace("-", "_")
    alias = {
        "win": "windows",
        "win32": "windows",
        "mac": "mac_only",
        "macos": "mac_only",
        "browser": "web",
        "chrome": "extension",
        "crossplatform": "cross_platform",
        "跨平台": "cross_platform",
    }
    s = alias.get(s, s)
    if s in _PLATFORM_FIT_VALUES:
        return s
    if "windows" in s:
        return "windows"
    if "mac" in s:
        return "mac_only"
    if "extension" in s or "chrome" in s:
        return "extension"
    if "web" in s:
        return "web"
    if "cli" in s or "terminal" in s:
        return "cli"
    return "unknown"


def _normalize_competitors(raw: object, *, max_items: int = 6) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = _clip(item.get("name"), 120)
        if not name:
            continue
        out.append({"name": name, "note": _clip(item.get("note"), 400)})
        if len(out) >= max_items:
            break
    return out


def _normalize_market_position(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    saturation = _clip(raw.get("market_saturation"), 16)
    if saturation not in _MARKET_SATURATION_VALUES:
        for v in _MARKET_SATURATION_VALUES:
            if v in saturation:
                saturation = v
                break
        else:
            saturation = "竞争适中"
    return {
        "target_user": _clip(raw.get("target_user"), 400),
        "vertical_niche": _clip(raw.get("vertical_niche"), 400),
        "market_saturation": saturation,
        "competitors": _normalize_competitors(raw.get("competitors")),
        "differentiation": _clip(raw.get("differentiation"), 800),
        "monetization_hypothesis": _clip(raw.get("monetization_hypothesis"), 800),
    }


def _normalize_open_source(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"has_support": False, "projects": [], "gaps": ""}
    projects: list[dict[str, str]] = []
    for p in raw.get("projects") or []:
        if not isinstance(p, dict):
            continue
        name = _clip(p.get("name"), 120)
        if not name:
            continue
        projects.append(
            {
                "name": name,
                "url": _clip(p.get("url"), 512),
                "role": _clip(p.get("role"), 200),
            }
        )
        if len(projects) >= 8:
            break
    return {
        "has_support": bool(raw.get("has_support")) or bool(projects),
        "projects": projects,
        "gaps": _clip(raw.get("gaps"), 800),
    }


def monetization_hypothesis_is_substantive(hypothesis: object) -> bool:
    """排除过短或 compat 填写的泛化变现假设。"""
    h = _clip(hypothesis, 900)
    if len(h) < 16:
        return False
    if h in _GENERIC_MONETIZATION_HYPOTHESES:
        return False
    if h.startswith("围绕「") and "垂直场景" in h and len(h) < 48:
        return False
    return True


def boost_worth_from_pricing_signals(
    worth: int,
    data: dict[str, Any],
    *,
    extra_text: str = "",
) -> int:
    """片段/字段中含可核对定价或营收线索时，价值分 +0~2（上限 10）。"""
    mp = data.get("market_position") if isinstance(data.get("market_position"), dict) else {}
    blob = " ".join(
        [
            str(data.get("value_summary") or ""),
            str(mp.get("monetization_hypothesis") or ""),
            str(extra_text or ""),
        ]
    )
    boost = 0
    if _PRICING_SIGNAL_RE.search(blob):
        boost += 1
    if re.search(r"\$\s?\d+", blob) or re.search(r"\d+\s*/\s*(?:月|mo)", blob, re.I):
        boost += 1
    return max(1, min(10, int(worth) + boost))


def normalize_replication_analysis(
    raw: object,
    *,
    pricing_context: str = "",
) -> dict[str, Any] | None:
    """将 LLM 输出规整为可入库的分析对象；无法识别时返回 None。"""
    if not isinstance(raw, dict):
        return None
    verdict = _clip(raw.get("verdict"), 32)
    if verdict in _VERDICT_ALIASES:
        verdict = _VERDICT_ALIASES[verdict]
    if verdict not in _VERDICT_VALUES:
        for v in _VERDICT_VALUES:
            if v in verdict:
                verdict = v
                break
        else:
            for alias, canon in _VERDICT_ALIASES.items():
                if alias in verdict:
                    verdict = canon
                    break
            else:
                verdict = "观望"
    difficulty = _clip(raw.get("difficulty"), 8)
    if difficulty not in _DIFFICULTY_VALUES:
        difficulty = "中"
    worth = boost_worth_from_pricing_signals(
        _as_int(raw.get("worth_score"), default=5, lo=1, hi=10),
        raw if isinstance(raw, dict) else {},
        extra_text=pricing_context,
    )
    phases = _normalize_phases(raw.get("phases"))
    hours = _sync_hours_from_phases(phases, _normalize_hours_block(raw.get("estimated_hours")))
    plan = _as_str_list(raw.get("implementation_plan"), max_items=8, item_max=500)
    if not plan and raw.get("implementation_plan"):
        plan = [_clip(raw.get("implementation_plan"), 2000)]
    details = _as_str_list(raw.get("implementation_details"), max_items=10, item_max=500)
    ai_steps = _as_str_list(raw.get("ai_usage_steps"), max_items=8, item_max=400)
    return {
        "verdict": verdict,
        "worth_score": worth,
        "difficulty": difficulty,
        "estimated_hours": hours,
        "phases": phases,
        "team_shape": _clip(raw.get("team_shape"), 200),
        "assumptions": _clip(raw.get("assumptions"), 600),
        "platform_fit": _normalize_platform_fit(raw.get("platform_fit")),
        "tier_rationale": _clip(raw.get("tier_rationale"), 1200),
        "value_summary": _clip(raw.get("value_summary"), 1200),
        "market_position": _normalize_market_position(raw.get("market_position")),
        "ai_usage_steps": ai_steps,
        "tech_stack": _as_str_list(raw.get("tech_stack"), max_items=12, item_max=80),
        "implementation_plan": plan,
        "implementation_details": details,
        "open_source": _normalize_open_source(raw.get("open_source")),
        "risks": _as_str_list(raw.get("risks"), max_items=8, item_max=300),
    }


def parse_replication_analysis_json(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return normalize_replication_analysis(data)


def _phases_valid(phases: list[dict[str, Any]]) -> bool:
    if len(phases) < _MIN_PHASES:
        return False
    for p in phases:
        if len(_clip(p.get("name"), 200)) < 2:
            return False
        if _as_int(p.get("hours_max")) < 1:
            return False
        if len(_clip(p.get("deliverable"), 500)) < 8:
            return False
    return True


def _effort_hours_ok(data: dict[str, Any]) -> bool:
    hours = data.get("estimated_hours") or {}
    return _as_int(hours.get("mvp_max")) >= _MIN_MVP_HOURS


def describe_replication_analysis_reject(data: dict | None) -> str:
    """未通过 validate_replication_analysis_for_publish 时的分项原因（供同步诊断）。"""
    if not data:
        return "对象缺失或无法解析"
    parts: list[str] = []
    verdict = _clip(data.get("verdict"), 32)
    if verdict not in _VERDICT_VALUES and verdict not in _VERDICT_ALIASES:
        parts.append(f"verdict无效({verdict!r})")
    worth = _as_int(data.get("worth_score"), default=0, lo=0, hi=10)
    if worth < 1:
        parts.append("worth_score无效")
    vs = _clip(data.get("value_summary"), 2000)
    if len(vs) < 16:
        parts.append(f"value_summary={len(vs)}字(需≥16)")
    tr = _clip(data.get("tier_rationale"), 2000)
    if len(tr) < 12:
        parts.append(f"tier_rationale={len(tr)}字(需≥12)")
    mp = data.get("market_position")
    if not isinstance(mp, dict):
        parts.append("market_position缺失")
    else:
        if not monetization_hypothesis_is_substantive(mp.get("monetization_hypothesis")):
            parts.append("monetization_hypothesis过短或非实质(需≥16字且非泛化兜底)")
        if _clip(mp.get("market_saturation"), 32) not in _MARKET_SATURATION_VALUES:
            parts.append("market_saturation无效")
    phases = data.get("phases") or []
    if not _phases_valid(phases):
        parts.append(f"phases不足(需≥{_MIN_PHASES}条且含工时/交付物)")
    if not _effort_hours_ok(data):
        hours = data.get("estimated_hours") or {}
        parts.append(f"mvp_max={_as_int(hours.get('mvp_max'))}(需≥{_MIN_MVP_HOURS})")
    risks = data.get("risks") or []
    if len([x for x in risks if str(x).strip()]) < 1:
        parts.append("risks为空(需≥1条)")
    return "；".join(parts) if parts else "未分类"


def validate_replication_analysis_for_publish(data: dict | None) -> bool:
    """应用稿发布：变现评估 + 阶段化工时拆解均须达标。"""
    if not data:
        return False
    verdict = _clip(data.get("verdict"), 32)
    if verdict in _VERDICT_ALIASES:
        verdict = _VERDICT_ALIASES[verdict]
    if verdict not in _VERDICT_VALUES:
        return False
    if _as_int(data.get("worth_score"), default=0, lo=0, hi=10) < 1:
        return False
    if len(_clip(data.get("value_summary"), 2000)) < 16:
        return False
    if len(_clip(data.get("tier_rationale"), 2000)) < 12:
        return False
    mp = data.get("market_position")
    if not isinstance(mp, dict):
        return False
    if not monetization_hypothesis_is_substantive(mp.get("monetization_hypothesis")):
        return False
    if _clip(mp.get("market_saturation"), 32) not in _MARKET_SATURATION_VALUES:
        return False
    if not _phases_valid(data.get("phases") or []):
        return False
    if not _effort_hours_ok(data):
        return False
    risks = data.get("risks") or []
    if len([x for x in risks if str(x).strip()]) < 1:
        return False
    return True


def article_value_score_from_json(raw: str | None) -> int:
    repl = parse_replication_analysis_json(raw)
    if not repl:
        return 0
    return _as_int(repl.get("worth_score"), default=0, lo=0, hi=10)


def _format_hours_range(lo: object, hi: object) -> str:
    a, b = _as_int(lo), _as_int(hi)
    if a <= 0 and b <= 0:
        return "未估算"
    if a <= 0:
        return f"约 {b} 小时"
    if b <= 0 or b == a:
        return f"约 {a} 小时"
    return f"约 {a}–{b} 小时"


def mvp_weeks_label(hours_max: int, *, hours_per_week: int = 20) -> str | None:
    if hours_max < _MIN_MVP_HOURS:
        return None
    lo = max(1, int(math.ceil(hours_max / hours_per_week)))
    return f"约 {lo} 周（按每周 {hours_per_week}h）"


def effort_phases_summary(phases: list[dict[str, Any]], *, max_parts: int = 4) -> str:
    parts: list[str] = []
    for p in phases[:max_parts]:
        name = _clip(p.get("name"), 40)
        hmax = _as_int(p.get("hours_max"))
        if not name:
            continue
        parts.append(f"{name}({hmax}h)" if hmax else name)
    return " → ".join(parts)


def card_value_hook(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    mp = data.get("market_position") or {}
    hook = _clip(mp.get("monetization_hypothesis"), 220)
    if hook:
        return hook
    return _clip(data.get("value_summary"), 220)


def replication_analysis_public_view(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    hours = data.get("estimated_hours") or {}
    mvp = _format_hours_range(hours.get("mvp_min"), hours.get("mvp_max"))
    prod = _format_hours_range(hours.get("prod_min"), hours.get("prod_max"))
    phases = data.get("phases") or []
    mvp_max = _as_int(hours.get("mvp_max"))
    return {
        **data,
        "estimated_hours_label": {"mvp": mvp, "production": prod},
        "effort_summary": effort_phases_summary(phases),
        "mvp_weeks_label": mvp_weeks_label(mvp_max) or "",
    }


def estimated_hours_mvp_label(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    hours = data.get("estimated_hours") or {}
    label = _format_hours_range(hours.get("mvp_min"), hours.get("mvp_max"))
    return label if label != "未估算" else None


def article_value_filter_eligible(
    data: dict[str, Any] | None,
    *,
    min_worth: int = _PROJECT_PICK_MIN_WORTH,
    require_high_value: bool = False,
) -> bool:
    """公开列表筛选：仅变现价值（分、结论、变现假设），不要求阶段化工时。"""
    if not data:
        return False
    worth = _as_int(data.get("worth_score"), default=0, lo=0, hi=10)
    if worth < int(min_worth):
        return False
    verdict = _clip(data.get("verdict"), 32)
    if verdict in _VERDICT_ALIASES:
        verdict = _VERDICT_ALIASES[verdict]
    if verdict == "不建议" or verdict not in _VERDICT_VALUES:
        return False
    if len(_clip(data.get("value_summary"), 2000)) < 16:
        return False
    mp = data.get("market_position")
    if not isinstance(mp, dict):
        return False
    if not monetization_hypothesis_is_substantive(mp.get("monetization_hypothesis")):
        return False
    if require_high_value:
        return verdict == "高价值" and worth >= _HIGH_VALUE_MIN_WORTH
    return True


def article_project_pick_eligible(
    data: dict[str, Any] | None,
    *,
    min_worth: int = _PROJECT_PICK_MIN_WORTH,
    require_high_value: bool = False,
) -> bool:
    """入库发布 / 严格选项目：变现 + 阶段化工时均达标。"""
    if not validate_replication_analysis_for_publish(data):
        return False
    return article_value_filter_eligible(
        data,
        min_worth=min_worth,
        require_high_value=require_high_value,
    )
