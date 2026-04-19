"""从 admin 数据源的领域标签同步到 product 表：行业 + 板块合并为「单一根行业 + 主题板块」，避免行业/板块双层无限增生。"""
from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from .scope_labels_util import get_scope_labels_from_source

if TYPE_CHECKING:
    from .product_models import Industry

# 所有来自数据源的 scope 标签统一挂在此行业下；不再为「左半段」单独建 Industry。
MERGED_TAXONOMY_INDUSTRY_SLUG = "domains"
MERGED_TAXONOMY_INDUSTRY_NAME = "领域"


def _digest12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def slugify_industry(name: str) -> str:
    """行业 slug：优先可读拉丁字符；纯中文等则使用稳定短哈希。"""
    raw = (name or "").strip()
    if not raw:
        return "ind_unknown"
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    if len(ascii_part) >= 2:
        return ascii_part[:32]
    return f"i{_digest12(raw)}"[:32]


def slugify_segment(industry_slug: str, segment_name: str) -> str:
    """板块 slug：在同行业下稳定、唯一（跨中文名）。"""
    raw = f"{industry_slug}\n{segment_name.strip()}"
    base = re.sub(r"[^a-zA-Z0-9]+", "_", segment_name.strip()).strip("_").lower()
    if len(base) >= 2:
        return base[:64]
    return f"s{_digest12(raw)}"[:64]


def merge_scope_label_to_topic_name(label: str) -> str:
    """
    将「行业｜板块」或单行文案合并为 **一个** 展示用主题名，用于唯一 Segment。
    - 仅当存在全角/半角竖线时，合并为「左 · 右」
    - 其它情况（含「通用·社区」单段）整段作为一个主题，不再拆成两个层级
    """
    text = (label or "").strip()
    if not text:
        return ""
    for sep in ("\uff5c", "|"):
        if sep in text:
            a, b = text.split(sep, 1)
            a, b = a.strip(), b.strip()
            if a and b:
                return f"{a} · {b}"
            return a or b or ""
    return text


def parse_scope_label(label: str) -> tuple[str, str] | None:
    """
    返回 (固定行业名, 合并后的主题名)。行业层统一为 MERGED_TAXONOMY，仅 Segment 承载具体主题。
    """
    topic = merge_scope_label_to_topic_name(label)
    if not topic:
        return None
    return (MERGED_TAXONOMY_INDUSTRY_NAME, topic)


def sync_product_taxonomy_from_admin_sources(db: Session) -> int:
    """
    根据 admin_source_configs 的领域标签创建/补齐 **一个** 根 Industry（domains）及下属 Segment（合并主题）。
    返回新建行数（近似）。
    """
    from .models import AdminSourceConfig
    from .product_models import Industry, Segment

    created = 0
    rows = db.scalars(select(AdminSourceConfig).order_by(AdminSourceConfig.source.asc())).all()

    ind = db.scalar(select(Industry).where(Industry.slug == MERGED_TAXONOMY_INDUSTRY_SLUG))
    if not ind:
        max_ind_sort = db.scalar(select(Industry.sort_order).order_by(Industry.sort_order.desc()).limit(1)) or 0
        ind = Industry(
            slug=MERGED_TAXONOMY_INDUSTRY_SLUG,
            name=MERGED_TAXONOMY_INDUSTRY_NAME[:128],
            enabled=True,
            sort_order=max_ind_sort + 1,
        )
        db.add(ind)
        db.flush()
        created += 1

    for src in rows:
        for label in get_scope_labels_from_source(src):
            parsed = parse_scope_label(label)
            if not parsed:
                continue
            _ind_name, seg_name = parsed
            sslug = slugify_segment(MERGED_TAXONOMY_INDUSTRY_SLUG, seg_name)
            seg = db.scalar(
                select(Segment).where(Segment.industry_id == ind.id, Segment.slug == sslug)
            ) or db.scalar(select(Segment).where(Segment.industry_id == ind.id, Segment.name == seg_name))
            if not seg:
                max_seg = (
                    db.scalar(
                        select(Segment.sort_order)
                        .where(Segment.industry_id == ind.id)
                        .order_by(Segment.sort_order.desc())
                        .limit(1)
                    )
                    or 0
                )
                seg = Segment(
                    industry_id=ind.id,
                    slug=sslug,
                    name=seg_name[:128],
                    enabled=True,
                    sort_order=max_seg + 1,
                    show_on_public=True,
                )
                db.add(seg)
                created += 1

    db.commit()
    return created


def industry_slugs_from_enabled_sources(db: Session) -> set[str]:
    from .models import AdminSourceConfig

    for src in db.scalars(select(AdminSourceConfig).where(AdminSourceConfig.enabled == True)).all():
        for label in get_scope_labels_from_source(src):
            if merge_scope_label_to_topic_name(label):
                return {MERGED_TAXONOMY_INDUSTRY_SLUG}
    return set()


def segment_slugs_from_enabled_sources_for_industry(db: Session, industry: Industry) -> set[str]:
    from .models import AdminSourceConfig

    if industry.slug != MERGED_TAXONOMY_INDUSTRY_SLUG:
        return set()

    out: set[str] = set()
    for src in db.scalars(select(AdminSourceConfig).where(AdminSourceConfig.enabled == True)).all():
        for label in get_scope_labels_from_source(src):
            p = parse_scope_label(label)
            if not p:
                continue
            _ind_name, seg_name = p
            out.add(slugify_segment(MERGED_TAXONOMY_INDUSTRY_SLUG, seg_name))
    return out


def industry_ids_with_public_content(db: Session) -> set[int]:
    """有指标或已发布文章的行业，用于与「数据源驱动」列表合并，避免演示/历史内容不可选。"""
    from .product_models import Article, MetricDefinition, Segment

    m = {
        int(x)
        for x in db.scalars(
            select(Segment.industry_id)
            .join(MetricDefinition, MetricDefinition.segment_id == Segment.id)
            .distinct()
        ).all()
        if x is not None
    }
    a = {
        int(x)
        for x in db.scalars(select(Article.industry_id).where(Article.status == "published").distinct()).all()
        if x is not None
    }
    return m | a


def segment_ids_with_public_content_for_industry(db: Session, industry_id: int) -> set[int]:
    from .product_models import Article, MetricDefinition, Segment

    seg_set = {int(x) for x in db.scalars(select(Segment.id).where(Segment.industry_id == industry_id)).all()}
    if not seg_set:
        return set()
    m = {
        int(x)
        for x in db.scalars(select(MetricDefinition.segment_id).where(MetricDefinition.segment_id.in_(seg_set))).all()
        if x is not None
    }
    a = {
        int(x)
        for x in db.scalars(
            select(Article.segment_id).where(Article.industry_id == industry_id, Article.status == "published").distinct()
        ).all()
        if x is not None
    }
    return m | a
