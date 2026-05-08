from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter

from ...core.envelope import success

router = APIRouter(tags=["public-system"])


def _pyproject_version() -> str | None:
    root = Path(__file__).resolve().parents[4]
    pp = root / "pyproject.toml"
    if not pp.is_file():
        return None
    try:
        import tomllib  # py3.11+
    except ImportError:
        tomllib = None  # type: ignore[misc,assignment]
    if tomllib:
        try:
            with pp.open("rb") as f:
                ver = tomllib.load(f).get("project", {}).get("version")
            if ver:
                return str(ver).strip()
        except Exception:
            pass
    try:
        txt = pp.read_text(encoding="utf-8", errors="replace")
        if m := re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"", txt):
            return m.group(1).strip()
    except Exception:
        pass
    return None


def _public_version_payload() -> dict[str, str | None]:
    """供页面核对部署是否已更新；库内 app_release_label 优先，其次环境变量 AISOU_APP_RELEASE。"""
    from ...runtime_settings_service import app_release_label_effective

    db_rel = app_release_label_effective()
    if db_rel:
        git_sha = os.environ.get("AISOU_GIT_SHA", "").strip() or None
        return {"release": db_rel, "git_sha": git_sha}
    env_rel = os.environ.get("AISOU_APP_RELEASE", "").strip()
    git_sha = os.environ.get("AISOU_GIT_SHA", "").strip() or None
    if env_rel:
        return {"release": env_rel, "git_sha": git_sha}
    ver = _pyproject_version() or "0.0.0"
    if git_sha:
        return {"release": f"{ver}+{git_sha}", "git_sha": git_sha}
    return {"release": ver, "git_sha": None}


@router.get("/health")
def health_public():
    return success({"status": "ok"})


@router.get("/version")
def version_public():
    return success(_public_version_payload())
