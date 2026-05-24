"""连接器拉取 / 入库步骤诊断日志（供管理后台「同步日志」页展示）。"""
from __future__ import annotations

import contextvars
import uuid
from datetime import datetime

# 写入 batch_start 消息，便于确认线上是否已部署最新诊断提交逻辑。
DIAG_PIPELINE_VERSION = "4"

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("sync_diag_run_id", default=None)


def get_current_run_id() -> str | None:
    return _current_run_id.get()


def begin_run(db: Session, *, actor: str, kind: str = "theme_fetch") -> str:
    run_id = uuid.uuid4().hex[:16]
    _current_run_id.set(run_id)
    write(
        db,
        run_id=run_id,
        level="info",
        step="batch_start",
        message=f"开始拉取（{kind}）操作者={actor} diag_v={DIAG_PIPELINE_VERSION}",
    )
    commit_diagnostics(db)
    return run_id


def begin_connector_run(db: Session, *, actor: str, connector_id: int, source_key: str = "") -> str:
    """单连接器手动同步：独立 run_id，便于在「同步日志」页筛选复制。"""
    run_id = uuid.uuid4().hex[:16]
    _current_run_id.set(run_id)
    sk = (source_key or "").strip().lower()
    write(
        db,
        run_id=run_id,
        level="info",
        step="batch_start",
        message=(
            f"开始单连接器同步 #{connector_id} source={sk or '—'} "
            f"操作者={actor} diag_v={DIAG_PIPELINE_VERSION}"
        ),
        connector_id=connector_id,
        source_key=sk or None,
    )
    commit_diagnostics(db)
    return run_id


def end_run(db: Session, *, run_id: str, ok: int, fail: int, total: int) -> None:
    write(
        db,
        run_id=run_id,
        level="info" if fail == 0 else "warn",
        step="batch_done",
        message=f"整批拉取结束：连接器 {total} 个，成功 {ok}，失败 {fail}",
    )
    if _current_run_id.get() == run_id:
        _current_run_id.set(None)


def write(
    db: Session,
    *,
    run_id: str | None = None,
    level: str = "info",
    step: str,
    message: str,
    connector_id: int | None = None,
    source_key: str | None = None,
) -> None:
    from .product_models import ProductSyncDiagnosticLog

    rid = (run_id or _current_run_id.get() or "").strip() or uuid.uuid4().hex[:16]
    if not _current_run_id.get():
        _current_run_id.set(rid)
    row = ProductSyncDiagnosticLog(
        run_id=rid[:32],
        level=(level or "info")[:16],
        step=(step or "log")[:64],
        message=(message or "")[:8000],
        connector_id=connector_id,
        source_key=(source_key or "")[:64] or None,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()


def commit_diagnostics(db: Session) -> None:
    """立即提交当前会话中的诊断日志（避免 taxonomy 中途 commit 后仅留下 batch_start）。"""
    db.commit()


def list_logs(
    db: Session,
    *,
    run_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    from .product_models import ProductSyncDiagnosticLog

    lim = max(1, min(int(limit), 2000))
    q = select(ProductSyncDiagnosticLog).order_by(desc(ProductSyncDiagnosticLog.id)).limit(lim)
    if run_id:
        q = q.where(ProductSyncDiagnosticLog.run_id == run_id.strip()[:32])
    rows = db.scalars(q).all()
    if run_id:
        rows = list(reversed(rows))
    else:
        rows = list(reversed(rows))
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "level": r.level,
            "step": r.step,
            "message": r.message,
            "connector_id": r.connector_id,
            "source_key": r.source_key,
        }
        for r in rows
    ]


def list_recent_run_ids(db: Session, *, limit: int = 30) -> list[str]:
    from .product_models import ProductSyncDiagnosticLog

    rows = db.scalars(select(ProductSyncDiagnosticLog).order_by(desc(ProductSyncDiagnosticLog.id)).limit(800)).all()
    seen: list[str] = []
    for r in rows:
        rid = (r.run_id or "").strip()
        if rid and rid not in seen:
            seen.append(rid)
        if len(seen) >= max(1, min(limit, 100)):
            break
    return seen


def format_logs_for_export(items: list[dict], *, run_id: str | None = None) -> str:
    """供管理端「复制日志」：保留换行，便于粘贴到工单/聊天排查。"""
    lines = [
        f"# AiTrends 同步诊断日志 diag_v={DIAG_PIPELINE_VERSION}",
        f"# run_id={run_id or '(mixed)'}",
        f"# lines={len(items)}",
        "",
    ]
    for r in items:
        ts = r.get("created_at") or ""
        lvl = r.get("level") or "info"
        step = r.get("step") or ""
        cid = r.get("connector_id")
        sk = r.get("source_key") or ""
        meta = ""
        if cid is not None:
            meta += f" #{cid}"
        if sk:
            meta += f" [{sk}]"
        msg = (r.get("message") or "").replace("\r\n", "\n")
        lines.append(f"[{ts}] [{lvl}] [{step}]{meta} {msg}")
    return "\n".join(lines).strip() + "\n"


def clear_all(db: Session) -> int:
    from .product_models import ProductSyncDiagnosticLog

    n = int(db.query(ProductSyncDiagnosticLog).delete() or 0)
    db.flush()
    _current_run_id.set(None)
    return n
