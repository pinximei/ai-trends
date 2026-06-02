"""连接器拉取 / 入库步骤诊断日志（供管理后台「同步日志」页展示）。"""
from __future__ import annotations

import contextvars
import uuid
from datetime import datetime

# 写入 batch_start 消息，便于确认线上是否已部署最新诊断提交逻辑。
DIAG_PIPELINE_VERSION = "10"

# 管理端「同步日志」默认只展示 error：每条失败必须有明确原因（拉取 / 鉴权 / 入库 / LLM 校验）。

# step → 中文说明（导出/后台展示用；未知 step 仍显示英文代号）
STEP_LABELS_ZH: dict[str, str] = {
    "http_fail": "HTTP 请求失败",
    "http_exception": "网络或解析异常",
    "http_fallback": "备用请求失败",
    "auth_missing": "缺少 API Key / Token",
    "ph_auth": "Product Hunt 鉴权失败",
    "rate_limit": "上游限流",
    "url_invalid": "数据源 URL 不符合内置模板",
    "fetch_empty": "拉取成功但无可用条目",
    "news_fetch_empty": "新闻源拉取为空",
    "heat_done": "热度打包失败",
    "ingest_pack_empty": "入库打包为空",
    "llm_polish_retry": "LLM 润色未通过发布校验",
    "llm_config": "LLM 未配置或 Key 无效",
    "connector_done": "连接器同步结束（未新建文章）",
    "connector_fail": "连接器同步失败",
    "connector_aborted": "连接器同步中断",
    "segments": "行业/板块配置错误",
    "batch_done": "整批同步结束（含失败）",
    "batch_fatal": "整批同步致命错误",
    "batch_articles": "整批入库统计",
    "source_url_audit": "数据源 URL 审计",
}


def should_persist_diagnostic(*, level: str, step: str) -> bool:
    del step
    return (level or "info").strip().lower() == "error"


def should_persist_diagnostic_for_export(*, level: str, step: str) -> bool:
    """导出/复制时可选择包含 warn（默认 API 仍仅返回 error）。"""
    lv = (level or "info").strip().lower()
    return lv in ("error", "warn")

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("sync_diag_run_id", default=None)


def get_current_run_id() -> str | None:
    return _current_run_id.get()


def begin_run(db: Session, *, actor: str, kind: str = "theme_fetch") -> str:
    run_id = uuid.uuid4().hex[:16]
    _current_run_id.set(run_id)
    return run_id


def begin_connector_run(db: Session, *, actor: str, connector_id: int, source_key: str = "") -> str:
    """单连接器手动同步：独立 run_id，便于在「同步日志」页筛选复制。"""
    del db, actor, connector_id, source_key
    run_id = uuid.uuid4().hex[:16]
    _current_run_id.set(run_id)
    return run_id


def end_connector_run() -> None:
    """整批同步中每个连接器结束后清空 run_id，避免 skip 日志串到其它源。"""
    _current_run_id.set(None)


def end_run(db: Session, *, run_id: str, ok: int, fail: int, total: int) -> None:
    if fail > 0:
        write(
            db,
            run_id=run_id,
            level="error",
            step="batch_done",
            message=f"整批拉取结束：连接器 {total} 个，成功 {ok}，失败 {fail}（仅失败连接器见上方 error 行）",
        )
        commit_diagnostics(db)
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
    if not should_persist_diagnostic(level=level, step=step):
        return
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
    errors_only: bool = True,
) -> list[dict]:
    from .product_models import ProductSyncDiagnosticLog

    lim = max(1, min(int(limit), 2000))
    q = select(ProductSyncDiagnosticLog).order_by(desc(ProductSyncDiagnosticLog.id)).limit(lim * 3 if errors_only else lim)
    if run_id:
        q = q.where(ProductSyncDiagnosticLog.run_id == run_id.strip()[:32])
    rows = db.scalars(q).all()
    if errors_only:
        rows = [r for r in rows if (r.level or "").strip().lower() == "error"][:lim]
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


def step_label_zh(step: str) -> str:
    s = (step or "").strip()
    if not s:
        return "未知步骤"
    return STEP_LABELS_ZH.get(s, s)


def format_log_entry_human(r: dict, *, index: int | None = None) -> str:
    """单条错误：分层展示，便于非开发阅读。"""
    ts = (r.get("created_at") or "").replace("T", " ").replace("Z", " UTC")
    step = (r.get("step") or "").strip()
    step_zh = step_label_zh(step)
    lvl = (r.get("level") or "error").strip().upper()
    cid = r.get("connector_id")
    sk = (r.get("source_key") or "").strip()
    msg = (r.get("message") or "").strip().replace("\r\n", "\n")
    head = f"【{index}】{ts}" if index is not None else f"【{ts}】"
    lines = [head, f"  级别: {lvl}", f"  步骤: {step_zh} ({step})" if step else f"  步骤: {step_zh}"]
    if sk or cid is not None:
        parts = []
        if sk:
            parts.append(f"数据源={sk}")
        if cid is not None:
            parts.append(f"连接器=#{cid}")
        lines.append(f"  关联: {' | '.join(parts)}")
    lines.append(f"  原因: {msg or '（无详情）'}")
    return "\n".join(lines)


def format_logs_for_export(items: list[dict], *, run_id: str | None = None) -> str:
    """供管理端「复制日志」：中文分层说明，便于粘贴到工单/聊天排查。"""
    lines = [
        "=== AiTrends 同步诊断（仅错误）===",
        f"诊断版本: diag_v={DIAG_PIPELINE_VERSION}",
        f"批次 run_id: {run_id or '(未指定，混合最近错误)'}",
        f"共 {len(items)} 条",
        "",
        "说明: 每条 = 一次未入库/拉取失败；请从上到下对照后台数据源与连接器配置。",
        "",
    ]
    if not items:
        lines.append("（本批无错误记录：可能全部入库成功，或尚未执行同步）")
        lines.append("")
    for i, r in enumerate(items, start=1):
        lines.append(format_log_entry_human(r, index=i))
        lines.append("")
    lines.append("--- 技术简表（可选对照）---")
    for r in items:
        ts = r.get("created_at") or ""
        step = r.get("step") or ""
        cid = r.get("connector_id")
        sk = r.get("source_key") or ""
        meta = ""
        if cid is not None:
            meta += f" #{cid}"
        if sk:
            meta += f" [{sk}]"
        msg = (r.get("message") or "").replace("\r\n", " ").replace("\n", " ")
        lines.append(f"[{ts}] [{r.get('level') or 'error'}] [{step}]{meta} {msg[:500]}")
    return "\n".join(lines).strip() + "\n"


def clear_all(db: Session) -> int:
    from .product_models import ProductSyncDiagnosticLog

    n = int(db.query(ProductSyncDiagnosticLog).delete() or 0)
    db.flush()
    _current_run_id.set(None)
    return n
