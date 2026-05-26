"""Acquire 本地入库验收（mock LLM）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "data" / "_verify_monetization.sqlite3"

SOURCES: tuple[str, ...] = ("acquire",)
SOURCE_META: dict[str, dict[str, str]] = {
    "acquire": {"feed": "apps", "like": "%acquire%"},
}


def _fake_polish(*_a, feed_kind: str = "apps", ref_id: str = "", snippet: str = "", **_k):
    tag = (ref_id or "").strip()[-10:] or "mon"
    desc_summary = f"本地验收描述摘要 {tag}：" + "测" * 60
    desc_body = f"本地验收描述正文 {tag}。\n\n" + "内容" * 80
    data_summary = "数据支撑摘要：" + "指标" * 8
    data_body = "| 指标 | 数值 |\n| --- | --- |\n| 验收 | 通过 |\n" + "补充说明。" * 25
    fk = (feed_kind or "apps").strip().lower()
    if fk not in ("news", "apps"):
        fk = "apps"
    return (
        {
            "title": f"本地验收 {tag}：变现源连接器",
            "summary": desc_summary[:512],
            "body_md": "## 总览\n\n" + desc_body,
            "categories": ["变现案例"],
            "feed_kind": fk,
            "replication_tier": "A",
            "tabs": [
                {"label": "描述", "summary": desc_summary, "body_md": desc_body},
                {"label": "数据支撑", "summary": data_summary, "body_md": data_body},
            ],
        },
        "",
    )


def main() -> int:
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except OSError:
            pass
    os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{DB_PATH.resolve().as_posix()}"
    os.environ["AITRENDS_ENV"] = "dev"
    sys.path.insert(0, str(ROOT))

    from sqlalchemy import desc, func, select

    import backend.app.llm_service as llm_mod
    from backend.app.application import article_public as article_app
    from backend.app.connector_heat_fetch import sync_acquire_top_details, sync_taaft_top_details
    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.domain.articles import parse_connector_sync_item_snippets
    from backend.app.lifespan import _startup_sync
    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import Article, ProductConnector, ProductSyncDiagnosticLog
    from backend.app.routers.admin_extended import run_connector_sync

    ensure_schema_compatibility()
    _startup_sync()

    from scripts.load_local_credentials import UNIFIED_CREDENTIALS, load_llm_credentials, seed_all_local_credentials

    if not UNIFIED_CREDENTIALS.is_file():
        print(f"FAIL: missing {UNIFIED_CREDENTIALS} — run: py -3.12 scripts/merge_local_credentials.py")
        return 1

    print(f"DB: {DB_PATH}")
    print(f"credentials: {UNIFIED_CREDENTIALS}")
    print(f"LLM key: {'set' if load_llm_credentials()[0] else 'NOT SET'}")
    failed = 0
    db = SessionLocal()
    seeded = seed_all_local_credentials(db)
    print(f"seed_all_local_credentials: {seeded}")
    print("-" * 60)
    saved = llm_mod.polish_connector_article
    llm_mod.polish_connector_article = _fake_polish
    try:
        for key in SOURCES:
            print(f"\n=== {key} ===")
            src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
            conn = db.scalar(
                select(ProductConnector).where(ProductConnector.admin_source_key == key).order_by(ProductConnector.id)
            )
            if not src or not conn:
                print(f"  FAIL: missing admin_source or connector (src={bool(src)} conn={bool(conn)})")
                failed += 1
                continue
            src.enabled = True
            conn.enabled = True
            conn.min_interval_seconds = 0
            db.flush()

            url = (src.api_base or "").strip()
            headers = {"User-Agent": "AiTrends-Verify/1.0"}
            if key == "taaft":
                code, body = sync_taaft_top_details(url, headers)
            else:
                code, body = sync_acquire_top_details(url, headers)
            packs = len(parse_connector_sync_item_snippets(body or "") or [])
            print(f"  heat_fetch: HTTP {code} packs={packs}")
            if not (code and 200 <= code < 300 and packs > 0):
                failed += 1
                continue

            out = run_connector_sync(db, conn.id, actor="verify-monetization", bypass_rate_limit=True)
            db.commit()
            err = out.get("error")
            created = int(out.get("articles_created") or 0)
            print(
                f"  ingest: created={created} http={out.get('http_status')} "
                f"rows={out.get('rows_ingested')} err={err!r}"
            )
            if err or created < 1:
                rows = db.scalars(
                    select(ProductSyncDiagnosticLog)
                    .where(ProductSyncDiagnosticLog.source_key == key)
                    .order_by(desc(ProductSyncDiagnosticLog.id))
                    .limit(10)
                ).all()
                for r in rows:
                    if r.level in ("error", "warn") or (r.step or "").startswith("skip"):
                        print(f"    diag {r.step}: {(r.message or '')[:100]}")
                failed += 1
                continue

            art = db.scalar(
                select(Article)
                .where(Article.third_party_source.like(SOURCE_META[key]["like"]), Article.status == "published")
                .order_by(Article.id.desc())
                .limit(1)
            )
            if not art:
                print("  FAIL: no published article")
                failed += 1
                continue

            feed = article_app.list_articles_feed(
                db,
                feed=SOURCE_META[key]["feed"],
                industry_slug="ai",
                segment_id=None,
                segment_ids=None,
                page_size=48,
                cursor=None,
                exclude_fp=None,
                published_within_days=365,
                published_on_latest_day=False,
                category=None,
            )
            ids = {x.get("id") for x in (feed.get("items") or []) if isinstance(x, dict)}
            in_feed = art.id in ids
            print(f"  OK: article_id={art.id} title={(art.title or '')[:60]} in_apps_feed={in_feed}")
            if not in_feed:
                print("  WARN: not in public apps feed (detail may still work)")
    finally:
        llm_mod.polish_connector_article = saved
        db.close()

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED: {failed} source(s)")
        return 1
    print(f"ALL OK: {len(SOURCES)} monetization sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
