"""每日摘要 / 推送：与公开站一致的变现价值准入规则。"""
from __future__ import annotations

from typing import Any

from .application.article_public import _article_listing_product_gate, _article_replication_complete
from .domain.replication_analysis import parse_replication_analysis_json, replication_analysis_public_view

VALUE_ASSESSED_MIN_WORTH = 7
HIGH_VALUE_DIGEST_MIN_WORTH = 8


def article_value_assessed(a: Any, *, min_worth: int = VALUE_ASSESSED_MIN_WORTH) -> bool:
    repl = parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if not _article_listing_product_gate(a, repl):
        return False
    return _article_replication_complete(a, min_worth=min_worth, require_high_value=False)


def article_high_value_for_digest(a: Any) -> bool:
    repl = parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if not _article_listing_product_gate(a, repl):
        return False
    return _article_replication_complete(
        a,
        min_worth=HIGH_VALUE_DIGEST_MIN_WORTH,
        require_high_value=True,
    )


def article_replication_public(a: Any) -> dict[str, Any] | None:
    raw = parse_replication_analysis_json(getattr(a, "replication_analysis_json", None))
    if not raw:
        return None
    return replication_analysis_public_view(raw)


def split_deep_replicable_apps(articles: list[Any]) -> tuple[list[Any], list[Any]]:
    """worth≥8 且 verdict=高价值 → 高价值栏；其余进常规应用栏。"""
    rep: list[Any] = []
    rest: list[Any] = []
    for a in articles:
        if article_high_value_for_digest(a):
            rep.append(a)
        else:
            rest.append(a)

    def _rank(x: Any) -> tuple[int, float, int]:
        repl = article_replication_public(x) or {}
        worth = -int(repl.get("worth_score") or 0)
        heat = -float(getattr(x, "heat_score", None) or 0.0)
        return (worth, heat, -int(getattr(x, "id", 0) or 0))

    rep.sort(key=_rank)
    return rep, rest
