"""行业风向：首页快速路径不阻塞 LLM。"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.industry_wind_public import CACHE_KEY, get_industry_wind_overview
from backend.app.db import Base
from backend.app.product_models import Article, Industry, ProductSetting, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_hot_articles(db) -> None:
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="general", name="General")
    db.add(seg)
    db.flush()
    now = datetime.utcnow()
    for i in range(4):
        db.add(
            Article(
                industry_id=ind.id,
                segment_id=seg.id,
                title=f"OpenAI tool release wave {i} for developers",
                summary="x" * 40,
                status="published",
                third_party_source="hacker_news / front",
                feed_kind="news",
                heat_score=90.0 - i,
                ai_categories_json='["应用产品"]',
                published_at=now - timedelta(days=i + 1),
                updated_at=now - timedelta(hours=i + 1),
            )
        )
    db.commit()


def test_fast_path_skips_llm() -> None:
    db = _session()
    _seed_hot_articles(db)
    with patch("backend.app.application.industry_wind_public.chat_completion") as mock_llm:
        out = get_industry_wind_overview(db, industry_slug="ai", allow_llm=False)
    mock_llm.assert_not_called()
    assert out.get("source") in ("fallback", "empty")
    if out.get("industries"):
        assert len(out["industries"]) >= 1


def test_cache_without_chart_series_still_served() -> None:
    """旧缓存无 series_this_week 时公开 API 仍应返回热点列表（勿误判为空）。"""
    db = _session()
    db.add(
        ProductSetting(
            key=CACHE_KEY,
            value_json={
                "industry_slug": "ai",
                "recent_days": 15,
                "compare_mode": "period_half",
                "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
                "industries": [
                    {
                        "headline": "LLM tooling",
                        "summary": "dev tools heat",
                        "article_count": 3,
                        "prior_count": 1,
                    }
                ],
                "note": "cached",
                "source": "llm",
            },
        )
    )
    db.commit()
    with patch("backend.app.application.industry_wind_public.chat_completion") as mock_llm:
        out = get_industry_wind_overview(db, industry_slug="ai", allow_llm=False)
    mock_llm.assert_not_called()
    assert out["industries"][0]["headline"] == "LLM tooling"


def test_stale_cache_served_on_fast_path() -> None:
    db = _session()
    _seed_hot_articles(db)
    stale_payload = {
        "industry_slug": "ai",
        "recent_days": 15,
        "compare_mode": "period_half",
        "generated_at": (datetime.utcnow() - timedelta(hours=25)).isoformat(timespec="seconds"),
        "industries": [
            {
                "headline": "Cached headline",
                "summary": "from stale",
                "article_count": 2,
                "prior_count": 1,
                "series_this_week": [{"day": "2026-05-01", "count": 1}],
                "series_last_week": [{"day": "2026-04-30", "count": 0}],
            }
        ],
        "note": "cached",
        "source": "llm",
    }
    db.add(ProductSetting(key=CACHE_KEY, value_json=stale_payload))
    db.commit()
    with patch("backend.app.application.industry_wind_public.chat_completion") as mock_llm:
        out = get_industry_wind_overview(db, industry_slug="ai", allow_llm=False)
    mock_llm.assert_not_called()
    assert out.get("source") == "stale_cache"
    assert out["industries"][0]["headline"] == "Cached headline"
