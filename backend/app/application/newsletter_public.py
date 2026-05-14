"""首页等公开入口的邮件订阅：规范化、可投递性、临时域名拦截、落库去重。"""
from __future__ import annotations

import os
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
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


def _verify_mx_default() -> bool:
    v = (os.environ.get("NEWSLETTER_VERIFY_MX", "true") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def normalize_and_validate_email(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        raise ValueError("请填写邮箱")
    if len(s) > 320:
        raise ValueError("邮箱过长")
    verify_mx = _verify_mx_default()
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


def subscribe(db: Session, email_norm: str) -> Literal["created", "duplicate"]:
    hit = db.scalar(select(NewsletterSubscriber.id).where(NewsletterSubscriber.email == email_norm))
    if hit is not None:
        return "duplicate"
    db.add(NewsletterSubscriber(email=email_norm))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return "duplicate"
    return "created"
