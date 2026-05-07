from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...application import software_public as sw_app
from ...core.envelope import success
from ...db import get_db
from ...product_models import SoftwareDownload
from ...software_package_service import artifact_disk_path

router = APIRouter(tags=["public-software"])


@router.get("/software/downloads/{download_id}/file")
def download_software_file(download_id: int, db: Session = Depends(get_db)):
    row = db.get(SoftwareDownload, download_id)
    if not row or row.status != "published":
        raise HTTPException(404, "not found")
    rel = getattr(row, "artifact_rel_path", None) or None
    if not rel:
        raise HTTPException(404, "no direct download for this item")
    try:
        path = artifact_disk_path(rel)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not path.is_file():
        raise HTTPException(404, "file missing")
    name = (row.artifact_download_name or path.name).strip() or path.name
    media = (row.artifact_mime or "application/octet-stream").strip() or "application/octet-stream"
    return FileResponse(path, filename=name, media_type=media)


@router.get("/software/categories")
def list_software_categories(db: Session = Depends(get_db)):
    return success(sw_app.list_software_categories(db))


@router.get("/software/downloads")
def list_software_downloads(
    platform: str = Query("all", pattern="^(all|ios|android)$"),
    category_slug: str | None = Query(None, description="应用类型 slug，不传表示全部"),
    limit: int = Query(120, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return success(sw_app.list_software_downloads(db, platform=platform, category_slug=category_slug, limit=limit))
