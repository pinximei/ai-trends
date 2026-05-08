from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.envelope import success
from ...db import get_db
from ...product_models import CmsPage

router = APIRouter(tags=["public-pages"])


@router.get("/pages/{slug}")
def get_page(slug: str, lang: str = Query("", description="en 时关于页优先使用 slug=about_en（若存在）"), db: Session = Depends(get_db)):
    key = slug
    if slug == "about" and lang.strip().lower().startswith("en"):
        if db.get(CmsPage, "about_en"):
            key = "about_en"
    p = db.get(CmsPage, key)
    if not p or p.status != "published":
        raise HTTPException(404, "not found")
    return success({"slug": p.slug, "title": p.title, "body_md": p.body_md, "updated_at": p.updated_at.isoformat() + "Z"})
