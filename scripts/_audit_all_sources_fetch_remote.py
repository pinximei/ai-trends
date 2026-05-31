"""生产机：逐源检查热度拉取 pack 与上游门槛（不打印密钥）。"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path


def _load_db_url_from_systemd(unit: str = "aisoul-backend", *, force: bool = True) -> None:
    if os.environ.get("AITRENDS_DATABASE_URL", "").strip() and not force:
        return
    marker = "AITRENDS_DATABASE_URL="
    for path in (f"/etc/systemd/system/{unit}.service", f"/lib/systemd/system/{unit}.service"):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if marker in line:
                os.environ["AITRENDS_DATABASE_URL"] = line[line.index(marker) + len(marker) :].strip()
                return
    try:
        raw = subprocess.check_output(
            ["systemctl", "show", unit, "-p", "Environment", "--value"],
            text=True,
            timeout=10,
        )
        for part in raw.split():
            if part.startswith(marker):
                os.environ["AITRENDS_DATABASE_URL"] = part.split("=", 1)[1]
                return
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass


_load_db_url_from_systemd(force=True)

from sqlalchemy import desc, select

from backend.app.db import SessionLocal
from backend.app.models import AdminSourceConfig
from backend.app.product_models import ProductConnector, ProductConnectorLog, ProductSyncDiagnosticLog
from backend.app.product_connectors_bootstrap import build_connector_sync_request_cfg, mainstream_heat_fetch_url_ok
from backend.app.routers.admin_extended import _run_connector_request, _snippet_pack_diag
from backend.app.domain.articles import (
    connector_upstream_has_ingest_material,
    connector_upstream_material_char_count,
    parse_connector_sync_item_snippets,
)


def main() -> None:
    if not os.environ.get("AITRENDS_DATABASE_URL", "").strip():
        print("ERROR: no DATABASE_URL")
        return

    db = SessionLocal()
    try:
        print(f"=== audit all sources fetch {datetime.utcnow().isoformat()} UTC ===\n")
        sources = list(
            db.scalars(select(AdminSourceConfig).where(AdminSourceConfig.enabled.is_(True)).order_by(AdminSourceConfig.source))
        )
        print(f"enabled_admin_sources={len(sources)}")
        for src in sources:
            sk = (src.source or "").strip().lower()
            url_ok = mainstream_heat_fetch_url_ok(sk, (src.api_base or "").strip())
            print(f"  [{sk}] api_base_ok={url_ok} fetch_limit={src.fetch_limit} base={(src.api_base or '')[:80]!r}")

        conns = list(
            db.scalars(
                select(ProductConnector)
                .where(ProductConnector.enabled.is_(True))
                .order_by(ProductConnector.admin_source_key, ProductConnector.id)
            ).all()
        )
        print(f"\nenabled_connectors={len(conns)}\n")

        for c in conns:
            sk = (c.admin_source_key or "").strip().lower() or "?"
            print(f"--- connector #{c.id} {c.name!r} source={sk} ---")
            cfg = build_connector_sync_request_cfg(db, c)
            has_key = bool(str((cfg or {}).get("api_key") or "").strip())
            url = (cfg.get("url") or "")[:120]
            url_ok = mainstream_heat_fetch_url_ok(sk, url) if sk != "?" else False
            print(f"  url_ok={url_ok} has_api_key={has_key} url={url!r}")
            if not url_ok and sk in ("github", "product_hunt", "hacker_news", "newsapi", "thenewsapi", "acquire"):
                print("  ISSUE: api_base 未匹配热度打包路径，同步会走 http_fallback，无法入库多段 pack")

            code, snippet = _run_connector_request(cfg, db=None, connector_id=c.id, source_key=sk)
            diag = _snippet_pack_diag(snippet or "")
            items = parse_connector_sync_item_snippets((snippet or "")[:120000]) or []
            print(f"  fetch HTTP={code} {diag}")
            if code and 200 <= code < 300 and not items:
                preview = (snippet or "")[:280].replace("\n", " ")
                print(f"  ISSUE: 拉取成功但 pack 为空 preview={preview!r}")

            for i, snip in enumerate(items[:3]):
                ok, msg = connector_upstream_has_ingest_material(snip, sk)
                chars = connector_upstream_material_char_count(snip)
                print(f"  item[{i+1}] upstream_ok={ok} chars={chars} {('' if ok else msg[:100])}")

            since = datetime.utcnow() - timedelta(hours=72)
            logs = list(
                db.scalars(
                    select(ProductConnectorLog)
                    .where(ProductConnectorLog.connector_id == c.id, ProductConnectorLog.started_at >= since)
                    .order_by(desc(ProductConnectorLog.started_at))
                    .limit(3)
                ).all()
            )
            for log in logs:
                print(f"  log#{log.id} {log.status} rows={log.rows_ingested} at={log.started_at} err={(log.error_message or '')[:60]!r}")

            diag_rows = list(
                db.scalars(
                    select(ProductSyncDiagnosticLog)
                    .where(
                        ProductSyncDiagnosticLog.source_key == sk,
                        ProductSyncDiagnosticLog.created_at >= since,
                    )
                    .order_by(desc(ProductSyncDiagnosticLog.id))
                    .limit(5)
                ).all()
            )
            for d in diag_rows:
                if d.step in (
                    "fetch_empty",
                    "http_fallback",
                    "url_invalid",
                    "auth_missing",
                    "news_fetch_empty",
                    "connector_done",
                    "skip_thin_upstream",
                    "skip_llm_no_key",
                ):
                    print(f"  diag {d.created_at} [{d.step}] {(d.message or '')[:140]}")

            print()

        from backend.app.llm_settings_service import resolve_llm_http_config

        _b, key, model = resolve_llm_http_config(db)
        print(f"LLM configured={bool(key)} model={model}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
