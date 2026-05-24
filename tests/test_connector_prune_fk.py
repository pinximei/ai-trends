"""启动清理连接器时须先删 product_connector_logs，避免外键导致进程退出。"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.models import AdminSourceConfig
from backend.app.product_connectors_bootstrap import prune_discontinued_bootstrap_admin_sources
from backend.app.product_models import Base, ProductConnector, ProductConnectorLog


@pytest.fixture()
def db():
    url = os.getenv("AITRENDS_DATABASE_URL", "sqlite:///./_pytest_connector_prune.db")
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        if url.startswith("sqlite:///./_pytest"):
            try:
                os.remove(url.replace("sqlite:///", ""))
            except OSError:
                pass


def test_prune_discontinued_deletes_connector_logs_before_connectors(db) -> None:
    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "taaft"))
    if not src:
        db.add(
            AdminSourceConfig(
                source="taaft",
                preset_label="TAAFT",
                api_base="https://example.com",
                enabled=True,
            )
        )
        db.commit()
    conn = ProductConnector(
        name="taaft-conn",
        admin_source_key="taaft",
        config_json={"url": "https://example.com"},
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    db.add(
        ProductConnectorLog(
            connector_id=conn.id,
            status="ok",
            rows_ingested=1,
        )
    )
    db.commit()
    conn_id = conn.id

    out = prune_discontinued_bootstrap_admin_sources(db)
    assert out["connectors_deleted"] >= 1
    assert db.scalar(select(ProductConnector).where(ProductConnector.admin_source_key == "taaft")) is None
    assert db.scalar(select(ProductConnectorLog).where(ProductConnectorLog.connector_id == conn_id)) is None
