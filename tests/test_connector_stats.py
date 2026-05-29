"""连接器统计聚合。"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401
from backend.app.application.connector_stats import connector_stats_overview
from backend.app.db import Base
from backend.app.product_models import Article, Industry, ProductConnector, ProductConnectorLog, Segment


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    ind = Industry(slug="ai", name="AI")
    db.add(ind)
    db.flush()
    seg = Segment(industry_id=ind.id, slug="apps", name="Apps")
    db.add(seg)
    db.flush()
    return db, ind.id, seg.id


def test_connector_stats_overview() -> None:
    db, industry_id, segment_id = _session()
    now = datetime.utcnow()
    c = ProductConnector(name="PH", admin_source_key="product_hunt", enabled=True)
    db.add(c)
    db.flush()
    log_ok = ProductConnectorLog(
        connector_id=c.id,
        started_at=now - timedelta(days=2),
        finished_at=now,
        status="ok",
        rows_ingested=5,
    )
    log_err = ProductConnectorLog(
        connector_id=c.id,
        started_at=now - timedelta(days=1),
        finished_at=now,
        status="error",
        rows_ingested=0,
        error_message="timeout",
    )
    db.add_all([log_ok, log_err])
    db.flush()
    db.add(
        Article(
            title="A",
            summary="s",
            body="b",
            industry_id=industry_id,
            segment_id=segment_id,
            connector_sync_log_id=log_ok.id,
            created_at=now,
            status="published",
            published_at=now,
        )
    )
    db.commit()

    out = connector_stats_overview(db, days=7)
    assert out["summary"]["sync_runs"] == 2
    assert out["summary"]["ok_runs"] == 1
    assert out["summary"]["error_runs"] == 1
    assert out["summary"]["articles_created"] == 1
    assert out["summary"]["rows_ingested"] == 5
    assert len(out["daily"]) == 7
    assert out["by_connector"][0]["connector_id"] == c.id
    assert out["by_source"][0]["source_key"] == "product_hunt"


def test_connector_stats_api_requires_auth() -> None:
    from fastapi.testclient import TestClient

    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/admin/v1/product/connectors/stats?days=7")
    assert r.status_code in (401, 403, 422)
