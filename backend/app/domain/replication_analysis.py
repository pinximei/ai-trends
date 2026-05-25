"""应用泳道：LLM 复刻可行性结构化分析（入库 JSON + 公开 API）。"""
from __future__ import annotations

import json
from typing import Any

FEED_CARD_TAB_REPLICATION = "复刻评估"

_VERDICT_VALUES = frozenset({"值得复刻", "观望", "不建议"})
_DIFFICULTY_VALUES = frozenset({"低", "中", "高"})


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


def normalize_replication_analysis(raw: object) -> dict[str, Any] | None:
    """将 LLM 输出规整为可入库的复刻分析对象；无法识别时返回 None。"""
    if not isinstance(raw, dict):
        return None
    verdict = _clip(raw.get("verdict"), 32)
    if verdict not in _VERDICT_VALUES:
        for v in _VERDICT_VALUES:
            if v in verdict:
                verdict = v
                break
        else:
            verdict = "观望"
    difficulty = _clip(raw.get("difficulty"), 8)
    if difficulty not in _DIFFICULTY_VALUES:
        difficulty = "中"
    worth = _as_int(raw.get("worth_score"), default=5, lo=1, hi=10)
    plan = _as_str_list(raw.get("implementation_plan"), max_items=8, item_max=500)
    if not plan and raw.get("implementation_plan"):
        plan = [_clip(raw.get("implementation_plan"), 2000)]
    details = _as_str_list(raw.get("implementation_details"), max_items=10, item_max=500)
    return {
        "verdict": verdict,
        "worth_score": worth,
        "difficulty": difficulty,
        "estimated_hours": _normalize_hours_block(raw.get("estimated_hours")),
        "tier_rationale": _clip(raw.get("tier_rationale"), 1200),
        "value_summary": _clip(raw.get("value_summary"), 1200),
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


def validate_replication_analysis_for_publish(data: dict | None) -> bool:
    """应用稿：复刻分析须含结论、难度、工时与可执行方案要点。"""
    if not data:
        return False
    if len(_clip(data.get("tier_rationale"), 2000)) < 20:
        return False
    if len(_clip(data.get("value_summary"), 2000)) < 16:
        return False
    hours = data.get("estimated_hours") or {}
    if not isinstance(hours, dict):
        return False
    if _as_int(hours.get("mvp_max")) < 8 and _as_int(hours.get("prod_max")) < 40:
        return False
    plan = data.get("implementation_plan") or []
    details = data.get("implementation_details") or []
    if not plan and not details:
        return False
    stack = data.get("tech_stack") or []
    if not stack:
        return False
    return True


def replication_analysis_public_view(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not data:
        return None
    hours = data.get("estimated_hours") or {}
    mvp = _format_hours_range(hours.get("mvp_min"), hours.get("mvp_max"))
    prod = _format_hours_range(hours.get("prod_min"), hours.get("prod_max"))
    return {
        **data,
        "estimated_hours_label": {"mvp": mvp, "production": prod},
    }


def _format_hours_range(lo: object, hi: object) -> str:
    a, b = _as_int(lo), _as_int(hi)
    if a <= 0 and b <= 0:
        return "未估算"
    if a <= 0:
        return f"约 {b} 小时"
    if b <= 0 or b == a:
        return f"约 {a} 小时"
    return f"约 {a}–{b} 小时"


def estimated_hours_mvp_label(data: dict[str, Any] | None) -> str | None:
    if not data:
        return None
    hours = data.get("estimated_hours") or {}
    label = _format_hours_range(hours.get("mvp_min"), hours.get("mvp_max"))
    return label if label != "未估算" else None
