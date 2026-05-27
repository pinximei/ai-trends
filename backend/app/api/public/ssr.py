"""公开站 SSR：首页 HTML 壳 + 内嵌仪表盘 JSON。"""
from __future__ import annotations

from fastapi import Depends, Response
from fastapi import APIRouter
from sqlalchemy.orm import Session

from ...application.ssr_public import build_home_ssr_bootstrap, render_home_ssr_document
from ...core.envelope import success
from ...db import get_db

router = APIRouter(tags=["public-ssr"])


@router.get("/ssr/home-bootstrap")
def ssr_home_bootstrap(industry_slug: str = "ai", db: Session = Depends(get_db)):
    """客户端可读的 SSR 数据包（与首页 dashboard 结构一致）。"""
    return success(build_home_ssr_bootstrap(db, industry_slug=industry_slug))


@router.get("/ssr/document/home")
def ssr_document_home(industry_slug: str = "ai", db: Session = Depends(get_db)):
    """返回注入 SSR 的 index.html（Nginx SPA 回退应 proxy 到此）。"""
    try:
        html = render_home_ssr_document(db, industry_slug=industry_slug)
    except FileNotFoundError as e:
        return Response(content=str(e), status_code=503, media_type="text/plain; charset=utf-8")
    return Response(content=html, media_type="text/html; charset=utf-8")
