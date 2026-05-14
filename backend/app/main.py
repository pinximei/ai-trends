from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from .lifespan import app_lifespan
from .runtime_cors_middleware import RuntimeCORSMiddleware
from .api.public.router import router as public_api_router
from .routers import admin_data_browser, admin_extended, admin_product
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base, engine, ensure_schema_compatibility, get_db, get_db_runtime_info
from .admin_auth import (
    audit,
    ensure_default_admin,
    get_session,
    hash_password,
    verify_password,
    login as admin_login,
    logout as admin_logout,
    require_role,
)
from .data_api_service import DataApiService
from .models import AdminSession, AdminSourceConfig, AdminUser, EvidenceSignal, NewsletterDailyDigest, NewsletterSubscriber, Trend
from .schemas import (
    AdminLoginRequest,
    AdminChangePasswordRequest,
    AdminSettingsUpdate,
    AdminSourceConfigUpsert,
    AdminSourceTestRequest,
    AdminUserCreate,
    AdminUserUpdate,
)
from .security import enforce_https
from .services import clear_business_data, envelope, seed_demo_bundle

app = FastAPI(title="AI-TRENDS API", lifespan=app_lifespan)

root = Path(__file__).resolve().parent.parent

app.add_middleware(RuntimeCORSMiddleware)

app.include_router(public_api_router)
app.include_router(admin_product.router)
app.include_router(admin_extended.router)
app.include_router(admin_data_browser.router)


SUPPORTED_LANGS = {"zh", "en"}
DEFAULT_LANG = "zh"
I18N = {
    "api.ok": {"zh": "成功", "en": "ok"},
}


def resolve_lang(request: Request) -> str:
    lang = request.query_params.get("lang") or request.cookies.get("lang") or DEFAULT_LANG
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def tr(key: str, lang: str) -> str:
    item = I18N.get(key)
    if not item:
        return key
    return item.get(lang) or item.get(DEFAULT_LANG) or key


def api_envelope(request: Request, data, message_key: str = "api.ok"):
    return envelope(data, message=tr(message_key, resolve_lang(request)))


