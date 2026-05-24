from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..admin_auth import audit, require_role
from ..db import get_db
from ..hot_service import rebuild_hot_snapshot
from ..models import AdminSession
from ..product_models import Article, CmsPage, HotSnapshot, Industry
from ..services import clear_product_ingest_data
from .admin_extended import run_theme_fetch_batch

router = APIRouter(prefix="/api/admin/v1", tags=["admin-product"])


def ok(data):
    return {"code": 0, "message": "ok", "data": data}


class CmsUpdate(BaseModel):
    title: str | None = None
    body_md: str | None = None
    status: str | None = None


class ThemeFetchPayload(BaseModel):
    """可选搜索主题：若填写，仅在连接器 URL 尚未带 q/query/keywords/search_query 时追加 ``q``。"""

    theme: str | None = Field(default=None, max_length=200)


@router.post("/product/ingest-data/clear")
def post_clear_product_ingest_data(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    """删除连接器入库相关表数据并重置连接器上次同步时间（高危，仅管理员）。"""
    counts = clear_product_ingest_data(db)
    audit(db, actor=session.username, action="product.ingest_data.clear", detail=str(counts))
    return ok(counts)


@router.post("/product/ingest/theme-fetch")
def post_theme_fetch_ingest(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
    payload: ThemeFetchPayload = ThemeFetchPayload(),
):
    """按数据源领域刷新 taxonomy，并对所有已启用连接器立即同步（可选主题词写入 URL 的 q）。"""
    data = run_theme_fetch_batch(db, actor=session.username, theme=payload.theme)
    return ok(data)


@router.get("/product/sync-diagnostic-logs")
def get_sync_diagnostic_logs(
    run_id: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    from ..sync_diagnostic_log import DIAG_PIPELINE_VERSION, list_logs, list_recent_run_ids

    rid = (run_id or "").strip() or None
    items = list_logs(db, run_id=rid, limit=limit)
    return ok(
        {
            "items": items,
            "recent_run_ids": list_recent_run_ids(db),
            "run_id": rid,
            "diag_pipeline_version": DIAG_PIPELINE_VERSION,
        }
    )


@router.get("/product/sync-diagnostic-logs/export")
def export_sync_diagnostic_logs(
    run_id: str,
    limit: int = 800,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    """纯文本导出，便于复制到聊天/工单。"""
    from fastapi.responses import PlainTextResponse

    from ..sync_diagnostic_log import format_logs_for_export, list_logs

    _ = session
    rid = (run_id or "").strip()
    if not rid:
        from fastapi import HTTPException

        raise HTTPException(400, "run_id required")
    items = list_logs(db, run_id=rid, limit=limit)
    body = format_logs_for_export(items, run_id=rid)
    return PlainTextResponse(body, media_type="text/plain; charset=utf-8")


@router.delete("/product/sync-diagnostic-logs")
def delete_sync_diagnostic_logs(
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    from ..sync_diagnostic_log import clear_all

    n = clear_all(db)
    db.commit()
    audit(db, actor=session.username, action="product.sync_diagnostic.clear", detail=str(n))
    return ok({"deleted": n})


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
