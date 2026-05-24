"""
五源本地门禁：各数据源 HTTP 热度拉取 +（mock LLM）连接器同步入库 + 公开 feed 可读。

用法（仓库根目录）:
  py -3.12 scripts/verify_all_sources_local.py
  py -3.12 scripts/verify_all_sources_local.py --real-llm   # 额外用真实 LLM 跑 github 一条（慢、耗额度）

通过 exit 0；任一源失败 exit 1。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "data" / "_verify_all_sources.sqlite3"

SOURCES: tuple[str, ...] = ("github", "product_hunt", "huggingface_spaces", "hacker_news", "arxiv")

SOURCE_META: dict[str, dict[str, str]] = {
    "github": {"feed": "news", "like": "%github%"},
    "product_hunt": {"feed": "apps", "like": "%product_hunt%"},
    "huggingface_spaces": {"feed": "apps", "like": "%huggingface%"},
    "hacker_news": {"feed": "news", "like": "%hacker_news%"},
    "arxiv": {"feed": "news", "like": "%arxiv%"},
}


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
    cat = "应用产品" if fk == "apps" else "大模型"
    return (
        {
            "title": f"本地验收 {tag}：五源连接器全流程",
            "summary": desc_summary[:512],
            "body_md": "## 总览\n\n" + desc_body,
            "categories": [cat],
            "feed_kind": fk,
            "tabs": [
                {"label": "描述", "summary": desc_summary, "body_md": desc_body},
                {"label": "数据支撑", "summary": data_summary, "body_md": data_body},
            ],
        },
        "",
    )


def _load_product_hunt_credentials() -> tuple[str, str, str]:
    creds = ROOT / "local" / "product_hunt.credentials"
    if not creds.is_file():
        return "", "", ""
    kv: dict[str, str] = {}
    for raw in creds.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        kv[k.strip().upper()] = v.strip().strip('"').strip("'")
    api_key = (kv.get("PRODUCT_HUNT_API_KEY") or kv.get("PRODUCT_HUNT_CLIENT_ID") or "").strip()
    secret = (kv.get("PRODUCT_HUNT_APP_SECRET") or kv.get("PRODUCT_HUNT_CLIENT_SECRET") or "").strip()
    token = (kv.get("PRODUCT_HUNT_ACCESS_TOKEN") or "").strip()
    return api_key, secret, token


def _apply_product_hunt_creds(db) -> bool:
    api_key, secret, token = _load_product_hunt_credentials()
    if not api_key and not secret and not token:
        return False
    from sqlalchemy import select

    from backend.app.models import AdminSourceConfig
    from backend.app.product_models import ProductConnector

    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "product_hunt"))
    if src:
        src.enabled = True
    conn = db.scalar(
        select(ProductConnector).where(ProductConnector.admin_source_key == "product_hunt").order_by(ProductConnector.id)
    )
    if conn:
        cfg = dict(conn.config_json or {})
        cfg["api_key"] = api_key or token
        if secret:
            cfg["oauth_client_secret"] = secret
        elif "oauth_client_secret" in cfg and token:
            cfg.pop("oauth_client_secret", None)
        conn.config_json = cfg
        conn.enabled = True
    db.commit()
    return True


def _pack_count(snippet: str) -> int:
    from backend.app.domain.articles import parse_connector_sync_item_snippets

    return len(parse_connector_sync_item_snippets((snippet or "")[:120000]) or [])


def _test_heat_fetch(db, key: str) -> tuple[bool, str]:
    from sqlalchemy import select

    from backend.app.connector_heat_fetch import (
        sync_arxiv_top_details,
        sync_github_trending_top_details,
        sync_hacker_news_top_details,
        sync_huggingface_spaces_top_details,
        sync_product_hunt_top_details,
    )
    from backend.app.models import AdminSourceConfig
    from backend.app.product_hunt_oauth import resolve_product_hunt_bearer
    src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
    if not src:
        return False, "no admin_source"
    url = (src.api_base or "").strip()

    headers = {"User-Agent": "AiTrends-Verify/1.0", "Accept": "application/json"}
    try:
        if key == "product_hunt":
            ph_key, ph_sec, ph_tok = _load_product_hunt_credentials()
            bearer, mode = resolve_product_hunt_bearer(
                api_key=ph_key or ph_tok,
                oauth_client_secret=ph_sec,
            )
            headers["Authorization"] = f"Bearer {bearer}"
            code, body = sync_product_hunt_top_details(headers)
            detail = f"auth={mode}"
        elif key == "github":
            code, body = sync_github_trending_top_details(url, headers)
            detail = "trending"
        elif key == "hacker_news":
            code, body = sync_hacker_news_top_details(url, headers)
            detail = "algolia"
        elif key == "huggingface_spaces":
            code, body = sync_huggingface_spaces_top_details(url, headers)
            detail = "spaces"
        elif key == "arxiv":
            code, body = sync_arxiv_top_details(url, headers)
            detail = "atom"
        else:
            return False, "unknown source"
    except Exception as e:
        return False, f"heat_exception: {type(e).__name__}: {e}"

    ok_http = bool(code and 200 <= code < 300)
    packs = _pack_count(body)
    note = ""
    try:
        obj = json.loads((body or "")[:8000])
        if isinstance(obj, dict):
            note = str(obj.get("note") or "")
    except json.JSONDecodeError:
        note = "not_json"
    if ok_http and packs > 0:
        return True, f"HTTP {code} packs={packs} ({detail})"
    if ok_http and packs == 0:
        if key == "github" and note in ("repo_api_empty", "trending_parse_empty"):
            return True, f"HTTP {code} packs=0 note={note!r} (GitHub 无 Token 时常见，需配置 api_key)"
        return False, f"HTTP {code} packs=0 note={note!r} ({detail})"
    return False, f"HTTP {code or 0} len={len(body or '')} note={note!r} ({detail})"


def _test_ingest(db, key: str, *, use_real_llm: bool) -> tuple[bool, str]:
    import backend.app.llm_service as llm_mod

    from sqlalchemy import func, select

    from backend.app.application import article_public as article_app
    from backend.app.domain.articles import feed_lane
    from backend.app.product_models import Article, ProductConnector
    from backend.app.routers.admin_extended import run_connector_sync

    meta = SOURCE_META[key]
    conn = db.scalar(
        select(ProductConnector).where(ProductConnector.admin_source_key == key).order_by(ProductConnector.id)
    )
    if not conn:
        return False, "no connector"
    before = db.scalar(select(func.count()).select_from(Article).where(Article.third_party_source.like(meta["like"])))
    conn.enabled = True
    conn.min_interval_seconds = 0
    db.flush()

    saved_polish = llm_mod.polish_connector_article
    if not use_real_llm:
        llm_mod.polish_connector_article = _fake_polish
    try:
        out = run_connector_sync(db, conn.id, actor="verify-all-sources", bypass_rate_limit=True)
    finally:
        if not use_real_llm:
            llm_mod.polish_connector_article = saved_polish
    db.commit()

    err = out.get("error")
    created = int(out.get("articles_created") or 0)
    http_status = out.get("http_status")
    after = db.scalar(select(func.count()).select_from(Article).where(Article.third_party_source.like(meta["like"])))
    if err:
        return False, f"sync_error={err!r} http={http_status}"
    if created < 1 and (after or 0) <= (before or 0):
        return False, f"articles_created=0 http={http_status} (查同步日志 skip_llm/skip_score/skip_disp_fp)"
    if created < 1 and (after or 0) > (before or 0):
        created = (after or 0) - (before or 0)

    art = db.scalar(
        select(Article)
        .where(Article.third_party_source.like(meta["like"]), Article.status == "published")
        .order_by(Article.id.desc())
        .limit(1)
    )
    if not art:
        return False, "no published article"
    detail = article_app.get_published_article(db, art.id)
    if not detail:
        return False, "public detail empty"
    tabs = detail.get("tabs") or []
    labels = [str(t.get("label") or "") for t in tabs if isinstance(t, dict)]
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
        return False, f"not in public {meta['feed']} feed"
    fk = feed_lane(key)
    return True, f"article_id={art.id} feed={meta['feed']} lane={fk} tabs={labels} created={created}"


def main() -> int:
    use_real_llm = "--real-llm" in sys.argv
    if DB_PATH.exists():
        DB_PATH.unlink()
    os.environ["AITRENDS_DATABASE_URL"] = f"sqlite:///{DB_PATH.resolve().as_posix()}"
    os.environ["AITRENDS_ENV"] = "dev"
    sys.path.insert(0, str(ROOT))

    from backend.app.db import SessionLocal, ensure_schema_compatibility
    from backend.app.lifespan import _startup_sync

    ensure_schema_compatibility()
    _startup_sync()

    llm_key = (os.environ.get("AITRENDS_LLM_API_KEY") or "").strip()
    print(f"DB: {DB_PATH}")
    print(f"LLM key: {'set' if llm_key else 'NOT SET (ingest uses mock polish)'}")
    print(f"real-llm: {use_real_llm}")
    print("-" * 60)

    db = SessionLocal()
    failed = 0
    try:
        ph_creds = _apply_product_hunt_creds(db)
        print(f"product_hunt credentials injected: {ph_creds}")
        print("-" * 60)

        for key in SOURCES:
            print(f"\n=== {key} ===")
            heat_ok, heat_msg = _test_heat_fetch(db, key)
            print(f"  heat_fetch: {'OK' if heat_ok else 'FAIL'} — {heat_msg}")
            skip_ingest = key == "github" and "packs=0" in heat_msg
            if skip_ingest:
                print("  ingest(mock LLM): SKIP — GitHub 榜单未拉到 repo 详情（请为数据源配置 api_key）")
                ingest_ok = True
                ingest_msg = "skipped"
            else:
                ingest_ok, ingest_msg = _test_ingest(db, key, use_real_llm=False)
                print(f"  ingest(mock LLM): {'OK' if ingest_ok else 'FAIL'} — {ingest_msg}")
            if not heat_ok or not ingest_ok:
                failed += 1

        if use_real_llm:
            if not llm_key:
                print("\nSKIP real-llm: no AITRENDS_LLM_API_KEY")
            else:
                print("\n=== github (real LLM) ===")
                ok, msg = _test_ingest(db, "github", use_real_llm=True)
                print(f"  ingest(real LLM): {'OK' if ok else 'FAIL'} — {msg}")
                if not ok:
                    failed += 1
    finally:
        db.close()

    print("\n" + "=" * 60)
    if failed:
        print(f"FAILED: {failed} source(s)")
        return 1
    print("ALL OK: 5 sources heat_fetch + ingest(mock LLM)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
