"""本地 SQLite：逐连接器同步并汇总 LLM / 诊断日志（排查 skip_llm、retry）。

用法（仓库根目录）:
  set AITRENDS_DATABASE_URL=sqlite:///D:/aisoul/backend/data/dev_local.db
  py -3.12 scripts/diagnose_connector_sync_llm.py
  py -3.12 scripts/diagnose_connector_sync_llm.py --connector-id 28
  py -3.12 scripts/diagnose_connector_sync_llm.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 默认本地 SQLite（可被环境变量覆盖）
os.environ.setdefault("AITRENDS_DATABASE_URL", f"sqlite:///{ROOT.as_posix()}/backend/data/dev_local.db")
os.environ.setdefault("AITRENDS_ENV", "dev")

from sqlalchemy import desc, func, select  # noqa: E402

from backend.app.db import SessionLocal, engine  # noqa: E402
from backend.app.llm_settings_service import resolve_llm_http_config  # noqa: E402
from backend.app.product_models import (  # noqa: E402
    LlmUsageLog,
    ProductConnector,
    ProductSyncDiagnosticLog,
)
from backend.app.routers.admin_extended import run_connector_sync  # noqa: E402


def _mask_key(k: str) -> str:
    k = (k or "").strip()
    if not k:
        return "(空)"
    if len(k) <= 8:
        return "*" * len(k)
    return f"{k[:4]}...{k[-4:]}"


def _startup_db(db) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from load_local_credentials import seed_all_local_credentials

    from backend.app.db import Base, ensure_schema_compatibility
    from backend.app.product_connectors_bootstrap import (
        ensure_core_admin_connectors,
        repair_connector_urls_from_admin_sources,
    )
    from backend.app.services import ensure_mainstream_admin_sources, repair_mainstream_fetch_limits

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    ensure_mainstream_admin_sources(db)
    repair_mainstream_fetch_limits(db)
    ensure_core_admin_connectors(db)
    repair_connector_urls_from_admin_sources(db)
    seed_all_local_credentials(db)


def _summarize_diag(db, *, since_id: int) -> None:
    rows = db.scalars(
        select(ProductSyncDiagnosticLog)
        .where(ProductSyncDiagnosticLog.id > since_id)
        .order_by(ProductSyncDiagnosticLog.id)
    ).all()
    if not rows:
        print("  (本连接器无新诊断行)")
        return
    steps = Counter((r.step or "") for r in rows)
    print(f"  诊断行数={len(rows)} steps={dict(steps)}")
    for r in rows:
        if r.level in ("error", "warn") or (r.step or "") in (
            "skip_llm_polish",
            "skip_llm_no_key",
            "llm_polish_retry",
            "skip_llm_shape",
            "connector_done",
            "news_fetch_stats",
        ):
            sk = f" [{r.source_key}]" if r.source_key else ""
            print(f"    [{r.level}] [{r.step}]{sk} {(r.message or '')[:220]}")


def _summarize_llm(db, *, since_id: int) -> None:
    rows = db.scalars(
        select(LlmUsageLog)
        .where(LlmUsageLog.id > since_id, LlmUsageLog.scenario == "article_ingest_polish")
        .order_by(LlmUsageLog.id)
    ).all()
    if not rows:
        print("  LLM 调用: 0 次 article_ingest_polish")
        return
    ok = sum(1 for r in rows if r.success)
    fail = len(rows) - ok
    print(f"  LLM polish 调用={len(rows)} 成功={ok} 失败={fail}")
    for r in rows[-8:]:
        err = (r.error_code or "")[:120]
        print(
            f"    id={r.id} ok={r.success} model={r.model} "
            f"in={r.input_tokens} out={r.output_tokens} ref={r.ref_id} err={err!r}"
        )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--connector-id", type=int, default=0, help="只测指定连接器")
    p.add_argument("--dry-run", action="store_true", help="只检查 LLM/连接器，不发起同步")
    p.add_argument("--skip-disabled", action="store_true", default=True)
    args = p.parse_args()

    db = SessionLocal()
    try:
        _startup_db(db)
        base, key, model = resolve_llm_http_config(db)
        print("=== LLM 配置 ===")
        print(f"  base_url={base}")
        print(f"  model={model}")
        print(f"  api_key={_mask_key(key)}")
        if not (key or "").strip():
            print("FAIL: 库内与环境均无 LLM Key，入库必 skip_llm_no_key")
            return 1

        q = select(ProductConnector).order_by(ProductConnector.id)
        if args.connector_id:
            q = q.where(ProductConnector.id == args.connector_id)
        elif args.skip_disabled:
            q = q.where(ProductConnector.enabled.is_(True))
        connectors = list(db.scalars(q).all())
        print(f"\n=== 连接器 ({len(connectors)} 个) ===")
        for c in connectors:
            cfg = dict(c.config_json or {})
            has_key = bool(str(cfg.get("api_key") or "").strip())
            print(
                f"  id={c.id} enabled={c.enabled} source={c.admin_source_key!r} "
                f"name={c.name!r} has_connector_api_key={has_key}"
            )

        if args.dry_run:
            return 0

        print("\n=== 逐连接器同步（同步 HTTP + 同步 LLM，非 asyncio）===\n")
        total_articles = 0
        for c in connectors:
            diag_max = int(db.scalar(select(func.max(ProductSyncDiagnosticLog.id))) or 0)
            llm_max = int(db.scalar(select(func.max(LlmUsageLog.id))) or 0)
            print(f"--- #{c.id} {c.admin_source_key} / {c.name} ---")
            try:
                out = run_connector_sync(db, c.id, actor="diagnose_script", bypass_rate_limit=True)
                print(
                    f"  结果: http={out.get('http_status')} articles_created={out.get('articles_created')} "
                    f"error={out.get('error')!r}"
                )
                total_articles += int(out.get("articles_created") or 0)
            except Exception as e:
                print(f"  异常: {type(e).__name__}: {e}")
            _summarize_diag(db, since_id=diag_max)
            _summarize_llm(db, since_id=llm_max)
            print()

        print(f"=== 合计新建文章 {total_articles} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
