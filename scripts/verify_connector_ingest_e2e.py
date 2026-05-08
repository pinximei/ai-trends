"""
本地验证：数据源 HTTP 拉取 → 规则价值分与指纹 →（mock）LLM 润色 → 入库 → 公开文章接口可读。

说明：
- 正式环境必须在管理端或 AISOU_LLM_API_KEY 配置 DeepSeek 等 Key，否则 polish_connector_article 返回 None，文章不会入库（设计如此）。
- 本脚本使用独立 SQLite 文件，并 patch LLM，仅验证链路与数据结构是否合理。

用法（仓库根目录）:
  py -3.12 -m pip install -e .
  py -3.12 scripts/verify_connector_ingest_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "data" / "_verify_e2e.sqlite3"


def _fake_polish(*_a, **_k) -> dict:
    return {
        "title": "验证：连接器同步快照",
        "summary": "本地端到端脚本写入：模拟 LLM 润色后的摘要，用于确认 product_articles 与公开 feed 接口字段一致。",
        "body_md": "## 验证\n\n占位正文；生产环境为模型根据原始片段重写。",
        "categories": ["大模型", "开源", "算力", "论文", "基准", "推理", "生态", "多模态"],
        "feed_kind": "news",
        "tabs": [
            {
                "label": "要点",
                "summary": "从数据源 HTTP 响应提炼的结构化要点（脚本占位）。",
                "body_md": "- 拉取成功\n- 规则价值分通过阈值\n- 已写入 product_articles",
            },
            {
                "label": "说明",
                "summary": "本段由验证脚本注入，不代表真实模型输出。",
                "body_md": "配置 AISOU_LLM_API_KEY 后，此处为 DeepSeek 等对原始 JSON 的重写与分 tab。",
            },
        ],
    }


def main() -> int:
    if DB_PATH.exists():
        DB_PATH.unlink()

    # 必须在任何 backend 导入之前，避免 backend/.env 里的 PostgreSQL 覆盖本脚本的库。
    os.environ["AISOU_DATABASE_URL"] = f"sqlite:///{DB_PATH.resolve().as_posix()}"
    os.environ["AISOU_ENV"] = "dev"
    sys.path.insert(0, str(ROOT))

    from unittest.mock import patch

    from backend.app.db import SessionLocal
    from backend.app.lifespan import _startup_sync
    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import Article, ProductConnector
    from backend.app.routers.admin_extended import run_connector_sync
    from backend.app.application import article_public as article_app

    _startup_sync()

    db = SessionLocal()
    try:
        src = db.query(AdminSourceConfig).filter(AdminSourceConfig.source == "product_hunt").one_or_none()
        if not src:
            print("FAIL: mainstream seed missing product_hunt admin_source")
            return 1
        src.api_base = "https://httpbin.org/get"
        src.enabled = True
        db.commit()

        conn = db.query(ProductConnector).order_by(ProductConnector.id).first()
        if not conn:
            print("FAIL: no product_connectors row")
            return 1
        conn.enabled = True
        conn.admin_source_key = "product_hunt"
        conn.min_interval_seconds = 0
        db.commit()

        with patch("backend.app.llm_service.polish_connector_article", new=_fake_polish):
            out = run_connector_sync(db, conn.id, actor="verify-script", bypass_rate_limit=True)

        if out.get("error"):
            print("FAIL run_connector_sync:", out)
            return 1
        if int(out.get("articles_created") or 0) < 1:
            print("FAIL: expected articles_created >= 1, got:", out)
            return 1

        art = db.query(Article).order_by(Article.id.desc()).first()
        if not art or art.status != "published":
            print("FAIL: no published article")
            return 1

        # product_hunt 归入「AI 应用」泳道
        feed = article_app.list_articles_feed(
            db,
            feed="apps",
            industry_slug="ai",
            segment_id=None,
            segment_ids=None,
            page_size=24,
            cursor=None,
            exclude_fp=None,
            published_within_days=None,
            published_on_latest_day=False,
            category=None,
        )
        items = (feed.get("items") or []) if isinstance(feed, dict) else []
        ids = {x.get("id") for x in items if isinstance(x, dict)}
        if art.id not in ids:
            print("FAIL: new article not in public feed items", art.id, "feed=", feed)
            return 1
        print("OK: article id", art.id, "present in public feed (apps lane for product_hunt)")

        d = article_app.get_published_article(db, art.id)
        assert d
        tabs = d.get("tabs")
        if not isinstance(tabs, list) or len(tabs) < 2:
            print("FAIL: public article detail tabs invalid", json.dumps(d, ensure_ascii=False)[:400])
            return 1
        print("OK: public detail title=", (d.get("title") or "")[:60])
        print("connector_sync:", json.dumps(out, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
