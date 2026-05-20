"""
单数据源本地门禁：连接器同步 → 入库 → 公开 feed/detail 结构检查。

用法（仓库根目录）:
  py -3.12 scripts/verify_source_local.py --source github
  py -3.12 scripts/verify_source_local.py --source product_hunt
  py -3.12 scripts/verify_source_local.py --source huggingface_spaces
  py -3.12 scripts/verify_source_local.py --source hacker_news
  py -3.12 scripts/verify_source_local.py --source arxiv

通过 exit 0；失败 exit 1–3。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 当前产品内置数据源；新增前须先扩此表并完成本地验收。
VERIFIED_SOURCE_KEYS = frozenset({"github", "product_hunt", "huggingface_spaces", "hacker_news", "arxiv"})

SOURCE_META: dict[str, dict[str, str]] = {
    "github": {
        "feed": "news",
        "like": "%github%",
        "runner": "scripts/run_github_sync_local.py",
    },
    "product_hunt": {
        "feed": "apps",
        "like": "%product_hunt%",
        "runner": "scripts/run_product_hunt_sync_local.py",
    },
    "huggingface_spaces": {
        "feed": "apps",
        "like": "%huggingface%",
        "runner": "scripts/run_huggingface_spaces_sync_local.py",
    },
    "hacker_news": {
        "feed": "news",
        "like": "%hacker_news%",
        "runner": "scripts/run_hacker_news_sync_local.py",
    },
    "arxiv": {
        "feed": "news",
        "like": "%arxiv%",
        "runner": "scripts/run_arxiv_sync_local.py",
    },
}

DATA_TAB_LABELS = frozenset({"数据支撑", "功能亮点", "要点"})


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="单数据源本地验收门禁")
    ap.add_argument(
        "--source",
        required=True,
        choices=sorted(VERIFIED_SOURCE_KEYS),
        help="admin_source_key",
    )
    ap.add_argument(
        "--sqlite",
        nargs="?",
        const=str(ROOT / "backend" / "data" / "dev_local.db"),
        default=None,
        help="SQLite 路径（默认可用 dev_local.db）",
    )
    ap.add_argument("--skip-sync", action="store_true", help="跳过同步，只检查库内最新文章")
    return ap.parse_args()


def _configure_db(sqlite_arg: str | None) -> None:
    if sqlite_arg is None:
        default = ROOT / "backend" / "data" / "dev_local.db"
        if default.is_file():
            sqlite_arg = str(default)
    if sqlite_arg:
        p = Path(sqlite_arg)
        p.parent.mkdir(parents=True, exist_ok=True)
        os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{p.resolve().as_posix()}"


def main() -> int:
    args = _parse_args()
    key = args.source.strip().lower()
    meta = SOURCE_META[key]
    _configure_db(args.sqlite)
    sys.path.insert(0, str(ROOT))

    if not os.environ.get("AITRENDS_LLM_API_KEY", "").strip():
        print("WARN: 未设置 AITRENDS_LLM_API_KEY，同步可能 articles_created=0")
        print("      请配置 Key 后重试，或使用管理端 LLM 设置（需同一数据库）")

    from sqlalchemy import func, select

    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.lifespan import _startup_sync
    from backend.app.product_models import Article, ProductConnector
    from backend.app.routers.admin_extended import run_connector_sync
    from backend.app.application import article_public as article_app

    ensure_schema_compatibility()
    _startup_sync()

    db = SessionLocal()
    try:
        conn = db.scalar(
            select(ProductConnector).where(ProductConnector.admin_source_key == key).order_by(ProductConnector.id)
        )
        if not conn:
            print(f"FAIL: 无连接器 admin_source_key={key}")
            print(f"  先启动后端种子，或运行 {meta['runner']}")
            return 1

        before = db.scalar(
            select(func.count()).select_from(Article).where(Article.third_party_source.like(meta["like"]))
        )

        if not args.skip_sync:
            conn.enabled = True
            conn.min_interval_seconds = 0
            db.flush()
            out = run_connector_sync(db, conn.id, actor="verify-source-gate", bypass_rate_limit=True)
            db.commit()
            print("sync:", {k: out.get(k) for k in ("articles_created", "error", "http_status") if k in out})
            if out.get("error"):
                print("FAIL: sync error", out.get("error"))
                return 2
            created = int(out.get("articles_created") or 0)
            after = db.scalar(
                select(func.count()).select_from(Article).where(Article.third_party_source.like(meta["like"]))
            )
            if created < 1 and (after or 0) <= (before or 0):
                print("FAIL: 未新建文章（检查 LLM Key、价值分、去重）")
                print(f"  可先单独跑: py -3.12 {meta['runner']}")
                return 3

        art = db.scalar(
            select(Article)
            .where(Article.third_party_source.like(meta["like"]), Article.status == "published")
            .order_by(Article.id.desc())
            .limit(1)
        )
        if not art:
            print("FAIL: 无已发布文章")
            return 1

        detail = article_app.get_published_article(db, art.id)
        if not detail:
            print("FAIL: 公开详情为空")
            return 1

        tabs = detail.get("tabs") or []
        labels = [str(t.get("label") or "").strip() for t in tabs if isinstance(t, dict)]
        if "描述" not in labels:
            print("FAIL: tabs 缺少「描述」", labels)
            return 1
        if not DATA_TAB_LABELS.intersection(labels):
            print("FAIL: tabs 缺少数据支撑类 label", labels)
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
        if key in ("product_hunt", "huggingface_spaces") and not cover:
            print("WARN: 无 cover_image_url（部分 Space/帖子无 thumbnail，可接受）")

        print("OK:", key)
        print(f"  article id={art.id} feed={meta['feed']} tabs={labels}")
        print(f"  title={(art.title or '')[:72]}")
        if cover:
            print(f"  cover={cover[:80]}...")
        print(f"  detail_profile={detail.get('detail_profile')}")
        print("  下一步: 浏览器打开 /resources/{id} 与 /{feed} 做人工 UI 验收".format(id=art.id, feed=meta["feed"]))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
