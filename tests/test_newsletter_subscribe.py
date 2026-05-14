"""邮件订阅：规范化、临时域名拦截、SQLite 下去重（不启动 FastAPI lifespan / 不连默认 Postgres）。"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.application import newsletter_public as nl_pub
from backend.app.models import NewsletterSubscriber


@pytest.fixture(autouse=True)
def _newsletter_no_mx(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEWSLETTER_VERIFY_MX", "0")


def test_normalize_rejects_bad_email() -> None:
    with pytest.raises(ValueError):
        nl_pub.normalize_and_validate_email("not-an-email")


def test_normalize_rejects_disposable_domain() -> None:
    with pytest.raises(ValueError, match="临时"):
        nl_pub.normalize_and_validate_email("a@mailinator.com")


def test_normalize_accepts_example_com() -> None:
    assert nl_pub.normalize_and_validate_email("Test@EXAMPLE.com") == "test@example.com"


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
    em = nl_pub.normalize_and_validate_email("dup@example.com")
    assert nl_pub.subscribe(nl_db, em) == "created"
    assert nl_pub.subscribe(nl_db, em) == "duplicate"


def test_subscribe_race_duplicate_via_integrity(nl_db) -> None:
    em = nl_pub.normalize_and_validate_email("race@example.com")
    nl_db.add(NewsletterSubscriber(email=em))
    nl_db.commit()
    assert nl_pub.subscribe(nl_db, em) == "duplicate"
    nl_db.execute(delete(NewsletterSubscriber).where(NewsletterSubscriber.email == em))
    nl_db.commit()