def _mask_key(raw_key: str) -> str:
    cleaned = (raw_key or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 8:
        return "*" * len(cleaned)
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def _bootstrap_seed_demo_envelope(request: Request, db: Session):
    seed_demo_bundle(db)
    trend_count = db.query(Trend).count()
    signal_count = db.query(EvidenceSignal).count()
    source_count = db.query(AdminSourceConfig).count()
    return api_envelope(
        request,
        {
            "status": "ok",
            "trend_count": trend_count,
            "signal_count": signal_count,
            "source_count": source_count,
        },
    )


def _bootstrap_clear_demo_envelope(request: Request, db: Session):
    clear_business_data(db)
    return api_envelope(request, {"status": "ok", "message": "business data cleared"})


def _validate_password_policy(db: Session, raw_password: str) -> None:
    settings = DataApiService(db).get_settings()
    if len(raw_password or "") < settings["password_min_length"]:
        raise HTTPException(status_code=400, detail=f"password too short, min={settings['password_min_length']}")


@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    enforce_https(request)
    return await call_next(request)


@app.post("/api/admin/v1/auth/login")
def admin_auth_login(request: Request, response: Response, payload: AdminLoginRequest, db: Session = Depends(get_db)):
    data = admin_login(db, response, payload.username.strip(), payload.password)
    audit(db, actor=data["username"], action="auth.login", detail="admin login")
    return api_envelope(request, data)


@app.post("/api/admin/v1/auth/logout")
def admin_auth_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session_actor = "anonymous"
    try:
        session = get_session(db, request)
        session_actor = session.username
    except HTTPException:
        pass
    result = admin_logout(db, request, response)
    audit(db, actor=session_actor, action="auth.logout", detail="admin logout")
    return api_envelope(request, result)


@app.get("/api/admin/v1/auth/me")
def admin_auth_me(request: Request, db: Session = Depends(get_db)):
    session = get_session(db, request)
    pw_min = DataApiService(db).get_settings()["password_min_length"]
    return api_envelope(
        request,
        {
            "username": session.username,
            "role": session.role,
            "expires_at": session.expires_at.isoformat(),
            "password_min_length": pw_min,
        },
    )


@app.post("/api/admin/v1/auth/change-password")
def admin_auth_change_password(
    request: Request,
    payload: AdminChangePasswordRequest,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    user = db.scalar(select(AdminUser).where(AdminUser.username == session.username))
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    _validate_password_policy(db, payload.new_password)
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="old password incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="auth.change_password")
    return api_envelope(request, {"ok": True})


@app.post("/api/admin/v1/bootstrap/seed-demo")
def admin_seed_demo_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    result = _bootstrap_seed_demo_envelope(request, db)
    audit(db, actor=session.username, action="bootstrap.seed_demo")
    return result


@app.post("/api/admin/v1/bootstrap/clear-demo")
def admin_clear_demo_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    result = _bootstrap_clear_demo_envelope(request, db)
    audit(db, actor=session.username, action="bootstrap.clear_demo")
    return result


@app.get("/api/admin/v1/system/db-info")
def admin_db_info_v2(
    request: Request,
    session: AdminSession = Depends(require_role("admin")),
):
    _ = session
    info = get_db_runtime_info()
    return api_envelope(
        request,
        {
            "mode": info["mode"],
            "database_url": info["database_url"],
            "test_url": info["test_url"],
            "prod_url": info["prod_url"],
        },
    )


@app.get("/api/admin/v1/sources/presets")
def admin_source_presets(
    request: Request,
    session: AdminSession = Depends(require_role("viewer")),
):
    """与 services.MAINSTREAM_ADMIN_SOURCE_PRESETS 一致，供前台「新增数据源」一键填入。"""
    from .services import build_admin_source_preset_items

    return api_envelope(request, {"items": build_admin_source_preset_items()})


@app.get("/api/admin/v1/sources")
def admin_sources_v2(
    request: Request,
    keyword: str = "",
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, {"items": DataApiService(db).list_admin_sources(keyword=keyword.strip())})


@app.post("/api/admin/v1/sources")
def admin_sources_upsert_v2(
    request: Request,
    payload: AdminSourceConfigUpsert,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    try:
        data = DataApiService(db).upsert_admin_source(payload.model_dump(), _mask_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(db, actor=session.username, action="source.upsert", target=data["source"], detail="sync=scheduled_unified")
    return api_envelope(request, data)


@app.post("/api/admin/v1/sources/test")
def admin_sources_test_v2(
    request: Request,
    payload: AdminSourceTestRequest,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    """对数据源 api_base 发起 GET；api_key 可选 Bearer 或 GitLab PRIVATE-TOKEN（不落库）。"""
    _ = session
    try:
        data = DataApiService(db).test_source_connection(
            source=(payload.source or "").strip() or None,
            api_base=(payload.api_base or "").strip() or None,
            api_key=(payload.api_key or "").strip() or None,
            auth_mode=payload.auth_mode,
            key_param=(payload.key_param or "key").strip() or "key",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return api_envelope(request, data)


@app.delete("/api/admin/v1/sources/{source}")
def admin_sources_delete_v2(
    request: Request,
    source: str,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("operator")),
):
    try:
        deleted = DataApiService(db).delete_admin_source(source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit(db, actor=session.username, action="source.delete", target=deleted)
    return api_envelope(request, {"deleted": deleted})


@app.get("/api/admin/v1/overview")
def admin_overview_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    return api_envelope(request, DataApiService(db).get_overview_metrics())


@app.get("/api/admin/v1/users")
def admin_users_v2(
    request: Request,
    role: str = "",
    keyword: str = "",
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    return api_envelope(request, {"items": DataApiService(db).list_admin_users(role=role.strip(), keyword=keyword.strip())})


@app.post("/api/admin/v1/users")
def admin_users_create_v2(
    request: Request,
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    exists = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if exists:
        raise HTTPException(status_code=409, detail="username exists")
    _validate_password_policy(db, payload.password)
    item = AdminUser(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        enabled=payload.enabled,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(item)
    db.commit()
    audit(db, actor=session.username, action="user.create", target=username, detail=f"role={payload.role}")
    return api_envelope(request, {"username": item.username, "role": item.role, "enabled": item.enabled})


@app.post("/api/admin/v1/users/{username}")
def admin_users_update_v2(
    request: Request,
    username: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    item = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not item:
        raise HTTPException(status_code=404, detail="user not found")
    if payload.role is not None:
        item.role = payload.role
    if payload.enabled is not None:
        item.enabled = payload.enabled
    if payload.password:
        _validate_password_policy(db, payload.password)
        item.password_hash = hash_password(payload.password)
        item.failed_attempts = 0
        item.locked_until = None
    item.updated_at = datetime.utcnow()
    db.commit()
    audit(db, actor=session.username, action="user.update", target=username)
    return api_envelope(request, {"username": item.username, "role": item.role, "enabled": item.enabled})


@app.delete("/api/admin/v1/users/{username}")
def admin_users_delete_v2(
    request: Request,
    username: str,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    item = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not item:
        raise HTTPException(status_code=404, detail="user not found")
    if item.username == session.username:
        raise HTTPException(status_code=400, detail="cannot delete your own account")
    db.delete(item)
    db.commit()
    audit(db, actor=session.username, action="user.delete", target=username)
    return api_envelope(request, {"deleted": username})


@app.get("/api/admin/v1/settings")
def admin_settings_get_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    return api_envelope(request, DataApiService(db).get_settings())


@app.post("/api/admin/v1/settings")
def admin_settings_update_v2(
    request: Request,
    payload: AdminSettingsUpdate,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("admin")),
):
    data = DataApiService(db).update_settings(payload.model_dump())
    audit(db, actor=session.username, action="settings.update")
    return api_envelope(request, data)


@app.get("/api/admin/v1/health")
def admin_health_v2(
    request: Request,
    db: Session = Depends(get_db),
    session: AdminSession = Depends(require_role("viewer")),
):
    metrics = DataApiService(db).get_overview_metrics()
    return api_envelope(request, {"status": "ok", "db": "up", "metrics": metrics, "time": datetime.utcnow().isoformat()})


@app.get("/")
def api_root():
    """前后端分离：用户界面由 `frontend/`（Vite）提供，此处仅 API 入口说明。"""
    return {
        "service": "aitrends-api",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "ui": "http://127.0.0.1:5172",
        "hint": "cd frontend && npm install && npm run dev",
    }
