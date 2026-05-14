from __future__ import annotations

import os

from fastapi import APIRouter

from ...core.envelope import success

router = APIRouter(tags=["public-system"])


def _public_version_payload() -> dict[str, str | None]:
    """供页面核对部署是否已更新；库内 app_release_label 优先，其次环境变量 AITRENDS_APP_RELEASE。"""
    from ...runtime_settings_service import app_release_label_effective

    db_rel = app_release_label_effective()
    if db_rel:
        git_sha = os.environ.get("AITRENDS_GIT_SHA", "").strip() or None
        return {"release": db_rel, "git_sha": git_sha}
    env_rel = os.environ.get("AITRENDS_APP_RELEASE", "").strip()
    git_sha = os.environ.get("AITRENDS_GIT_SHA", "").strip() or None
    if env_rel:
        return {"release": env_rel, "git_sha": git_sha}
    return {"release": "0.0.0", "git_sha": git_sha}


@router.get("/health")
def health_public():
    return success({"status": "ok"})


@router.get("/version")
def version_public():
    return success(_public_version_payload())
