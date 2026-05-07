from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core.envelope import success
from ...db import get_db
from ...product_models import CmsPage

router = APIRouter(tags=["public-pages"])


@router.get("/pages/{slug}")
def get_page(slug: str, db: Session = Depends(get_db)):
    p = db.get(CmsPage, slug)
    if not p or p.status != "published":
        raise HTTPException(404, "not found")
    return success({"slug": p.slug, "title": p.title, "body_md": p.body_md, "updated_at": p.updated_at.isoformat() + "Z"})
