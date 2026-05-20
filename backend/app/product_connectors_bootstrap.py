"""启动时补齐与 admin 数据源绑定的 ProductConnector（与演示种子无关，生产也会执行）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdminSourceConfig
from .product_models import ProductConnector
from .connector_heat_fetch import GITHUB_TRENDING_DEFAULT
from .services import MAINSTREAM_ADMIN_SOURCE_KEYS, MAINSTREAM_ADMIN_SOURCE_PRESETS

_CORE_ADMIN_SOURCE_KEYS: tuple[str, ...] = tuple(row["source"] for row in MAINSTREAM_ADMIN_SOURCE_PRESETS)

# 启动时默认启用拉取（参与定时连接器批量同步）；HF Spaces 仍由运营手动开启以免与 GitHub/PH 同时暴量请求。
# 扩容：每增加一个 key 前须本地 verify_source_local.py 通过，见 docs/DATA_SOURCE_ONBOARDING.md。
AUTO_ENABLE_PULL_SOURCE_KEYS: frozenset[str] = frozenset({"github", "product_hunt"})


def repair_github_admin_source_if_still_zen(db: Session) -> None:
    """旧库若仍为 /zen，响应过短无法通过 rule_value_score（<80 字符），同步永远不入库。"""
    row = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == "github"))
    if not row:
        return
    u = (row.api_base or "").strip().lower()
    if "api.github.com/zen" in u or u.rstrip("/").endswith("/zen"):
        row.api_base = GITHUB_TRENDING_DEFAULT
        row.updated_at = datetime.utcnow()
        db.commit()


def repair_short_probe_admin_sources(db: Session) -> None:
    """旧预设中 maxitem、/ping 等过短响应无法通过入库价值分；并将若干「统计型」默认 URL 升为条目型端点。"""
    changed = False
    for row in db.scalars(select(AdminSourceConfig)).all():
        if row.source == "github":
            u = (row.api_base or "").strip().lower()
            legacy = (
                "/repos/octocat/hello-world" in u
                or "/repos/microsoft/vscode/issues" in u
                or "api.github.com/zen" in u
            )
            if legacy:
                row.api_base = GITHUB_TRENDING_DEFAULT
                row.updated_at = datetime.utcnow()
                changed = True
    if changed:
        db.commit()


def repair_connector_urls_from_admin_sources(db: Session) -> int:
    """绑定数据源的连接器 ``config_json.url`` 与 ``admin_source_configs.api_base`` 对齐（避免仍请求 /zen 等旧地址）。"""
    n = 0
    for c in db.scalars(
        select(ProductConnector).where(ProductConnector.admin_source_key.isnot(None))
    ).all():
        ask = (c.admin_source_key or "").strip().lower()
        if not ask:
            continue
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == ask))
        if not src:
            continue
        base = (src.api_base or "").strip()
        if not base:
            continue
        cfg = dict(c.config_json or {})
        if (cfg.get("url") or "").strip() != base:
            cfg["url"] = base
            c.config_json = cfg
            n += 1
    if n:
        db.commit()
    return n


def ensure_core_admin_connectors(db: Session) -> None:
    """每个核心 admin 数据源最多补一条连接器（admin_source_key 对齐），便于后台「连接器」里直接启用同步。"""
    for key in _CORE_ADMIN_SOURCE_KEYS:
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
        if not src:
            continue
        exists = db.scalar(
            select(ProductConnector.id).where(ProductConnector.admin_source_key == key).limit(1)
        )
        if exists:
            continue
        label = ((src.preset_label or "").strip() or key.replace("_", " ").title())
        db.add(
            ProductConnector(
                name=f"{label} 拉取",
                provider_name=key,
                type="api",
                config_json={"method": "GET"},
                enabled=key in AUTO_ENABLE_PULL_SOURCE_KEYS,
                min_interval_seconds=3600,
                admin_source_key=key,
            )
        )
    db.commit()


def enable_auto_pull_admin_sources_and_connectors(db: Session) -> dict[str, int]:
    """将 GitHub、Product Hunt 数据源与绑定连接器设为启用（新建与已有库均生效）。"""
    import logging

    log = logging.getLogger(__name__)
    n_src = 0
    n_conn = 0
    for key in AUTO_ENABLE_PULL_SOURCE_KEYS:
        src = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == key))
        if src and not src.enabled:
            src.enabled = True
            src.updated_at = datetime.utcnow()
            n_src += 1
        for c in db.scalars(
            select(ProductConnector).where(ProductConnector.admin_source_key == key)
        ).all():
            if not c.enabled:
                c.enabled = True
                n_conn += 1
    if n_src or n_conn:
        db.commit()
        log.info(
            "enabled auto-pull sources: admin_sources=%s connectors=%s keys=%s",
            n_src,
            n_conn,
            sorted(AUTO_ENABLE_PULL_SOURCE_KEYS),
        )
    return {"admin_sources_enabled": n_src, "connectors_enabled": n_conn}


def prune_admin_sources_outside_mainstream(db: Session) -> dict[str, int]:
    """删除库中一切不在当前 MAINSTREAM 预置列表内的 admin 数据源及其绑定连接器。

    自定义标识、旧版预置残留等都会被清掉；随后 ``ensure_mainstream_admin_sources`` 会补回四条 AI 内置行。
    """
    import logging

    from sqlalchemy import delete

    log = logging.getLogger(__name__)
    if not MAINSTREAM_ADMIN_SOURCE_KEYS:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0}
    keys = tuple(MAINSTREAM_ADMIN_SOURCE_KEYS)
    rc = db.execute(
        delete(ProductConnector).where(
            ProductConnector.admin_source_key.isnot(None),
            ~ProductConnector.admin_source_key.in_(keys),
        )
    )
    ra = db.execute(delete(AdminSourceConfig).where(~AdminSourceConfig.source.in_(keys)))
    db.commit()
    n_c = int(rc.rowcount) if rc.rowcount is not None and rc.rowcount >= 0 else 0
    n_a = int(ra.rowcount) if ra.rowcount is not None and ra.rowcount >= 0 else 0
    if n_c or n_a:
        log.info("pruned admin sources outside mainstream: connectors=%s admin_sources=%s", n_c, n_a)
    return {"connectors_deleted": n_c, "admin_sources_deleted": n_a}


def prune_disabled_admin_sources(db: Session) -> dict[str, int]:
    """删除所有已停用（enabled=False）的数据源行及其绑定连接器。

    内置 AI 预置若曾被停用，删除后由随后的 ``ensure_mainstream_admin_sources`` 按模板重新插入（默认启用）。
    """
    import logging

    from sqlalchemy import delete

    log = logging.getLogger(__name__)
    rows = db.scalars(select(AdminSourceConfig).where(AdminSourceConfig.enabled.is_(False))).all()
    if not rows:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0}
    keys = tuple({r.source.strip().lower() for r in rows if (r.source or "").strip()})
    if not keys:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0}
    rc = db.execute(delete(ProductConnector).where(ProductConnector.admin_source_key.in_(keys)))
    ra = db.execute(delete(AdminSourceConfig).where(AdminSourceConfig.enabled.is_(False)))
    db.commit()
    n_c = int(rc.rowcount) if rc.rowcount is not None and rc.rowcount >= 0 else 0
    n_a = int(ra.rowcount) if ra.rowcount is not None and ra.rowcount >= 0 else 0
    if n_c or n_a:
        log.info("pruned disabled admin sources: connectors=%s admin_sources=%s keys=%s", n_c, n_a, keys)
    return {"connectors_deleted": n_c, "admin_sources_deleted": n_a}


def prune_discontinued_bootstrap_admin_sources(db: Session) -> dict[str, int]:
    """删除已下线的内置数据源及其绑定连接器，与当前 MAINSTREAM 预设对齐。"""
    import logging

    from sqlalchemy import delete

    from .services import DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES

    log = logging.getLogger(__name__)
    if not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0}
    keys = tuple(DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES)
    rc = db.execute(delete(ProductConnector).where(ProductConnector.admin_source_key.in_(keys)))
    ra = db.execute(delete(AdminSourceConfig).where(AdminSourceConfig.source.in_(keys)))
    db.commit()
    n_c = int(rc.rowcount) if rc.rowcount is not None and rc.rowcount >= 0 else 0
    n_a = int(ra.rowcount) if ra.rowcount is not None and ra.rowcount >= 0 else 0
    if n_c or n_a:
        log.info("pruned discontinued bootstrap sources: connectors=%s admin_sources=%s", n_c, n_a)
    return {"connectors_deleted": n_c, "admin_sources_deleted": n_a}
