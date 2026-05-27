"""在部署机执行：统计美东「今日」入库/发布文章数。用法: cd /opt/aisoul && . backend/.venv/bin/activate && python scripts/_count_articles_today_remote.py"""
from __future__ import annotations

from sqlalchemy import func, select

from backend.app.db import SessionLocal
from backend.app.product_models import Article, ProductConnectorLog
from backend.app.us_content_calendar import US_TIMEZONE_LABEL, utc_naive_bounds_for_us_date, us_calendar_today


def main() -> None:
    db = SessionLocal()
    try:
        today = us_calendar_today()
        start, end = utc_naive_bounds_for_us_date(today)
        n_created = db.scalar(
            select(func.count()).select_from(Article).where(Article.created_at >= start, Article.created_at < end)
        )
        n_published = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(Article.status == "published", Article.published_at >= start, Article.published_at < end)
        )
        n_new_pub = db.scalar(
            select(func.count())
            .select_from(Article)
            .where(
                Article.status == "published",
                Article.created_at >= start,
                Article.created_at < end,
            )
        )
        sync_sum = db.scalar(
            select(func.coalesce(func.sum(ProductConnectorLog.rows_ingested), 0)).where(
                ProductConnectorLog.started_at >= start,
                ProductConnectorLog.started_at < end,
            )
        )
        sync_runs = db.scalar(
            select(func.count())
            .select_from(ProductConnectorLog)
            .where(ProductConnectorLog.started_at >= start, ProductConnectorLog.started_at < end)
        )
        print(f"calendar={today.isoformat()} ({US_TIMEZONE_LABEL})")
        print(f"utc_window=[{start.isoformat()}Z, {end.isoformat()}Z)")
        print(f"articles_created_today={int(n_created or 0)}")
        print(f"articles_published_at_today={int(n_published or 0)}")
        print(f"articles_created_and_published_today={int(n_new_pub or 0)}")
        print(f"connector_sync_runs_today={int(sync_runs or 0)}")
        print(f"connector_rows_ingested_sum_today={int(sync_sum or 0)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
