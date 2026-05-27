"""行业风向：近两周各技术赛道热度对比（首页专用，非文章列表页）。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..product_models import Article
from .article_public import _article_matches_public_feed
from .home_public import _industry_article_ids

MOMENTUM_MIN_HEAT = 48.0
SCAN_LIMIT = 500

TOPIC_INDUSTRY_TRACK_LABELS: tuple[str, ...] = (
    "Agent",
    "多模态",
    "模型层(谨慎)",
    "数据算力",
    "安全合规",
    "政策市场",
)


def _days_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


def topic_track_labels_for_article(a: Article) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in art.parse_category_labels_json(getattr(a, "ai_categories_json", None)):
        canon = art.map_raw_label_to_canonical(raw)
        if canon in TOPIC_INDUSTRY_TRACK_LABELS and canon not in seen:
            seen.add(canon)
            out.append(canon)
    if not out:
        cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
        label = cats[0] if cats else ""
        if label in TOPIC_INDUSTRY_TRACK_LABELS and label not in seen:
            out.append(label)
    return out


def compute_article_momentum(a: Article, *, now: datetime | None = None) -> float:
    now = now or datetime.utcnow()
    heat = float(getattr(a, "heat_score", 0.0) or 0.0)
    if heat < MOMENTUM_MIN_HEAT:
        return 0.0
    fresh = art.article_freshness_for_row(a) or a.published_at or a.updated_at or now
    published = a.published_at or fresh
    days_upd = _days_between(now, fresh)
    days_pub = _days_between(now, published)
    update_boost = 1.0 if days_upd <= 2 else (0.85 if days_upd <= 5 else (0.6 if days_upd <= 10 else 0.35))
    sustained_boost = 1.2 if days_pub >= 4 and days_upd <= 6 and heat >= 72 else 1.0
    stars_today = int(getattr(a, "engagement_stars_today", None) or 0)
    star_boost = 1.0 + min(stars_today / 400.0, 0.55)
    return round(heat * update_boost * sustained_boost * star_boost, 2)


def _growth_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round((current - previous) / previous * 100.0, 1)


def _wind_signal(*, growth_pct: float | None, recent_count: int, raw_momentum: float) -> str:
    if recent_count <= 0:
        return "偏冷"
    if growth_pct is not None and growth_pct >= 20:
        return "升温"
    if growth_pct is not None and growth_pct <= -15:
        return "降温"
    if raw_momentum >= 120:
        return "升温"
    return "稳定"


def get_industry_wind_overview(
    db: Session,
    *,
    industry_slug: str = "ai",
    recent_days: int = 14,
) -> dict:
    """
    固定 6 条行业赛道，返回可对比的动量条与环比，便于一眼看出「哪个方向在热」。

    与首页其它区块分工：
    - 今日精选 / 资讯墙 / 应用榜 → 具体文章
    - 入库曲线 → 全站活跃度
    - 本接口 → 行业赛道横向对比
    """
    recent = max(7, min(int(recent_days), 30))
    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    empty = {
        "recent_days": recent,
        "industries": [
            {
                "label": label,
                "rank": i + 1,
                "momentum_pct": 0,
                "raw_momentum": 0.0,
                "article_count": 0,
                "prior_count": 0,
                "growth_pct": None,
                "signal": "偏冷",
                "heat_avg": 0.0,
                "top_pick": None,
            }
            for i, label in enumerate(TOPIC_INDUSTRY_TRACK_LABELS)
        ],
        "note": "近两周入库文章按行业标签聚合；动量条越长表示该赛道当前综合热度越高",
    }
    if not industry_ids:
        return empty

    now = datetime.utcnow()
    recent_since = now - timedelta(days=recent)
    prior_since = now - timedelta(days=recent * 2)
    fe = art.article_freshness_sql_expr()
    base = and_(
        Article.industry_id.in_(industry_ids),
        Article.status == "published",
        fe.isnot(None),
        fe >= prior_since,
        Article.heat_score >= MOMENTUM_MIN_HEAT,
    )

    rows = list(
        db.scalars(
            select(Article)
            .where(base)
            .order_by(desc(Article.heat_score), desc(fe), desc(Article.id))
            .limit(SCAN_LIMIT)
        ).all()
    )

    acc: dict[str, dict] = {
        label: {
            "label": label,
            "recent_count": 0,
            "prior_count": 0,
            "raw_momentum": 0.0,
            "heat_sum": 0.0,
            "best_mom": 0.0,
            "best_article": None,
        }
        for label in TOPIC_INDUSTRY_TRACK_LABELS
    }

    for a in rows:
        labels = topic_track_labels_for_article(a)
        if not labels:
            continue
        fresh = art.article_freshness_for_row(a) or a.published_at or now
        mom = compute_article_momentum(a, now=now)
        in_recent = fresh >= recent_since
        in_prior = prior_since <= fresh < recent_since
        for label in labels:
            bucket = acc[label]
            if in_recent:
                bucket["recent_count"] += 1
                bucket["raw_momentum"] += mom
                bucket["heat_sum"] += float(a.heat_score or 0)
                if mom > bucket["best_mom"]:
                    bucket["best_mom"] = mom
                    bucket["best_article"] = a
            elif in_prior:
                bucket["prior_count"] += 1

    max_raw = max((b["raw_momentum"] for b in acc.values()), default=0.0) or 1.0
    industries: list[dict] = []
    for label in TOPIC_INDUSTRY_TRACK_LABELS:
        b = acc[label]
        rc = int(b["recent_count"])
        pc = int(b["prior_count"])
        raw = round(float(b["raw_momentum"]), 1)
        growth = _growth_pct(rc, pc)
        signal = _wind_signal(growth_pct=growth, recent_count=rc, raw_momentum=raw)
        top = None
        if b["best_article"] is not None:
            ba = b["best_article"]
            feed = "apps" if _article_matches_public_feed(ba, "apps") else "news"
            top = {"id": ba.id, "title": (ba.title or "")[:200], "feed_kind": feed}
        industries.append(
            {
                "label": label,
                "rank": 0,
                "momentum_pct": round(100.0 * raw / max_raw) if raw > 0 else 0,
                "raw_momentum": raw,
                "article_count": rc,
                "prior_count": pc,
                "growth_pct": growth,
                "signal": signal,
                "heat_avg": round(b["heat_sum"] / rc, 1) if rc else 0.0,
                "top_pick": top,
            }
        )

    industries.sort(key=lambda x: (-x["momentum_pct"], -x["article_count"], x["label"]))
    for i, row in enumerate(industries):
        row["rank"] = i + 1

    return {
        "recent_days": recent,
        "industries": industries,
        "note": empty["note"],
    }
