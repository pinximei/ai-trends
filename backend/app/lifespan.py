"""应用生命周期：建表、种子、调度器（约三天热门快照、异动扫描、连接器批量同步）。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .admin_auth import ensure_default_admin
from .db import Base, SessionLocal, engine, ensure_schema_compatibility

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _startup_sync() -> None:
    import time

    from . import models as _core_site_models  # noqa: F401

    from . import product_models  # noqa: F401

    t0 = time.perf_counter()
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        raise RuntimeError(
            "无法连接数据库。请确认 PostgreSQL 已启动（如 docker compose up -d），"
            "且 backend/.env 中 AITRENDS_DATABASE_URL / AISOU_DB_URL_TEST 正确。"
        ) from e
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
        from .services import ensure_mainstream_admin_sources, repair_mainstream_fetch_limits, seed_if_empty, sync_catalog_preset_metadata

        from .product_connectors_bootstrap import (
            enable_auto_pull_admin_sources_and_connectors,
            ensure_core_admin_connectors,
            prune_admin_sources_outside_mainstream,
            prune_disabled_admin_sources,
            prune_discontinued_bootstrap_admin_sources,
            repair_connector_urls_from_admin_sources,
            repair_github_admin_source_if_still_zen,
            repair_mainstream_heat_fetch_admin_sources,
            repair_short_probe_admin_sources,
        )

        t_prune = time.perf_counter()
        pr = prune_discontinued_bootstrap_admin_sources(db)
        if any(pr.values()):
            logger.debug("startup: pruned discontinued sources %s", pr)
        prune_admin_sources_outside_mainstream(db)
        prune_disabled_admin_sources(db)
        ensure_mainstream_admin_sources(db)
        sync_catalog_preset_metadata(db)
        n_fl = repair_mainstream_fetch_limits(db)
        if n_fl:
            logger.debug("startup: repaired mainstream fetch_limit rows=%s", n_fl)
        repair_github_admin_source_if_still_zen(db)
        repair_mainstream_heat_fetch_admin_sources(db)
        repair_short_probe_admin_sources(db)
        ensure_core_admin_connectors(db)
        from .product_connectors_bootstrap import (
            migrate_legacy_thenewsapi_scheduler_to_source,
            repair_custom_sync_connector_intervals,
        )

        migrate_legacy_thenewsapi_scheduler_to_source(db)
        repair_custom_sync_connector_intervals(db)
        repair_connector_urls_from_admin_sources(db)
        enable_auto_pull_admin_sources_and_connectors(db)
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
            logger.debug("newsletter: backfilled %s unsubscribe tokens", ntok)
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(db)
        from sqlalchemy import select

        from .hot_service import rebuild_hot_snapshot
        from .product_models import HotSnapshot, Industry

        ind = db.scalar(select(Industry).where(Industry.slug == "ai"))
        if ind and not db.scalar(select(HotSnapshot).where(HotSnapshot.industry_id == ind.id).limit(1)):
            rebuild_hot_snapshot(db, trigger="system")
        logger.info("startup: finished (%.1fs)", time.perf_counter() - t0)
    finally:
        db.close()


def _job_scheduled_hot() -> None:
    db = SessionLocal()
    try:
        from .hot_service import rebuild_hot_snapshot

        rebuild_hot_snapshot(db, trigger="three_day_cron")
    except Exception as e:
        logger.exception("scheduled hot snapshot failed: %s", e)
    finally:
        db.close()


def _job_anomaly() -> None:
    db = SessionLocal()
    try:
        from .anomaly_service import compute_anomalies

        compute_anomalies(db)
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
        CONNECTOR_SCHEDULER_TZ,
        connector_batch_due_now,
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
        now_local = datetime.now(CONNECTOR_SCHEDULER_TZ)
        if not connector_batch_due_now(interval_hours=interval_h, last_batch_at=last_dt, now=now_local):
            return

        if getattr(engine.dialect, "name", "") == "postgresql":
            locked = bool(db.execute(text("SELECT pg_try_advisory_lock(928471001)")).scalar())
            if not locked:
                logger.debug("connector batch: advisory lock busy, skip")
                return

        from .models import AdminSourceConfig

        rows = db.scalars(select(ProductConnector).where(ProductConnector.enabled.is_(True)).order_by(ProductConnector.id)).all()
        if not rows:
            return

        custom_keys: set[str] = set()
        for cfg in db.scalars(
            select(AdminSourceConfig).where(AdminSourceConfig.custom_sync_enabled.is_(True))
        ).all():
            custom_keys.add((cfg.source or "").strip().lower())

        ok = 0
        fail = 0
        for r in rows:
            ask = (r.admin_source_key or "").strip().lower()
            if ask and ask in custom_keys:
                continue
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
            set_last_connector_batch_at(db, datetime.utcnow())
            if fail > 0:
                logger.warning("scheduled connector batch: ok=%s fail=%s total=%s", ok, fail, len(rows))
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


def _job_custom_source_sync_gate() -> None:
    """数据源卡片开启「单独同步」的源：按各自间隔小时拉取，不参与整批 EOD。"""
    from sqlalchemy import select, text

    from fastapi import HTTPException

    from .connector_sync_policy import clamp_custom_sync_interval_hours, custom_source_batch_due_now
    from .db import engine
    from .models import AdminSourceConfig
    from .product_models import ProductConnector
    from .routers.admin_extended import run_connector_sync
    from .scheduler_settings_service import (
        ensure_scheduler_settings_row,
        get_last_custom_source_batch_at,
        get_scheduler_settings_merged,
        set_last_custom_source_batch_at,
    )

    db = SessionLocal()
    locked = False
    try:
        ensure_scheduler_settings_row(db)
        settings = get_scheduler_settings_merged(db)
        if not settings.get("connector_scheduler_enabled", True):
            return

        now_utc = datetime.now(timezone.utc)
        due_rows: list[AdminSourceConfig] = []
        for cfg in db.scalars(
            select(AdminSourceConfig).where(
                AdminSourceConfig.enabled.is_(True),
                AdminSourceConfig.custom_sync_enabled.is_(True),
            )
        ).all():
            sk = (cfg.source or "").strip().lower()
            if not sk:
                continue
            interval_h = clamp_custom_sync_interval_hours(cfg.custom_sync_interval_hours)
            last_dt = get_last_custom_source_batch_at(settings, sk)
            if custom_source_batch_due_now(interval_hours=interval_h, last_batch_at=last_dt, now=now_utc):
                due_rows.append(cfg)
        if not due_rows:
            return

        if getattr(engine.dialect, "name", "") == "postgresql":
            locked = bool(db.execute(text("SELECT pg_try_advisory_lock(928471002)")).scalar())
            if not locked:
                logger.debug("custom-source connector batch: advisory lock busy, skip")
                return

        for cfg in due_rows:
            sk = cfg.source
            rows = db.scalars(
                select(ProductConnector)
                .where(
                    ProductConnector.enabled.is_(True),
                    ProductConnector.admin_source_key == sk,
                )
                .order_by(ProductConnector.id)
            ).all()
            if not rows:
                continue
            ok = 0
            for r in rows:
                try:
                    out = run_connector_sync(db, r.id, actor="system_custom_sync", bypass_rate_limit=True)
                    if out.get("error"):
                        logger.warning(
                            "custom sync %s connector #%s failed: %s",
                            sk,
                            r.id,
                            out.get("error"),
                        )
                    else:
                        ok += 1
                        logger.info(
                            "custom sync %s connector #%s ok articles_created=%s",
                            sk,
                            r.id,
                            out.get("articles_created"),
                        )
                except HTTPException:
                    logger.warning("custom sync %s connector #%s HTTPException", sk, r.id)
                except Exception:
                    logger.exception("custom sync failed source=%s id=%s", sk, r.id)
            if ok > 0:
                set_last_custom_source_batch_at(db, sk, datetime.utcnow())
    except Exception as e:
        logger.exception("custom-source connector gate failed: %s", e)
    finally:
        if locked and getattr(engine.dialect, "name", "") == "postgresql":
            try:
                db.execute(text("SELECT pg_advisory_unlock(928471002)"))
                db.commit()
            except Exception:
                logger.exception("custom-source advisory unlock failed")
        db.close()


def _job_newsletter_daily() -> None:
    db = SessionLocal()
    try:
        from .application.newsletter_daily_digest import run_daily_newsletter_digest_job
        from .newsletter_settings_service import get_newsletter_settings_merged
        from .us_content_calendar import US_CONTENT_TZ

        s = get_newsletter_settings_merged(db)
        if not s.get("daily_digest_job_enabled", True):
            return
        if not s.get("cron_enabled", True):
            return
        now = datetime.now(US_CONTENT_TZ)
        h = int(s.get("daily_hour", 9))
        m = int(s.get("daily_minute", 0))
        slot_start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        slot_end = slot_start + timedelta(minutes=5)
        if not (slot_start <= now < slot_end):
            return
        run_daily_newsletter_digest_job(db=db, settings=s)
    except Exception as e:
        logger.exception("newsletter daily job failed: %s", e)
    finally:
        db.close()


def _start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone="America/New_York")
    _scheduler.add_job(_job_scheduled_hot, IntervalTrigger(days=3), id="hot_snapshot_3d")
    _scheduler.add_job(_job_anomaly, "interval", hours=1, id="hourly_anomaly")
    _scheduler.add_job(
        _job_connector_sync_gate,
        IntervalTrigger(minutes=15),
        id="connector_sync_gate",
    )
    _scheduler.add_job(
        _job_custom_source_sync_gate,
        IntervalTrigger(minutes=15),
        id="custom_source_sync_gate",
    )
    _scheduler.add_job(
        _job_newsletter_daily,
        IntervalTrigger(minutes=5),
        id="newsletter_daily_digest",
    )
    _scheduler.start()


def _shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


@asynccontextmanager
async def app_lifespan(_):
    try:
        _startup_sync()
    except Exception:
        logger.exception("application startup failed")
        raise
    _start_scheduler()
    yield
    _shutdown_scheduler()
