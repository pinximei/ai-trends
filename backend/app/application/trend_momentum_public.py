"""行业趋势：识别持续升温的软件、开源项目、资讯热点与话题赛道。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..product_models import Article
from .article_public import _admin_source_label_by_key, _article_matches_public_feed, _feed_card_from_article
from .home_public import _industry_article_ids

MOMENTUM_MIN_HEAT = 52.0
MOMENTUM_SCAN_LIMIT = 400

# 行业/技术话题赛道（不含复刻档位、变现运营、泛化产品类标签）
TOPIC_INDUSTRY_TRACK_LABELS: frozenset[str] = frozenset(
    {
        "Agent",
        "多模态",
        "模型层(谨慎)",
        "数据算力",
        "安全合规",
        "政策市场",
    }
)
def _days_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


def compute_article_momentum(a: Article, *, now: datetime | None = None) -> tuple[float, list[str]]:
    """综合热度、近期同步与 GitHub 增速，估算「持续火热」动量分。"""
    now = now or datetime.utcnow()
    heat = float(getattr(a, "heat_score", 0.0) or 0.0)
    if heat < MOMENTUM_MIN_HEAT:
        return 0.0, []

    fresh = art.article_freshness_for_row(a) or a.published_at or a.updated_at or now
    published = a.published_at or fresh
    days_upd = _days_between(now, fresh)
    days_pub = _days_between(now, published)

    update_boost = 1.0 if days_upd <= 2 else (0.85 if days_upd <= 5 else (0.6 if days_upd <= 10 else 0.35))
    sustained_boost = 1.2 if days_pub >= 4 and days_upd <= 6 and heat >= 72 else 1.0
    stars_today = int(getattr(a, "engagement_stars_today", None) or 0)
    star_boost = 1.0 + min(stars_today / 400.0, 0.55)

    score = heat * update_boost * sustained_boost * star_boost
    tags: list[str] = []
    if days_pub >= 4 and days_upd <= 6 and heat >= 68:
        tags.append("持续升温")
    if stars_today >= 80:
        tags.append("今日飙星")
    if days_upd <= 2 and heat >= 85:
        tags.append("仍在发酵")
    if not tags:
        tags.append("高热度")
    return round(score, 2), tags


def topic_track_labels_for_article(a: Article) -> list[str]:
    """从文章分类提取可聚合的行业话题（白名单），排除高可复刻/变现等运营标签。"""
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


def _track_for_article(a: Article) -> str:
    sk = art.admin_source_key(a.third_party_source)
    if sk == "github":
        return "oss"
    if _article_matches_public_feed(a, "apps"):
        return "software"
    return "hotspot"


def _enrich_card(card: dict, *, momentum_score: float, momentum_tags: list[str], days_on_radar: int) -> dict:
    out = dict(card)
    out["momentum_score"] = momentum_score
    out["momentum_tags"] = momentum_tags
    out["days_on_radar"] = days_on_radar
    return out


def get_trend_momentum_dashboard(
    db: Session,
    *,
    industry_slug: str = "ai",
    period_days: int = 30,
    limit_per_track: int = 8,
    topic_limit: int = 10,
) -> dict:
    """返回分赛道持续升温榜 + 话题聚合。"""
    period = max(7, min(int(period_days), 90))
    lim = max(3, min(int(limit_per_track), 20))
    topic_lim = max(4, min(int(topic_limit), 20))
    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    empty = {
        "period_days": period,
        "software": [],
        "oss": [],
        "hotspots": [],
        "topics": [],
        "scoring_note": (
            "momentum = heat_score × 近期同步加权 × 持续热度加成 × GitHub 今日 star 增速；"
            "用于发现仍在被连接器刷新、跨日保持高热的条目"
        ),
    }
    if not industry_ids:
        return empty

    now = datetime.utcnow()
    since = now - timedelta(days=period)
    fe = art.article_freshness_sql_expr()
    base = and_(
        Article.industry_id.in_(industry_ids),
        Article.status == "published",
        fe.isnot(None),
        fe >= since,
        Article.heat_score >= MOMENTUM_MIN_HEAT,
    )

    rows = list(
        db.scalars(
            select(Article)
            .where(base)
            .order_by(desc(Article.heat_score), desc(fe), desc(Article.id))
            .limit(MOMENTUM_SCAN_LIMIT)
        ).all()
    )

    label_by_key = _admin_source_label_by_key(db)
    scored: list[tuple[float, Article, list[str]]] = []
    topic_acc: dict[str, dict] = defaultdict(
        lambda: {"momentum_sum": 0.0, "heat_sum": 0.0, "count": 0, "titles": []}
    )

    for a in rows:
        mom, tags = compute_article_momentum(a, now=now)
        if mom <= 0:
            continue
        scored.append((mom, a, tags))
        for label in topic_track_labels_for_article(a):
            acc = topic_acc[label]
            acc["momentum_sum"] += mom
            acc["heat_sum"] += float(a.heat_score or 0)
            acc["count"] += 1
            if len(acc["titles"]) < 3:
                acc["titles"].append((a.title or "")[:120])

    scored.sort(key=lambda x: (-x[0], -float(x[1].heat_score or 0)))

    buckets: dict[str, list[dict]] = {"software": [], "oss": [], "hotspot": []}
    for mom, a, tags in scored:
        track = _track_for_article(a)
        if len(buckets[track]) >= lim:
            continue
        fresh = art.article_freshness_for_row(a) or a.published_at or now
        published = a.published_at or fresh
        days_on = int(_days_between(now, published))
        card = _enrich_card(
            _feed_card_from_article(a, label_by_key=label_by_key),
            momentum_score=mom,
            momentum_tags=tags,
            days_on_radar=days_on,
        )
        buckets[track].append(card)

    topics_sorted = sorted(
        topic_acc.items(),
        key=lambda kv: (-kv[1]["momentum_sum"], -kv[1]["count"]),
    )[:topic_lim]
    topics = []
    for label, acc in topics_sorted:
        if acc["count"] < 2:
            continue
        topics.append(
            {
                "label": label,
                "article_count": int(acc["count"]),
                "momentum_score": round(acc["momentum_sum"], 1),
                "heat_avg": round(acc["heat_sum"] / acc["count"], 1),
                "sample_titles": list(acc["titles"]),
            }
        )

    return {
        "period_days": period,
        "software": buckets["software"],
        "oss": buckets["oss"],
        "hotspots": buckets["hotspot"],
        "topics": topics,
        "scoring_note": empty["scoring_note"],
    }
