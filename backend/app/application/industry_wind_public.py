"""行业风向：从近 30 日高热文章由 AI 归纳可读热点（非固定赛道）。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from ..domain import articles as art
from ..llm_settings_service import resolve_llm_http_config
from ..llm_service import _extract_json_object, chat_completion
from ..product_models import Article, ProductSetting
from .article_public import _article_matches_public_feed
from .home_public import _industry_article_ids

MOMENTUM_MIN_HEAT = 48.0
SCAN_LIMIT = 120
LLM_CANDIDATE_LIMIT = 55
MAX_TRENDS = 6
MIN_TRENDS = 3
CACHE_KEY = "industry_wind_cache_v6"
CACHE_TTL_SECONDS = 24 * 3600
CACHE_STALE_MAX_SECONDS = 7 * 24 * 3600
WIND_LLM_MIN_INTERVAL_SECONDS = 24 * 3600
WIND_HALF_PERIOD_DAYS = 15
WIND_TOTAL_DAYS = 30
WIND_COMPARE_MODE = "period_half"

# 运营/空泛大类：不参与风向聚类，也不作为 LLM 输出
_OPS_OR_ABSTRACT_LABELS: frozenset[str] = frozenset(
    {
        "高价值复刻",
        "已验证变现",
        "变现案例",
        "其他",
        "政策市场",
        "安全合规",
        "数据算力",
        "模型层(谨慎)",
    }
)

_TITLE_STOP: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "your",
        "you",
        "are",
        "was",
        "has",
        "have",
        "new",
        "how",
        "why",
        "what",
        "when",
        "can",
        "will",
        "not",
        "all",
        "our",
        "its",
        "into",
        "out",
        "app",
        "api",
        "tool",
        "tools",
        "using",
        "use",
        "based",
        "open",
        "source",
        "github",
        "show",
        "hn",
        "ai",
        "llm",
        "gpt",
        "发布",
        "更新",
        "推出",
        "开源",
        "工具",
        "应用",
        "产品",
        "平台",
        "服务",
        "技术",
        "方案",
        "系统",
        "模型",
        "最新",
        "今日",
        "本周",
        "一个",
        "如何",
        "什么",
        "可以",
        "已经",
        "进行",
        "通过",
        "基于",
        "支持",
        "实现",
        "提供",
        "包括",
        "相关",
        "更多",
        "首次",
        "正式",
    }
)


def _days_between(later: datetime, earlier: datetime) -> float:
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


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


def _wind_article_period_dt(a: Article, *, now: datetime) -> datetime:
    """环比与按日曲线用发布时间，不用连接器刷新后的 updated_at。"""
    if a.published_at is not None:
        return a.published_at
    return art.article_freshness_for_row(a) or a.updated_at or now


def _growth_pct(current: int, previous: int) -> float | None:
    if previous <= 0:
        return None
    if current <= 0:
        return round(-100.0, 1)
    return round((current - previous) / previous * 100.0, 1)


def _day_keys_utc(*, end: datetime, days: int) -> list[str]:
    """``days`` 个 UTC 自然日（不含 end 当日），从旧到新。"""
    end_day = end.replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = end_day - timedelta(days=days)
    out: list[str] = []
    d = start_day
    while d < end_day:
        out.append(d.date().isoformat())
        d += timedelta(days=1)
    return out


def _daily_series_for_article_ids(
    ids: list[int],
    articles_by_id: dict[int, Article],
    *,
    now: datetime,
    window_end_offset_days: int,
    days: int = WIND_HALF_PERIOD_DAYS,
) -> list[dict[str, int | str]]:
    """window_end_offset_days=0 → 近半窗；=WIND_HALF_PERIOD_DAYS → 再前一半。"""
    window_end = now - timedelta(days=window_end_offset_days)
    window_start = window_end - timedelta(days=days)
    day_keys = _day_keys_utc(end=window_end, days=days)
    counts = {k: 0 for k in day_keys}
    for aid in ids:
        a = articles_by_id.get(aid)
        if a is None:
            continue
        period_dt = _wind_article_period_dt(a, now=now)
        if period_dt < window_start or period_dt >= window_end:
            continue
        dk = period_dt.replace(hour=0, minute=0, second=0, microsecond=0).date().isoformat()
        if dk in counts:
            counts[dk] += 1
    return [{"day": k, "count": counts[k]} for k in day_keys]


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


def _article_snippet(a: Article) -> str:
    for field in ("card_highlights", "card_description", "summary"):
        raw = str(getattr(a, field, None) or "").strip()
        if raw:
            return raw.replace("\n", " ")[:140]
    return ""


def _article_source_label(a: Article) -> str:
    raw = str(getattr(a, "third_party_source", None) or "").strip()
    if " / " in raw:
        return raw.split(" / ", 1)[0].strip() or raw
    return raw or "unknown"


def _is_ops_facet_article(a: Article) -> bool:
    cats = art.display_categories_for_article(getattr(a, "ai_categories_json", None))
    if cats and cats[0] in _OPS_OR_ABSTRACT_LABELS:
        return True
    for raw in art.parse_category_labels_json(getattr(a, "ai_categories_json", None)):
        canon = art.map_raw_label_to_canonical(raw)
        if canon in _OPS_OR_ABSTRACT_LABELS:
            return True
    return False


def _collect_hot_articles(
    db: Session,
    *,
    industry_ids: list[int],
    lookback_days: int,
    now: datetime,
) -> list[tuple[Article, float, datetime]]:
    lookback = max(WIND_TOTAL_DAYS, min(int(lookback_days), 90))
    prior_since = now - timedelta(days=lookback)
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
    scored: list[tuple[Article, float, datetime]] = []
    for a in rows:
        if _is_ops_facet_article(a):
            continue
        mom = compute_article_momentum(a, now=now)
        if mom <= 0:
            continue
        fresh = art.article_freshness_for_row(a) or a.published_at or now
        scored.append((a, mom, fresh))
    scored.sort(key=lambda x: (-x[1], -float(x[0].heat_score or 0), -x[0].id))
    return scored


def _load_cache(
    db: Session,
    *,
    industry_slug: str,
    recent_days: int,
    max_age_seconds: int | None = CACHE_TTL_SECONDS,
) -> dict[str, Any] | None:
    row = db.get(ProductSetting, CACHE_KEY)
    if not row or not isinstance(row.value_json, dict):
        return None
    blob = row.value_json
    if blob.get("compare_mode") != WIND_COMPARE_MODE:
        return None
    if blob.get("industry_slug") != industry_slug or int(blob.get("recent_days") or 0) != recent_days:
        return None
    gen = blob.get("generated_at")
    if not gen:
        return None
    try:
        ts = datetime.fromisoformat(str(gen).replace("Z", ""))
    except ValueError:
        return None
    age = (datetime.utcnow() - ts).total_seconds()
    if max_age_seconds is not None and age > max_age_seconds:
        return None
    industries = blob.get("industries")
    if not isinstance(industries, list) or not industries:
        return None
    if not any(
        isinstance(r, dict) and str(r.get("headline") or r.get("label") or "").strip()
        for r in industries
    ):
        return None
    period_label = f"近{WIND_HALF_PERIOD_DAYS}日 vs 前{WIND_HALF_PERIOD_DAYS}日"
    source = str(blob.get("source") or "cache")
    if max_age_seconds is not None and age > CACHE_TTL_SECONDS:
        source = "stale_cache"
    return {
        "recent_days": recent_days,
        "compare_mode": WIND_COMPARE_MODE,
        "period_label": period_label,
        "industries": industries,
        "note": str(blob.get("note") or ""),
        "source": source,
        "generated_at": gen,
    }


def _save_cache(
    db: Session,
    *,
    industry_slug: str,
    recent_days: int,
    payload: dict[str, Any],
) -> None:
    row = db.get(ProductSetting, CACHE_KEY)
    if not row:
        row = ProductSetting(key=CACHE_KEY, value_json={})
        db.add(row)
    row.value_json = {
        "industry_slug": industry_slug,
        "recent_days": recent_days,
        "compare_mode": payload.get("compare_mode") or WIND_COMPARE_MODE,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "industries": payload.get("industries") or [],
        "note": payload.get("note") or "",
        "source": payload.get("source") or "llm",
    }
    db.commit()


def _build_llm_user_payload(candidates: list[tuple[Article, float, datetime]], *, recent_days: int) -> str:
    lines = [
        f"时间窗口：近 {WIND_HALF_PERIOD_DAYS} 天 vs 再前 {WIND_HALF_PERIOD_DAYS} 天（共 {WIND_TOTAL_DAYS} 日，环比）",
        "下列为高热文章，请归纳 4～6 个读者能立刻理解的热点方向。",
        "要求：",
        "- headline 必须具体（产品名/场景/现象），禁止「政策市场」「安全合规」「数据算力」等空泛词",
        "- summary 一句话说明为何正在变热，可引用标题中的事实",
        "- 每篇 id 最多归属一个 trend",
        "- article_ids 至少 2 条（若整体文章不足可 1 条）",
        "",
        "文章列表：",
    ]
    for a, mom, fresh in candidates[:LLM_CANDIDATE_LIMIT]:
        title = (a.title or "").strip().replace("\n", " ")[:100]
        snip = _article_snippet(a)[:100]
        src = _article_source_label(a)
        feed = "apps" if _article_matches_public_feed(a, "apps") else "news"
        lines.append(f"- id={a.id} heat={a.heat_score:.0f} mom={mom:.0f} src={src} feed={feed} title={title}")
        if snip:
            lines.append(f"  摘要: {snip}")
    return "\n".join(lines)


def _parse_llm_trends(raw: str, valid_ids: set[int]) -> list[dict[str, Any]] | None:
    obj = _extract_json_object(raw)
    if not obj or not isinstance(obj.get("trends"), list):
        return None
    out: list[dict[str, Any]] = []
    used: set[int] = set()
    for item in obj["trends"]:
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline") or item.get("label") or "").strip()
        summary = str(item.get("summary") or item.get("why_hot") or "").strip()
        if not headline or len(headline) < 4:
            continue
        if headline in _OPS_OR_ABSTRACT_LABELS:
            continue
        ids_raw = item.get("article_ids") or item.get("ids") or []
        if not isinstance(ids_raw, list):
            continue
        ids: list[int] = []
        for x in ids_raw:
            try:
                i = int(x)
            except (TypeError, ValueError):
                continue
            if i in valid_ids and i not in used:
                ids.append(i)
                used.add(i)
        if not ids:
            continue
        signal = str(item.get("signal") or "稳定").strip()
        if signal not in ("升温", "稳定", "降温", "偏冷"):
            signal = "稳定"
        out.append(
            {
                "headline": headline[:40],
                "summary": summary[:200] if summary else f"近两周 {len(ids)} 篇相关高热讨论",
                "article_ids": ids,
                "signal_hint": signal,
            }
        )
        if len(out) >= MAX_TRENDS:
            break
    return out if len(out) >= 1 else None


def _generate_wind_llm(
    db: Session,
    candidates: list[tuple[Article, float, datetime]],
    *,
    recent_days: int,
    industry_slug: str,
) -> list[dict[str, Any]] | None:
    _base, key, _model = resolve_llm_http_config(db)
    if not (key or "").strip():
        return None
    valid_ids = {a.id for a, _, _ in candidates}
    system = (
        "你是 AI 行业情报主编。根据文章标题与摘要，归纳当下正在变热的具体方向。"
        "输出必须是 JSON 对象，字段 trends 为数组，每项含 headline、summary、article_ids、signal。"
        "headline 8～20 字，要让普通开发者一眼看懂在讨论什么；禁止空泛赛道名。"
    )
    user = _build_llm_user_payload(candidates, recent_days=recent_days)
    try:
        raw, _, _, _ = chat_completion(
            db,
            system=system,
            user=user,
            scenario="industry_wind",
            ref_type="industry",
            ref_id=industry_slug,
            response_json=True,
            max_tokens=1200,
        )
    except Exception:
        return None
    return _parse_llm_trends(raw, valid_ids)


def _title_tokens(title: str) -> list[str]:
    t = (title or "").strip()
    if not t:
        return []
    tokens: list[str] = []
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", t):
        w = m.group().lower()
        if w not in _TITLE_STOP and len(w) >= 3:
            tokens.append(w)
    for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", t):
        w = m.group()
        if w not in _TITLE_STOP:
            tokens.append(w)
    return tokens


def _headline_from_cluster(cluster: list[Article]) -> str:
    if not cluster:
        return "近期热点"
    seed_title = (cluster[0].title or "").strip()
    if len(seed_title) <= 22:
        return seed_title
    counts: dict[str, int] = {}
    for a in cluster:
        for tok in _title_tokens(a.title or ""):
            if len(tok) >= 4 or (len(tok) >= 2 and "\u4e00" <= tok[0] <= "\u9fff"):
                counts[tok] = counts.get(tok, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], -len(x[0])))
    if ranked:
        top = [w for w, c in ranked[:3] if c >= 2]
        if not top:
            top = [ranked[0][0]]
        name = " · ".join(top[:2])
        if len(name) >= 6:
            return name[:22]
    return seed_title[:22] + ("…" if len(seed_title) > 22 else "")


def _fallback_trends(candidates: list[tuple[Article, float, datetime]]) -> list[dict[str, Any]]:
    """无 LLM 时：按标题关键词重叠粗聚类，仍输出具体可读 headline。"""
    if not candidates:
        return []
    assigned: set[int] = set()
    trends: list[dict[str, Any]] = []
    for seed_a, _, _ in candidates:
        if seed_a.id in assigned:
            continue
        seed_tokens = set(_title_tokens(seed_a.title or ""))
        cluster: list[Article] = [seed_a]
        assigned.add(seed_a.id)
        for other_a, _, _ in candidates:
            if other_a.id in assigned:
                continue
            other_tokens = set(_title_tokens(other_a.title or ""))
            overlap = seed_tokens & other_tokens
            strong = [t for t in overlap if len(t) >= 4 or (len(t) >= 2 and "\u4e00" <= t[0] <= "\u9fff")]
            if strong:
                cluster.append(other_a)
                assigned.add(other_a.id)
        if len(cluster) == 1 and len(trends) >= MIN_TRENDS:
            continue
        headline = _headline_from_cluster(cluster)
        trends.append(
            {
                "headline": headline,
                "summary": f"近{WIND_HALF_PERIOD_DAYS}日 {len(cluster)} 篇标题/主题相近的高热讨论",
                "article_ids": [a.id for a in cluster],
                "signal_hint": "稳定",
            }
        )
        if len(trends) >= MAX_TRENDS:
            break
    if not trends and candidates:
        a0 = candidates[0][0]
        trends.append(
            {
                "headline": _headline_from_cluster([a0]),
                "summary": "当前最热单条讨论",
                "article_ids": [a0.id],
                "signal_hint": "稳定",
            }
        )
    return trends


def _enrich_trends(
    trends: list[dict[str, Any]],
    *,
    articles_by_id: dict[int, Article],
    momentum_by_id: dict[int, float],
    now: datetime,
    recent_since: datetime,
    prior_since: datetime,
) -> list[dict]:
    industries: list[dict] = []
    for t in trends:
        ids = [int(i) for i in (t.get("article_ids") or []) if int(i) in articles_by_id]
        if not ids:
            continue
        recent_count = 0
        prior_count = 0
        raw_momentum = 0.0
        heat_sum = 0.0
        best_mom = 0.0
        best_article: Article | None = None
        for aid in ids:
            a = articles_by_id[aid]
            mom = momentum_by_id.get(aid, 0.0)
            period_dt = _wind_article_period_dt(a, now=now)
            if period_dt >= recent_since:
                recent_count += 1
                raw_momentum += mom
                heat_sum += float(a.heat_score or 0)
                if mom > best_mom:
                    best_mom = mom
                    best_article = a
            elif prior_since <= period_dt < recent_since:
                prior_count += 1
        growth = _growth_pct(recent_count, prior_count)
        signal = _wind_signal(growth_pct=growth, recent_count=recent_count, raw_momentum=raw_momentum)
        top = None
        if best_article is not None:
            feed = "apps" if _article_matches_public_feed(best_article, "apps") else "news"
            top = {"id": best_article.id, "title": (best_article.title or "")[:200], "feed_kind": feed}
        headline = str(t.get("headline") or "").strip()
        summary = str(t.get("summary") or "").strip()
        industries.append(
            {
                "label": headline,
                "headline": headline,
                "summary": summary,
                "rank": 0,
                "momentum_pct": 0,
                "raw_momentum": round(raw_momentum, 1),
                "article_count": recent_count,
                "prior_count": prior_count,
                "growth_pct": growth,
                "signal": signal,
                "heat_avg": round(heat_sum / recent_count, 1) if recent_count else 0.0,
                "top_pick": top,
                "series_this_week": _daily_series_for_article_ids(
                    ids, articles_by_id, now=now, window_end_offset_days=0
                ),
                "series_last_week": _daily_series_for_article_ids(
                    ids, articles_by_id, now=now, window_end_offset_days=WIND_HALF_PERIOD_DAYS
                ),
            }
        )

    max_raw = max((x["raw_momentum"] for x in industries), default=0.0) or 1.0
    for row in industries:
        raw = float(row["raw_momentum"])
        row["momentum_pct"] = round(100.0 * raw / max_raw) if raw > 0 else 0
    industries.sort(key=lambda x: (-x["momentum_pct"], -x["article_count"], x["headline"]))
    for i, row in enumerate(industries):
        row["rank"] = i + 1
    return industries


def get_industry_wind_overview(
    db: Session,
    *,
    industry_slug: str = "ai",
    recent_days: int = WIND_HALF_PERIOD_DAYS,
    allow_llm: bool = True,
) -> dict:
    """
    从高热文章归纳 4～6 个可读热点（LLM + 缓存；无 Key 时标题聚类回退）。

    默认 **近 15 日 vs 前 15 日**（共 30 日窗口）对比增幅与信号。

    ``allow_llm=False``：仅新鲜/过期缓存或标题聚类回退，供首页仪表盘快速路径，不阻塞 LLM。
    """
    recent = WIND_HALF_PERIOD_DAYS
    period_label = f"近{WIND_HALF_PERIOD_DAYS}日 vs 前{WIND_HALF_PERIOD_DAYS}日"
    note = (
        f"由近 {WIND_TOTAL_DAYS} 日高热文章 AI 归纳；环比为近{WIND_HALF_PERIOD_DAYS}日 vs "
        f"前{WIND_HALF_PERIOD_DAYS}日文章数；条越长表示近半窗综合热度越高"
    )
    empty = {
        "recent_days": recent,
        "compare_mode": WIND_COMPARE_MODE,
        "period_label": period_label,
        "industries": [],
        "note": note,
        "source": "empty",
    }

    cached = _load_cache(db, industry_slug=industry_slug, recent_days=recent, max_age_seconds=CACHE_TTL_SECONDS)
    if cached:
        return cached

    if not allow_llm:
        stale = _load_cache(
            db,
            industry_slug=industry_slug,
            recent_days=recent,
            max_age_seconds=CACHE_STALE_MAX_SECONDS,
        )
        if stale:
            stale_note = str(stale.get("note") or note)
            if "每日" not in stale_note:
                stale_note = f"{stale_note}（完整 AI 归纳每日自动更新一次）"
            return {**stale, "note": stale_note}
        # 公开 API 绝不现场调 LLM；有库内缓存即返回（含缺折线序列的旧格式，由前端估算图表）
        any_cached = _load_cache(
            db,
            industry_slug=industry_slug,
            recent_days=recent,
            max_age_seconds=None,
        )
        if any_cached:
            any_note = str(any_cached.get("note") or note)
            if "每日" not in any_note:
                any_note = f"{any_note}（完整 AI 归纳每日自动更新一次）"
            return {**any_cached, "note": any_note, "source": any_cached.get("source") or "cache"}

    if allow_llm:
        recent_llm = _load_cache(
            db,
            industry_slug=industry_slug,
            recent_days=recent,
            max_age_seconds=WIND_LLM_MIN_INTERVAL_SECONDS,
        )
        if recent_llm and str(recent_llm.get("source") or "") in ("llm", "fallback"):
            return recent_llm

    industry_ids = _industry_article_ids(db, industry_slug=industry_slug)
    if not industry_ids:
        return empty

    now = datetime.utcnow()
    recent_since = now - timedelta(days=WIND_HALF_PERIOD_DAYS)
    prior_since = now - timedelta(days=WIND_TOTAL_DAYS)
    this_week_start = recent_since.date().isoformat()
    last_week_start = prior_since.date().isoformat()
    candidates = _collect_hot_articles(
        db, industry_ids=industry_ids, lookback_days=WIND_TOTAL_DAYS, now=now
    )
    if len(candidates) < MIN_TRENDS:
        return {**empty, "note": f"近{WIND_TOTAL_DAYS}日高热文章不足，暂无法归纳风向"}

    articles_by_id = {a.id: a for a, _, _ in candidates}
    momentum_by_id = {a.id: mom for a, mom, _ in candidates}

    source = "fallback"
    raw_trends = None
    if allow_llm:
        raw_trends = _generate_wind_llm(db, candidates, recent_days=recent, industry_slug=industry_slug)
        source = "llm"
    if not raw_trends:
        raw_trends = _fallback_trends(candidates)
        if allow_llm and source == "llm":
            source = "fallback"

    industries = _enrich_trends(
        raw_trends,
        articles_by_id=articles_by_id,
        momentum_by_id=momentum_by_id,
        now=now,
        recent_since=recent_since,
        prior_since=prior_since,
    )
    if not industries:
        return {**empty, "note": "未能从当前文章归纳出清晰热点，请稍后再试"}

    payload = {
        "recent_days": recent,
        "compare_mode": WIND_COMPARE_MODE,
        "period_label": period_label,
        "this_week_start": this_week_start,
        "last_week_start": last_week_start,
        "industries": industries,
        "note": note if allow_llm else f"{note}（当前为快速聚类预览；完整 AI 归纳每日自动更新）",
        "source": source,
    }
    if allow_llm and source in ("llm", "fallback"):
        try:
            _save_cache(db, industry_slug=industry_slug, recent_days=recent, payload=payload)
        except Exception:
            db.rollback()
    return payload
