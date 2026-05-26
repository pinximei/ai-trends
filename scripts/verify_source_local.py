"""
单数据源本地门禁：连接器同步 → 入库 → 公开 feed/detail 结构检查。

用法（仓库根目录）:
  py -3.12 scripts/verify_source_local.py --source github
  py -3.12 scripts/verify_source_local.py --source product_hunt
  py -3.12 scripts/verify_source_local.py --source hacker_news
  py -3.12 scripts/verify_source_local.py --source newsapi
  py -3.12 scripts/verify_source_local.py --source thenewsapi
  py -3.12 scripts/verify_source_local.py --source acquire

新闻源密钥：``local/newsapi.credentials`` / ``local/thenewsapi.credentials``（见 example）。

通过 exit 0；失败 exit 1–3。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "data" / "_verify_source_local.sqlite3"

VERIFIED_SOURCE_KEYS = frozenset(
    {"github", "product_hunt", "hacker_news", "newsapi", "thenewsapi", "acquire"}
)

SOURCE_META: dict[str, dict[str, str]] = {
    "github": {
        "feed": "apps",
        "like": "%github%",
        "runner": "scripts/run_github_sync_local.py",
    },
    "product_hunt": {
        "feed": "apps",
        "like": "%product_hunt%",
        "runner": "scripts/run_product_hunt_sync_local.py",
    },
    "hacker_news": {
        "feed": "news",
        "like": "%hacker_news%",
        "runner": "scripts/run_hacker_news_sync_local.py",
    },
    "newsapi": {
        "feed": "news",
        "like": "%newsapi%",
        "runner": "",
    },
    "thenewsapi": {
        "feed": "news",
        "like": "%thenewsapi%",
        "runner": "",
    },
    "acquire": {
        "feed": "apps",
        "like": "%acquire%",
        "runner": "",
    },
}

DATA_TAB_LABELS = frozenset({"数据支撑", "功能亮点", "要点"})


def _fake_polish(
    *_a,
    feed_kind: str = "news",
    ref_id: str = "",
    snippet: str = "",
    **_k,
) -> tuple[dict, str]:
    tag = (ref_id or "").strip()[-10:] or str(abs(hash((snippet or "")[:200])))[-8:]
    desc_summary = f"本地验收描述摘要 {tag}：" + "测" * 60
    desc_body = f"本地验收描述正文 {tag}。\n\n" + "内容" * 80
    data_summary = "数据支撑摘要：" + "指标" * 8
    data_body = "| 指标 | 数值 |\n| --- | --- |\n| 验收 | 通过 |\n" + "补充说明。" * 25
    fk = (feed_kind or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    cat = "应用产品" if fk == "apps" else "模型层(谨慎)"
    return (
        {
            "title": f"本地验收 {tag}：连接器全流程",
            "summary": desc_summary[:512],
            "body_md": "## 总览\n\n" + desc_body,
            "categories": [cat],
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--real-llm", action="store_true", help="使用真实 LLM（耗额度）；默认 mock 润色")
    args = ap.parse_args()
    key = (args.source or "").strip().lower()
    if key not in VERIFIED_SOURCE_KEYS:
        print(f"FAIL: unknown source {key!r}; allowed: {sorted(VERIFIED_SOURCE_KEYS)}")
        return 2

    os.environ.setdefault("AITRENDS_ENV", "dev")
    if not (os.environ.get("AITRENDS_DATABASE_URL") or "").strip():
        if DB_PATH.exists():
            try:
                DB_PATH.unlink()
            except OSError:
                pass
        os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{DB_PATH.resolve().as_posix()}"
    sys.path.insert(0, str(ROOT))

    from sqlalchemy import select

    import backend.app.llm_service as llm_mod

    from backend.app.application import article_public as article_app
    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.lifespan import _startup_sync
    from backend.app.product_models import Article, ProductConnector
    from backend.app.routers.admin_extended import run_connector_sync

    ensure_schema_compatibility()
    _startup_sync()

    print(f"DB: {os.environ.get('AITRENDS_DATABASE_URL', '')}")

    from scripts.load_local_credentials import (
        apply_newsapi_credentials,
        apply_product_hunt_credentials,
        apply_thenewsapi_credentials,
        load_newsapi_credentials,
        load_thenewsapi_credentials,
    )

    meta = SOURCE_META[key]
    db = SessionLocal()
    try:
        apply_product_hunt_credentials(db)
        if key == "newsapi":
            if not load_newsapi_credentials():
                print("FAIL: no key — copy local/newsapi.credentials.example -> newsapi.credentials")
                return 2
            apply_newsapi_credentials(db)
        elif key == "thenewsapi":
            if not load_thenewsapi_credentials():
                print("FAIL: no token — copy local/thenewsapi.credentials.example -> thenewsapi.credentials")
                return 2
            apply_thenewsapi_credentials(db)

        conn = db.scalar(
            select(ProductConnector).where(ProductConnector.admin_source_key == key).order_by(ProductConnector.id)
        )
        if not conn:
            print(f"FAIL: no connector for {key}")
            return 1
        conn.enabled = True
        conn.min_interval_seconds = 0
        db.flush()

        use_real_llm = bool(args.real_llm)
        saved_polish = llm_mod.polish_connector_article
        if not use_real_llm:
            llm_mod.polish_connector_article = _fake_polish
        try:
            out = run_connector_sync(db, conn.id, actor="verify-source-local", bypass_rate_limit=True)
        finally:
            if not use_real_llm:
                llm_mod.polish_connector_article = saved_polish
        db.commit()
        if out.get("error"):
            print(f"FAIL: sync {out.get('error')!r}")
            return 1
        if int(out.get("articles_created") or 0) < 1:
            print(
                f"FAIL: articles_created=0 http={out.get('http_status')} "
                f"rows={out.get('rows_ingested')} (无 LLM Key 时应已 mock；查同步日志)"
            )
            return 1
        art = db.scalar(
            select(Article)
            .where(Article.third_party_source.like(meta["like"]), Article.status == "published")
            .order_by(Article.id.desc())
            .limit(1)
        )
        if not art:
            print("FAIL: no published article after sync")
            return 1
        detail = article_app.get_published_article(db, art.id)
        if not detail:
            print("FAIL: public detail empty")
            return 1
        tabs = detail.get("tabs") or []
        labels = [str(t.get("label") or "") for t in tabs if isinstance(t, dict)]
        if "描述" not in labels:
            print(f"FAIL: tabs missing 描述: {labels}")
            return 1
        if not any(l in DATA_TAB_LABELS for l in labels):
            print(f"FAIL: tabs missing data tab: {labels}")
            return 1
        feed = article_app.list_articles_feed(
            db,
            feed=meta["feed"],
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
        if art.id not in ids:
            print(f"FAIL: 文章 {art.id} 不在公开 {meta['feed']} feed 中")
            return 1

        cover = (detail.get("cover_image_url") or "").strip()
        if key == "product_hunt" and not cover:
            print("WARN: 无 cover_image_url（部分帖子无 thumbnail，可接受）")

        print("OK:", key)
        print(f"  article id={art.id} feed={meta['feed']} tabs={labels}")
        print(f"  title={(art.title or '')[:72]}")
        if cover:
            print(f"  cover={cover[:80]}...")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
