"""连接器同步等场景下写入「资源」文章（product_articles），供公开站 /resources 使用。"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from .product_models import Article


def create_published_articles_for_connector_targets(
    db: Session,
    *,
    connector_id: int,
    connector_name: str,
    admin_source_key: str,
    targets: list[dict],
    http_status: int,
    snippet: str,
    now: datetime,
) -> int:
    """
    为每个解析出的 (industry_id, segment_id) 新增一篇 **已发布** 文章。
    targets 项须含: industry_id, segment_id, segment_slug, label（展示用）。
    返回新建篇数。
    """
    if not targets:
        return 0
    safe = (snippet or "")[:12000]
    summary_base = (safe[:500] if safe else f"HTTP {http_status}")[:512]
    src_tag = admin_source_key.strip() if admin_source_key.strip() else "未绑定数据源"
    n = 0
    for t in targets:
        slug = f"sync-c{connector_id}-s{t['segment_id']}-{uuid.uuid4().hex[:16]}"[:128]
        label = (t.get("label") or t.get("segment_slug") or "板块")[:200]
        title = f"同步资源 · {label} · {connector_name}"[:500]
        body = (
            "## 连接器同步快照\n\n"
            f"- **数据源标识**: `{src_tag}`\n"
            f"- **领域标签**: {label}\n"
            f"- **HTTP 状态**: {http_status}\n\n"
            f"```\n{safe[:8000]}\n```\n"
        )
        db.add(
            Article(
                title=title,
                slug=slug,
                summary=summary_base,
                body=body,
                segment_id=int(t["segment_id"]),
                industry_id=int(t["industry_id"]),
                content_type="third_party_derived",
                third_party_source=f"{src_tag} / {connector_name}"[:512],
                status="published",
                published_at=now,
            )
        )
        n += 1
    return n
