"""根据后台「数据源」配置（admin_source_configs）解析行业、板块，供同步/入库绑定 segment_id。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdminSourceConfig
from .product_models import Industry, MetricDefinition, Segment
from .scope_labels_util import get_scope_labels_from_source
from .taxonomy_from_sources import (
    MERGED_TAXONOMY_INDUSTRY_SLUG,
    parse_scope_label,
    slugify_segment,
)


def resolve_admin_source_key_to_segments(db: Session, source_key: str) -> list[dict[str, Any]]:
    """
    按数据源标识（与 admin_source_configs.source 一致，小写）解析出已落库的 Industry / Segment。
    会先执行一次 taxonomy 同步，确保 scope_labels 已生成对应行。
    多条 scope_labels 会去重到同一 segment_id 只保留一条。
    返回每项: industry_id, industry_slug, segment_id, segment_slug, label（原始领域字符串）
    """
    from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

    sync_product_taxonomy_from_admin_sources(db)
    key = (source_key or "").strip().lower()
    if not key:
        return []
    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
    if not src:
        return []

    out: list[dict[str, Any]] = []
    seen_seg: set[int] = set()
    for label in get_scope_labels_from_source(src):
        parsed = parse_scope_label(label)
        if not parsed:
            continue
        _ind_name, seg_name = parsed
        sslug = slugify_segment(MERGED_TAXONOMY_INDUSTRY_SLUG, seg_name)
        ind = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
        if not ind:
            continue
        seg = db.scalar(
            select(Segment).where(Segment.industry_id == ind.id, Segment.slug == sslug)
        ) or db.scalar(select(Segment).where(Segment.industry_id == ind.id, Segment.name == seg_name))
        if not seg:
            continue
        if seg.id in seen_seg:
            continue
        seen_seg.add(seg.id)
        out.append(
            {
                "industry_id": ind.id,
                "industry_slug": ind.slug,
                "segment_id": seg.id,
                "segment_slug": seg.slug,
                "label": label,
            }
        )
    return out


def first_metric_for_segment(db: Session, segment_id: int) -> MetricDefinition | None:
    """该板块下用于演示/占位同步的第一条指标（按 id）。"""
    return db.scalar(
        select(MetricDefinition).where(MetricDefinition.segment_id == segment_id).order_by(MetricDefinition.id).limit(1)
    )
