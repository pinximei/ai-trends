from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...application import newsletter_public as nl_app
from ...core.envelope import failure, success
from ...db import get_db

router = APIRouter(tags=["public-newsletter"])


class NewsletterSubscribeBody(BaseModel):
    email: str = Field(..., min_length=1, max_length=320)


@router.post("/newsletter/subscribe")
def newsletter_subscribe(body: NewsletterSubscribeBody, db: Session = Depends(get_db)):
    try:
        norm = nl_app.normalize_and_validate_email(body.email)
    except ValueError as e:
        return failure(str(e), code=400001)
    result = nl_app.subscribe(db, norm)
    if result == "duplicate":
        return failure("该邮箱已订阅，无需重复提交", code=409001)
    return success({"subscribed": True})
