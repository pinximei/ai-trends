import sys

sys.path.insert(0, "/opt/aisoul")
from sqlalchemy import select

from backend.app.application.newsletter_daily_digest import fetch_articles_for_shanghai_day_split
from backend.app.db import SessionLocal
from backend.app.models import NewsletterDailyDigest
from backend.app.us_content_calendar import us_calendar_today

k = us_calendar_today().isoformat()
db = SessionLocal()
try:
    d = __import__("datetime").date.fromisoformat(k)
    apps, news = fetch_articles_for_shanghai_day_split(db, d, apps_limit=12, news_limit=12)
    print("digest_date", k)
    print("apps_pool", len(apps), "news_pool", len(news))
    row = db.scalar(select(NewsletterDailyDigest).where(NewsletterDailyDigest.digest_date == k))
    if row:
        print("status", row.status, "body_len", len(row.body_md or ""))
        print("subject", row.subject)
        print("body_preview", (row.body_md or "")[:800])
finally:
    db.close()
