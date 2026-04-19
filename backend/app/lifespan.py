"""应用生命周期：建表、种子、调度器（约三天热门快照、异动扫描）。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .admin_auth import ensure_default_admin
from .db import Base, SessionLocal, engine, ensure_schema_compatibility

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _startup_sync() -> None:
    from . import product_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        from .services import ensure_mainstream_admin_sources, seed_if_empty

        seed_if_empty(db)
        ensure_mainstream_admin_sources(db)
        from .product_seed import ensure_product_settings_and_demo_connector, seed_product_if_empty

        seed_product_if_empty(db)
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(db)
        ensure_product_settings_and_demo_connector(db)
        from sqlalchemy import select

        from .hot_service import rebuild_hot_snapshot
        from .product_models import HotSnapshot, Industry

        ind = db.scalar(select(Industry).where(Industry.slug == "ai"))
        if ind and not db.scalar(select(HotSnapshot).where(HotSnapshot.industry_id == ind.id).limit(1)):
            rebuild_hot_snapshot(db, trigger="system")
    finally:
        db.close()


def _job_scheduled_hot() -> None:
    db = SessionLocal()
    try:
        from .hot_service import rebuild_hot_snapshot

        rebuild_hot_snapshot(db, trigger="three_day_cron")
        logger.info("scheduled hot snapshot ok (3-day interval)")
    except Exception as e:
        logger.exception("scheduled hot snapshot failed: %s", e)
    finally:
        db.close()


def _job_anomaly() -> None:
    db = SessionLocal()
    try:
        from .anomaly_service import compute_anomalies

        n = compute_anomalies(db)
        logger.info("anomaly scan created %s events", n)
    except Exception as e:
        logger.exception("anomaly failed: %s", e)
    finally:
        db.close()


def _start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_job_scheduled_hot, IntervalTrigger(days=3), id="hot_snapshot_3d")
    _scheduler.add_job(_job_anomaly, "interval", hours=1, id="hourly_anomaly")
    _scheduler.start()


def _shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@asynccontextmanager
async def app_lifespan(_):
    _startup_sync()
    _start_scheduler()
    yield
    _shutdown_scheduler()
