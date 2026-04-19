from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..admin_auth import audit, require_role
from ..db import get_db
from ..hot_service import rebuild_hot_snapshot
from ..models import AdminSession
from ..product_models import Article, CmsPage, HotSnapshot, Industry

router = APIRouter(prefix="/api/admin/v1", tags=["admin-product"])


def ok(data):
    return {"code": 0, "message": "ok", "data": data}


class CmsUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    status: str | None = None


@router.post("/product/hot/rebuild")
def post_hot_rebuild(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    snap = rebuild_hot_snapshot(db, trigger="manual")
    audit(db, actor=session.username, action="product.hot.rebuild", target=str(snap.id))
    return ok({"snapshot_id": snap.id, "generated_at": snap.generated_at.isoformat() + "Z"})


@router.get("/product/hot/snapshots")
def list_hot_snapshots(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    rows = db.scalars(select(HotSnapshot).order_by(desc(HotSnapshot.generated_at)).limit(50)).all()
    return ok(
        [
            {
                "id": r.id,
                "industry_id": r.industry_id,
                "generated_at": r.generated_at.isoformat() + "Z",
                "status": r.status,
                "trigger": r.trigger,
            }
            for r in rows
        ]
    )


@router.put("/cms/pages/{slug}")
def put_cms_page(
    slug: str,
    payload: CmsUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    p = db.get(CmsPage, slug)
    if not p:
        p = CmsPage(slug=slug, title=payload.title or "", body_md=payload.body_md or "")
        db.add(p)
    else:
        if payload.title is not None:
            p.title = payload.title
        if payload.body_md is not None:
            p.body_md = payload.body_md
        if payload.status is not None:
            p.status = payload.status
            if payload.status == "published":
                p.published_at = datetime.utcnow()
    p.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="cms.update", target=slug)
    return ok({"slug": p.slug, "status": p.status})


@router.get("/cms/pages/{slug}")
def get_cms_admin(
    slug: str,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    p = db.get(CmsPage, slug)
    if not p:
        raise HTTPException(404, "not found")
    return ok({"slug": p.slug, "title": p.title, "body_md": p.body_md, "status": p.status})
