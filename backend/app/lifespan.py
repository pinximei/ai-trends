"""应用生命周期：建表、种子、调度器（约三天热门快照、异动扫描、连接器批量同步）。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .admin_auth import ensure_default_admin
from .db import Base, SessionLocal, engine, ensure_schema_compatibility

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _startup_sync() -> None:
    from . import models as _core_site_models  # noqa: F401

    from . import product_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    db = SessionLocal()
    try:
        from .newsletter_settings_service import ensure_newsletter_settings_row
        from .product_settings_seed import seed_product_settings_from_environment
        from .runtime_settings_service import assert_production_security, demo_seed_enabled_effective, refresh_runtime_snapshot
        from .scheduler_settings_service import ensure_scheduler_settings_row

        ensure_scheduler_settings_row(db)
        ensure_newsletter_settings_row(db)
        seed_product_settings_from_environment(db)
        refresh_runtime_snapshot(db)
        assert_production_security()
        ensure_default_admin(db)
        from .services import ensure_mainstream_admin_sources, seed_if_empty, sync_catalog_preset_metadata

        from .product_connectors_bootstrap import (
            ensure_core_admin_connectors,
            prune_disabled_admin_sources,
            prune_discontinued_bootstrap_admin_sources,
            repair_github_admin_source_if_still_zen,
            repair_short_probe_admin_sources,
        )

        prune_discontinued_bootstrap_admin_sources(db)
        prune_disabled_admin_sources(db)
        ensure_mainstream_admin_sources(db)
        sync_catalog_preset_metadata(db)
        repair_github_admin_source_if_still_zen(db)
        repair_short_probe_admin_sources(db)
        ensure_core_admin_connectors(db)
        if demo_seed_enabled_effective():
            seed_if_empty(db)
            from .product_seed import (
                ensure_demo_software_downloads,
                ensure_product_settings_and_demo_connector,
                seed_product_if_empty,
            )

            seed_product_if_empty(db)
            ensure_product_settings_and_demo_connector(db)
            ensure_demo_software_downloads(db)
        from .product_seed import ensure_public_about_page

        ensure_public_about_page(db)
        from .scheduler_settings_service import ensure_scheduler_settings_row

        ensure_scheduler_settings_row(db)
        from .newsletter_settings_service import ensure_newsletter_settings_row
        from .application.newsletter_public import backfill_newsletter_unsubscribe_tokens

        ensure_newsletter_settings_row(db)
        ntok = backfill_newsletter_unsubscribe_tokens(db)
        if ntok:
            logger.info("newsletter: backfilled %s unsubscribe tokens", ntok)
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(db)
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


def _job_connector_sync_gate() -> None:
    """每 15 分钟检查一次：若距上次整批已超过配置的间隔，则同步所有已启用连接器（不受单连接器 min_interval 限制）。"""
    from sqlalchemy import select, text

    from fastapi import HTTPException

    from .db import engine
    from .product_models import ProductConnector
    from .routers.admin_extended import run_connector_sync
    from .scheduler_settings_service import (
        ensure_scheduler_settings_row,
        get_scheduler_settings_merged,
        parse_last_batch_at,
        set_last_connector_batch_at,
    )

    db = SessionLocal()
    locked = False
    try:
        ensure_scheduler_settings_row(db)
        settings = get_scheduler_settings_merged(db)
        if not settings.get("connector_scheduler_enabled", True):
            logger.debug("connector scheduler disabled, skip gate")
            return

        interval_h = max(1, min(168, int(settings.get("connector_sync_interval_hours") or 6)))
        last_dt = parse_last_batch_at(settings.get("last_connector_batch_at"))
        now = datetime.utcnow()
        if last_dt and (now - last_dt).total_seconds() < interval_h * 3600 - 30:
            return

        if getattr(engine.dialect, "name", "") == "postgresql":
            locked = bool(db.execute(text("SELECT pg_try_advisory_lock(928471001)")).scalar())
            if not locked:
                logger.debug("connector batch: advisory lock busy, skip")
                return

        rows = db.scalars(select(ProductConnector).where(ProductConnector.enabled.is_(True)).order_by(ProductConnector.id)).all()
        if not rows:
            logger.info("scheduled connector batch: no enabled connectors")
            return

        ok = 0
        fail = 0
        for r in rows:
            try:
                out = run_connector_sync(db, r.id, actor="system", bypass_rate_limit=True)
                if out.get("error"):
                    fail += 1
                else:
                    ok += 1
            except HTTPException:
                fail += 1
            except Exception:
                fail += 1
                logger.exception("connector sync failed id=%s", r.id)

        try:
            from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

            sync_product_taxonomy_from_admin_sources(db)
        except Exception:
            logger.exception("taxonomy sync after connector batch failed")

        if ok > 0:
            set_last_connector_batch_at(db, now)
            logger.info("scheduled connector batch finished: ok=%s fail=%s total=%s", ok, fail, len(rows))
        else:
            logger.warning(
                "scheduled connector batch: all failed (ok=0), not advancing last_connector_batch_at — will retry on next gate",
            )
    except Exception as e:
        logger.exception("scheduled connector gate failed: %s", e)
    finally:
        if locked and getattr(engine.dialect, "name", "") == "postgresql":
            try:
                db.execute(text("SELECT pg_advisory_unlock(928471001)"))
                db.commit()
            except Exception:
                logger.exception("advisory unlock failed")
        db.close()


def _job_newsletter_daily() -> None:
    db = SessionLocal()
    try:
        from zoneinfo import ZoneInfo

        from .application.newsletter_daily_digest import run_daily_newsletter_digest_job
        from .newsletter_settings_service import get_newsletter_settings_merged

        s = get_newsletter_settings_merged(db)
        if not s.get("daily_digest_job_enabled", True):
            return
        if not s.get("cron_enabled", True):
            return
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        h = int(s.get("daily_hour", 9))
        m = int(s.get("daily_minute", 0))
        slot_start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=5)
        if not (slot_start <= now < slot_end):
            return
        out = run_daily_newsletter_digest_job(db=db, settings=s)
        logger.info("newsletter daily job: %s", out)
    except Exception as e:
        logger.exception("newsletter daily job failed: %s", e)
    finally:
        db.close()


def _start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(_job_scheduled_hot, IntervalTrigger(days=3), id="hot_snapshot_3d")
    _scheduler.add_job(_job_anomaly, "interval", hours=1, id="hourly_anomaly")
    _scheduler.add_job(
        _job_connector_sync_gate,
        IntervalTrigger(minutes=15),
        id="connector_sync_gate",
    )
    _scheduler.add_job(
        _job_newsletter_daily,
        IntervalTrigger(minutes=5),
        id="newsletter_daily_digest",
    )
    logger.info(
        "connector sync gate every 15m; newsletter digest checks every 5m (fires in configured Asia/Shanghai window)",
    )
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
