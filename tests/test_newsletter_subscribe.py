"""邮件订阅：规范化、临时域名拦截、SQLite 下去重（不启动 FastAPI lifespan / 不连默认 Postgres）。"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.application import newsletter_public as nl_pub
from backend.app.models import NewsletterSubscriber


def test_normalize_rejects_bad_email() -> None:
    with pytest.raises(ValueError):
        nl_pub.normalize_and_validate_email("not-an-email")


def test_normalize_rejects_disposable_domain() -> None:
    with pytest.raises(ValueError, match="临时"):
        nl_pub.normalize_and_validate_email("a@mailinator.com")


def test_normalize_accepts_example_com() -> None:
    assert nl_pub.normalize_and_validate_email("Test@EXAMPLE.com", verify_mx=False) == "test@example.com"


@pytest.fixture()
def nl_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    NewsletterSubscriber.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_subscribe_created_then_duplicate(nl_db) -> None:
    em = nl_pub.normalize_and_validate_email("dup@example.com", verify_mx=False)
    assert nl_pub.subscribe(nl_db, em) == "created"
    assert nl_pub.subscribe(nl_db, em) == "duplicate"


def test_subscribe_race_duplicate_via_integrity(nl_db) -> None:
    em = nl_pub.normalize_and_validate_email("race@example.com", verify_mx=False)
    nl_db.add(NewsletterSubscriber(email=em, unsubscribe_token="x" * 64))
    nl_db.commit()
    assert nl_pub.subscribe(nl_db, em) == "duplicate"
    nl_db.execute(delete(NewsletterSubscriber).where(NewsletterSubscriber.email == em))
    nl_db.commit()


def test_subscribe_reactivate_after_unsub(nl_db) -> None:
    from datetime import datetime

    from sqlalchemy import select

    em = nl_pub.normalize_and_validate_email("re@example.com", verify_mx=False)
    assert nl_pub.subscribe(nl_db, em) == "created"
    row = nl_db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == em))
    assert row and row.unsubscribe_token
    row.unsubscribed_at = datetime.utcnow()
    nl_db.commit()
    assert nl_pub.subscribe(nl_db, em) == "reactivated"
    nl_db.refresh(row)
    assert row.unsubscribed_at is None


def test_unsubscribe_by_token(nl_db) -> None:
    from sqlalchemy import select

    em = nl_pub.normalize_and_validate_email("un@example.com", verify_mx=False)
    assert nl_pub.subscribe(nl_db, em) == "created"
    row = nl_db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == em))
    tok = row.unsubscribe_token
    assert tok
    assert nl_pub.unsubscribe_by_token(nl_db, tok) is True
    nl_db.refresh(row)
    assert row.unsubscribed_at is not None
    assert nl_pub.unsubscribe_by_token(nl_db, tok) is False
