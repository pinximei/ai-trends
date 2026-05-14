"""首页等公开入口的邮件订阅：规范化、可投递性、临时域名拦截、落库去重。"""
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import NewsletterSubscriber

# 常见临时邮箱域名（可随运营扩充）
_DISPOSABLE_DOMAINS = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "10minutemail.com",
        "tempmail.com",
        "yopmail.com",
        "trashmail.com",
        "fakeinbox.com",
        "sharklasers.com",
        "getairmail.com",
        "maildrop.cc",
        "dispostable.com",
    }
)


def normalize_and_validate_email(raw: str, *, verify_mx: bool = True) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("请填写邮箱")
    if len(s) > 320:
        raise ValueError("邮箱过长")
    try:
        info = validate_email(s, check_deliverability=verify_mx)
    except EmailNotValidError:
        raise ValueError("邮箱不可用或域名无法接收邮件，请检查后重试") from None
    dom = info.domain.lower()
    if dom in _DISPOSABLE_DOMAINS:
        raise ValueError("暂不支持临时邮箱，请使用常用邮箱订阅")
    out = info.normalized.lower()
    if len(out) > 254:
        raise ValueError("邮箱过长")
    return out


def _new_unsubscribe_token() -> str:
    return secrets.token_urlsafe(32)[:64]


def subscribe(db: Session, email_norm: str) -> Literal["created", "duplicate", "reactivated"]:
    row = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == email_norm))
    if row is not None and row.unsubscribed_at is None:
        return "duplicate"
    if row is not None and row.unsubscribed_at is not None:
        row.unsubscribed_at = None
        row.unsubscribe_token = _new_unsubscribe_token()
        db.commit()
        return "reactivated"
    db.add(NewsletterSubscriber(email=email_norm, unsubscribe_token=_new_unsubscribe_token()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    return "created"


def unsubscribe_by_token(db: Session, token: str) -> bool:
    t = (token or "").strip()
    if len(t) < 8:
        return False
    row = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.unsubscribe_token == t))
    if not row or row.unsubscribed_at is not None:
        return False
    row.unsubscribed_at = datetime.utcnow()
    db.commit()
    return True


def backfill_newsletter_unsubscribe_tokens(db: Session) -> int:
    """旧数据补 token；返回更新行数。"""
    rows = list(
        db.scalars(
            select(NewsletterSubscriber).where(
                or_(NewsletterSubscriber.unsubscribe_token.is_(None), NewsletterSubscriber.unsubscribe_token == "")
            )
        ).all()
    )
    n = 0
    for r in rows:
        r.unsubscribe_token = _new_unsubscribe_token()
        n += 1
    if n:
        db.commit()
    return n
