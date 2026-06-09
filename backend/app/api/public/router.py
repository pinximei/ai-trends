from __future__ import annotations

from fastapi import APIRouter

from .articles import router as articles_router
from .github_trending import router as github_trending_router
from .home import router as home_router
from .media import router as media_router
from .newsletter import router as newsletter_router
from .pages import router as pages_router
from .seo import router as seo_router
from .software import router as software_router
from .ssr import router as ssr_router
from .system import router as system_router
from .publishing import router as publishing_router
router = APIRouter(prefix="/api/public/v1")
router.include_router(articles_router)
router.include_router(github_trending_router)
router.include_router(publishing_router)
router.include_router(home_router)
router.include_router(ssr_router)
router.include_router(newsletter_router)
router.include_router(pages_router)
router.include_router(software_router)
router.include_router(media_router)
router.include_router(seo_router)
router.include_router(system_router)
