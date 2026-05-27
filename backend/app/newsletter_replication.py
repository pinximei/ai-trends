"""每日摘要 / 推送：与公开站一致的复刻评估准入规则。"""
from __future__ import annotations

from typing import Any

from .application.article_public import _article_replication_complete
from .domain.replication_analysis import parse_replication_analysis_json, replication_analysis_public_view

DEEP_REPLICATION_MIN_WORTH = 7
DEEP_REPLICATION_TIERS = frozenset({"S", "A"})


def article_deep_replication(a: Any, *, min_worth: int = DEEP_REPLICATION_MIN_WORTH) -> bool:
    return _article_replication_complete(a, min_worth=min_worth)


def article_replication_public(a: Any) -> dict[str, Any] | None:
    raw = parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if not raw:
        return None
    return replication_analysis_public_view(raw)


def split_deep_replicable_apps(articles: list[Any]) -> tuple[list[Any], list[Any]]:
    """完整评估且 worth≥7 的 S/A 档 → 高可复刻；其余进常规应用栏。"""
    rep: list[Any] = []
    rest: list[Any] = []
    for a in articles:
        tier = (getattr(a, "replication_tier", None) or "").strip().upper()
        if article_deep_replication(a) and tier in DEEP_REPLICATION_TIERS:
            rep.append(a)
        else:
            rest.append(a)

    def _rank(x: Any) -> tuple[int, float, int]:
        tier = (getattr(x, "replication_tier", None) or "").strip().upper()
        tier_rank = 0 if tier == "S" else 1
        heat = -float(getattr(x, "heat_score", None) or 0.0)
        return (tier_rank, heat, -int(getattr(x, "id", 0) or 0))

    rep.sort(key=_rank)
    return rep, rest
