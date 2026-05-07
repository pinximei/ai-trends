from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..product_models import SoftwareDownload


def list_software_categories(db: Session) -> list[dict]:
    q = (
        select(
            SoftwareDownload.category_slug,
            SoftwareDownload.category_label,
            func.count(SoftwareDownload.id),
        )
        .where(SoftwareDownload.status == "published")
        .group_by(SoftwareDownload.category_slug, SoftwareDownload.category_label)
        .order_by(SoftwareDownload.category_label)
    )
    rows = db.execute(q).all()
    return [
        {"slug": r[0], "label": (r[1] or r[0] or "").strip() or r[0], "count": int(r[2] or 0)}
        for r in rows
        if r[0]
    ]


def list_software_downloads(
    db: Session,
    *,
    platform: str,
    category_slug: str | None,
    limit: int,
) -> list[dict]:
    q = select(SoftwareDownload).where(SoftwareDownload.status == "published")
    if platform in ("ios", "android"):
        q = q.where(SoftwareDownload.platform == platform)
    if category_slug and str(category_slug).strip():
        q = q.where(SoftwareDownload.category_slug == str(category_slug).strip())
    rows = db.scalars(q.order_by(desc(SoftwareDownload.sort_order), desc(SoftwareDownload.id)).limit(limit)).all()
    out: list[dict] = []
    for r in rows:
        rel = getattr(r, "artifact_rel_path", None) or None
        if rel:
            download_url = f"/api/public/v1/software/downloads/{r.id}/file"
            download_mode = "direct"
        else:
            download_url = (r.store_url or "").strip()
            download_mode = "external" if download_url else "none"
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "summary": r.summary,
                "platform": r.platform,
                "category_slug": r.category_slug,
                "category_label": r.category_label,
                "store_url": (r.store_url or "").strip(),
                "download_url": download_url,
                "download_mode": download_mode,
                "icon_url": r.icon_url,
                "sort_order": r.sort_order,
            }
        )
    return out
