from __future__ import annotations

from fastapi import APIRouter

from .articles import router as articles_router
from .newsletter import router as newsletter_router
from .pages import router as pages_router
from .software import router as software_router
from .system import router as system_router

router = APIRouter(prefix="/api/public/v1")
router.include_router(articles_router)
router.include_router(newsletter_router)
router.include_router(pages_router)
router.include_router(software_router)
router.include_router(system_router)
