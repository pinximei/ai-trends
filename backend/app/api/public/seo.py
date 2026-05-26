from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ...application import seo_public as seo_app
from ...db import get_db
from ...public_site import resolve_public_site_base_url

router = APIRouter(tags=["public-seo"])


@router.get("/sitemap.xml")
def sitemap_xml(db: Session = Depends(get_db)):
    xml = seo_app.build_sitemap_xml(db)
    return Response(
        content=xml,
        media_type="application/xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/seo/site")
def seo_site_meta(db: Session = Depends(get_db)):
    """供前端构建 canonical / og:url（与 sitemap 同源 base）。"""
    from ...core.envelope import success

    return success({"public_site_base_url": resolve_public_site_base_url(db)})
