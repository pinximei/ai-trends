"""应用安装包：落盘到 data/software_uploads 并写入 product_software_downloads。"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .db import DATA_DIR
from .product_models import SoftwareDownload

_UPLOAD_ROOT = DATA_DIR / "software_uploads"


def _sanitize_filename(name: str) -> str:
    base = Path(name).name
    s = re.sub(r"[^a-zA-Z0-9._\u4e00-\u9fff-]+", "_", base).strip("._") or "package"
    return s[:180]


def artifact_disk_path(rel: str) -> Path:
    """校验路径落在 data/software_uploads 下，防穿越。"""
    p = (DATA_DIR / rel).resolve()
    root = _UPLOAD_ROOT.resolve()
    try:
        p.relative_to(root)
    except ValueError as e:
        raise ValueError("invalid artifact path") from e
    return p


def create_software_package_with_file(
    db: Session,
    *,
    title: str,
    summary: str,
    platform: str,
    category_slug: str,
    category_label: str,
    file_body: bytes,
    original_filename: str,
    content_type: str | None,
    sort_order: int = 0,
    store_url: str | None = None,
    status: str = "published",
) -> SoftwareDownload:
    plat = (platform or "").strip().lower()
    if plat not in ("ios", "android"):
        raise ValueError("platform must be ios or android")
    if not file_body:
        raise ValueError("empty file")
    if len(file_body) > 120_000_000:
        raise ValueError("file too large (max 120MB)")
    title = (title or "").strip()[:256]
    if not title:
        raise ValueError("title required")
    slug = (category_slug or "").strip()[:64] or "general"
    label = (category_label or "").strip()[:128] or slug
    row = SoftwareDownload(
        title=title,
        summary=(summary or "")[:4000],
        platform=plat,
        category_slug=slug,
        category_label=label,
        store_url=(store_url or "").strip()[:1024],
        icon_url=None,
        sort_order=int(sort_order),
        status=status if status in ("published", "draft") else "published",
        artifact_rel_path=None,
        artifact_download_name=None,
        artifact_mime=None,
    )
    db.add(row)
    db.flush()
    safe = _sanitize_filename(original_filename)
    rel_posix = f"software_uploads/{row.id}/{safe}".replace("\\", "/")
    dest_dir = _UPLOAD_ROOT / str(row.id)
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / safe
        dest.write_bytes(file_body)
        row.artifact_rel_path = rel_posix
        row.artifact_download_name = Path(original_filename).name[:200] or safe
        row.artifact_mime = ((content_type or "").strip()[:128] or "application/octet-stream")
        db.commit()
    except Exception:
        db.rollback()
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        raise
    db.refresh(row)
    return row


def delete_software_package(db: Session, package_id: int) -> bool:
    row = db.get(SoftwareDownload, package_id)
    if not row:
        return False
    rel = row.artifact_rel_path
    db.delete(row)
    db.commit()
    if rel:
        try:
            p = artifact_disk_path(rel)
            if p.is_file():
                p.unlink(missing_ok=True)
            parent = p.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass
    return True


def list_packages_admin(db: Session, *, limit: int = 80) -> list[dict]:
    rows = db.scalars(select(SoftwareDownload).order_by(desc(SoftwareDownload.id)).limit(limit)).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "platform": r.platform,
            "category_slug": r.category_slug,
            "category_label": r.category_label,
            "status": r.status,
            "sort_order": r.sort_order,
            "has_artifact": bool(r.artifact_rel_path),
            "store_url": (r.store_url or "").strip(),
            "created_at": r.created_at.isoformat() + "Z",
        }
        for r in rows
    ]
