"""启动清理连接器时须先删 product_connector_logs，避免外键导致进程退出。"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app import models as _admin_models  # noqa: F401 — admin ORM tables for metadata
from backend.app.models import AdminSourceConfig
from backend.app.product_connectors_bootstrap import prune_discontinued_bootstrap_admin_sources
from backend.app.product_models import Base, ProductConnector, ProductConnectorLog

# 历史上已下架、启动时会 prune 的 source（勿用仍在内置预置中的 taaft/acquire）。
_DISCONTINUED_SAMPLE = "mcp_skills"


@pytest.fixture()
def db():
    url = os.getenv("AITRENDS_DATABASE_URL", "sqlite:///./_pytest_connector_prune.db")
    if url.startswith("sqlite:///./_pytest"):
        path = url.replace("sqlite:///", "")
        try:
            os.remove(path)
        except OSError:
            pass
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
    src_key = _DISCONTINUED_SAMPLE
    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == src_key))
    if not src:
        db.add(
            AdminSourceConfig(
                source=src_key,
                preset_label="MCP Skills (legacy)",
                api_base="https://example.com",
                enabled=True,
            )
        )
        db.commit()
    conn = ProductConnector(
        name=f"{src_key}-conn",
        admin_source_key=src_key,
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
    assert db.scalar(select(ProductConnector).where(ProductConnector.admin_source_key == src_key)) is None
    assert db.scalar(select(ProductConnectorLog).where(ProductConnectorLog.connector_id == conn_id)) is None
