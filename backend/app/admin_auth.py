from __future__ import annotations

import hashlib
import os
import secrets
import hmac
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AdminSession, AdminSetting, AdminUser, AuditLog

SESSION_COOKIE = "aisoul_admin_session"
SESSION_TTL_HOURS = 12
ROLE_LEVEL = {"viewer": 1, "operator": 2, "admin": 3}
ADMIN_COOKIE_SECURE = os.getenv("AISOU_ADMIN_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"}
ADMIN_MAX_FAILED_ATTEMPTS = int(os.getenv("AISOU_ADMIN_MAX_FAILED_ATTEMPTS", "5"))
ADMIN_LOCK_MINUTES = int(os.getenv("AISOU_ADMIN_LOCK_MINUTES", "15"))
APP_ENV = os.getenv("AISOU_ENV", "dev").lower()

if APP_ENV in {"dev", "local"} and os.getenv("AISOU_ADMIN_COOKIE_SECURE") is None:
    ADMIN_COOKIE_SECURE = False


def hash_password(password: str) -> str:
    iterations = 120_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(raw_password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iter_s, salt, digest = stored_hash.split("$", 3)
            iterations = int(iter_s)
        except ValueError:
            return False
        check = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
        return hmac.compare_digest(check, digest)
    # backward compatibility with legacy plain sha256 storage
    legacy = hashlib.sha256(raw_password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, stored_hash)


def ensure_default_admin(db: Session) -> None:
    if db.scalar(select(AdminUser.id).limit(1)):
        return
    init_username = os.getenv("AISOU_ADMIN_INIT_USERNAME")
    init_password = os.getenv("AISOU_ADMIN_INIT_PASSWORD")
    if not init_username or not init_password:
        if APP_ENV not in {"dev", "local"}:
            raise RuntimeError("missing AISOU_ADMIN_INIT_USERNAME/AISOU_ADMIN_INIT_PASSWORD")
        init_username = "admin"
        init_password = "admin123456"
    user = AdminUser(
        username=init_username,
        password_hash=hash_password(init_password),
        role="admin",
        enabled=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()


def audit(db: Session, actor: str, action: str, target: str = "", detail: str = "", request_id: str = "") -> None:
    db.add(AuditLog(actor=actor, action=action, target=target, detail=detail, request_id=request_id))
    db.commit()


def login(db: Session, response: Response, username: str, password: str) -> dict:
    user = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="invalid credentials")
    now = datetime.utcnow()
    settings = {s.key: s.value for s in db.scalars(select(AdminSetting)).all()}
    max_failed_attempts = int(settings.get("max_failed_attempts", str(ADMIN_MAX_FAILED_ATTEMPTS)))
    lock_minutes = int(settings.get("lock_minutes", str(ADMIN_LOCK_MINUTES)))
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=423, detail="account locked")
    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        if user.failed_attempts >= max_failed_attempts:
            user.locked_until = now + timedelta(minutes=lock_minutes)
        user.updated_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not user.password_hash.startswith("pbkdf2_sha256$"):
        user.password_hash = hash_password(password)
    user.failed_attempts = 0
    user.locked_until = None
    user.updated_at = now
    db.commit()
    sid = f"s_{secrets.token_hex(24)}"
    expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
    db.add(
        AdminSession(
            sid=sid,
            user_id=user.id,
            username=user.username,
            role=user.role,
            expires_at=expires_at,
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sid,
        httponly=True,
        secure=ADMIN_COOKIE_SECURE,
        samesite="lax",
        max_age=SESSION_TTL_HOURS * 3600,
        path="/",
    )
    return {"username": user.username, "role": user.role, "expires_at": expires_at.isoformat()}


def logout(db: Session, request: Request, response: Response) -> dict:
    sid = request.cookies.get(SESSION_COOKIE, "")
    if sid:
        session = db.scalar(select(AdminSession).where(AdminSession.sid == sid))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


def get_session(db: Session, request: Request) -> AdminSession:
    sid = request.cookies.get(SESSION_COOKIE, "")
    if not sid:
        raise HTTPException(status_code=401, detail="unauthenticated")
    session = db.scalar(select(AdminSession).where(AdminSession.sid == sid))
    if not session:
        raise HTTPException(status_code=401, detail="unauthenticated")
    if session.expires_at < datetime.utcnow():
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="session expired")
    return session


def require_role(role: str):
    required_level = ROLE_LEVEL.get(role, 99)

    def _dep(request: Request, db: Session = Depends(get_db)) -> AdminSession:
        session = get_session(db, request)
        if ROLE_LEVEL.get(session.role, 0) < required_level:
            raise HTTPException(status_code=403, detail="forbidden")
        return session

    return _dep
