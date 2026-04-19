"""Rebuild hot snapshot (rule-based; optional LLM later)."""
from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .product_models import Article, HotSnapshot, Industry, LlmUsageLog, MetricDefinition, MetricPoint, ProductSetting


def get_hot_settings(db: Session) -> dict:
    row = db.get(ProductSetting, "hot")
    if row and row.value_json:
        return row.value_json
    return {"top_n_trends": 5, "top_n_articles": 10, "llm_model": os.getenv("AISOU_HOT_LLM_MODEL", "rule-based")}


def save_hot_settings(db: Session, data: dict) -> dict:
    row = db.get(ProductSetting, "hot")
    if not row:
        row = ProductSetting(key="hot", value_json={})
        db.add(row)
    merged = {**get_hot_settings(db), **data}
    row.value_json = merged
    row.updated_at = datetime.utcnow()
    db.commit()
    return merged


def rebuild_hot_snapshot(db: Session, industry_slug: str = "ai", trigger: str = "manual") -> HotSnapshot:
    ind = db.scalar(select(Industry).where(Industry.slug == industry_slug))
    if not ind:
        raise ValueError("industry not found")

    cfg = get_hot_settings(db)
    n_trend = int(cfg.get("top_n_trends", 5))
    n_art = int(cfg.get("top_n_articles", 10))
    model_label = str(cfg.get("llm_model") or os.getenv("AISOU_HOT_LLM_MODEL", "rule-based"))

    metrics = db.scalars(select(MetricDefinition).where(MetricDefinition.segment_id.isnot(None))).all()
    trend_items = []
    for m in metrics[:n_trend]:
        last_pt = db.scalar(
            select(MetricPoint)
            .where(MetricPoint.metric_id == m.id)
            .order_by(desc(MetricPoint.bucket_start))
            .limit(1)
        )
        seg_id = m.segment_id
        trend_items.append(
            {
                "metric_key": m.key,
                "metric_name": m.name,
                "segment_id": seg_id,
                "last_value": last_pt.value if last_pt else None,
            }
        )

    arts = db.scalars(
        select(Article)
        .where(Article.industry_id == ind.id, Article.status == "published")
        .order_by(desc(Article.published_at))
        .limit(n_art)
    ).all()
    article_ids = [a.id for a in arts]

    payload = {
        "trend_items": trend_items,
        "article_ids": article_ids,
        "model": model_label,
        "prompt_version": "v1-rule",
    }

    snap = HotSnapshot(
        industry_id=ind.id,
        generated_at=datetime.utcnow(),
        payload_json=payload,
        status="success",
        trigger=trigger,
    )
    db.add(snap)
    db.flush()

    db.add(
        LlmUsageLog(
            scenario="hot_rank_manual" if trigger == "manual" else "hot_rank_weekly",
            model=payload["model"],
            input_tokens=0,
            output_tokens=0,
            ref_type="hot_snapshot",
            ref_id=str(snap.id),
            success=True,
        )
    )
    db.commit()
    db.refresh(snap)
    return snap
