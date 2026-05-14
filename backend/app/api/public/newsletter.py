from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...application import newsletter_public as nl_app
from ...core.envelope import failure, success
from ...db import get_db
from ...newsletter_settings_service import get_newsletter_settings_merged

router = APIRouter(tags=["public-newsletter"])


class NewsletterSubscribeBody(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)


@router.post("/newsletter/subscribe")
def newsletter_subscribe(body: NewsletterSubscribeBody, db: Session = Depends(get_db)):
    try:
        settings = get_newsletter_settings_merged(db)
        verify_mx = bool(settings.get("subscribe_verify_mx", True))
        norm = nl_app.normalize_and_validate_email(body.email, verify_mx=verify_mx)
    except ValueError as e:
        return failure(str(e), code=400001)
    result = nl_app.subscribe(db, norm)
    if result == "duplicate":
        return failure("该邮箱已订阅，无需重复提交", code=409001)
    return success({"subscribed": True, "reactivated": result == "reactivated"})


@router.get("/newsletter/unsubscribe", response_class=HTMLResponse)
def newsletter_unsubscribe(token: str | None = Query(None), db: Session = Depends(get_db)):
    t = (token or "").strip()
    ok = len(t) >= 8 and nl_app.unsubscribe_by_token(db, t)
    title = "退订成功" if ok else "退订链接无效或已退订"
    body = (
        "<p>您已成功退订本站邮件。如需再次订阅，可回到首页提交邮箱。</p>"
        if ok
        else "<p>链接无效或该邮箱已退订。若需帮助，请联系站点管理员。</p>"
    )
    return HTMLResponse(
        content=(
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"/>"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/><title>{title}</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1rem;color:#0f172a;}"
            "a{color:#4f46e5;}</style></head><body>"
            f"<h1>{title}</h1>{body}<p><a href=\"/\">返回首页</a></p></body></html>"
        ),
        status=200,
    )
