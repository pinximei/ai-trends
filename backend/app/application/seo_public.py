from __future__ import annotations

from datetime import datetime, timezone
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..product_models import Article
from ..public_site import resolve_public_site_base_url

# Google 单文件 sitemap 上限 50_000；保留余量给静态页
_MAX_ARTICLE_URLS = 10_000

_STATIC_PATHS: tuple[tuple[str, str, str], ...] = (
    ("/", "daily", "1.0"),
    ("/news", "daily", "0.9"),
    ("/apps", "daily", "0.9"),
    ("/downloads", "weekly", "0.6"),
    ("/about", "monthly", "0.5"),
)


def _url_node(loc: str, *, lastmod: datetime | None, changefreq: str, priority: str) -> str:
    lines = ["  <url>", f"    <loc>{escape(loc)}</loc>"]
    if lastmod is not None:
        lines.append(f"    <lastmod>{lastmod.strftime('%Y-%m-%d')}</lastmod>")
    lines.append(f"    <changefreq>{changefreq}</changefreq>")
    lines.append(f"    <priority>{priority}</priority>")
    lines.append("  </url>")
    return "\n".join(lines)


def build_sitemap_xml(db: Session) -> str:
    base = resolve_public_site_base_url(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    nodes: list[str] = []

    for path, changefreq, priority in _STATIC_PATHS:
        nodes.append(
            _url_node(
                f"{base}{path}",
                lastmod=now,
                changefreq=changefreq,
                priority=priority,
            )
        )

    rows = db.execute(
        select(Article.id, Article.updated_at)
        .where(Article.status == "published")
        .order_by(Article.updated_at.desc(), Article.id.desc())
        .limit(_MAX_ARTICLE_URLS)
    ).all()

    for article_id, updated_at in rows:
        lastmod = updated_at if isinstance(updated_at, datetime) else now
        nodes.append(
            _url_node(
                f"{base}/resources/{article_id}",
                lastmod=lastmod,
                changefreq="weekly",
                priority="0.6",
            )
        )

    body = "\n".join(nodes)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
