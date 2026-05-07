from __future__ import annotations

from fastapi import APIRouter

from ...core.envelope import success

router = APIRouter(tags=["public-system"])


@router.get("/health")
def health_public():
    return success({"status": "ok"})
