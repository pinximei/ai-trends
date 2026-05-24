"""启动时补齐与 admin 数据源绑定的 ProductConnector（与演示种子无关，生产也会执行）。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdminSourceConfig
from .product_models import ProductConnector
from .connector_heat_fetch import (
    GITHUB_TRENDING_DEFAULT,
    HN_ALGOLIA_SEARCH_DEFAULT,
    NEWSAPI_TOP_HEADLINES_DEFAULT,
    THENEWSAPI_TOP_DEFAULT,
    github_trending_is_discovery_url,
    hacker_news_algolia_is_search_url,
    newsapi_is_v2_url,
    thenewsapi_is_news_url,
)
from .scope_labels_util import get_scope_labels_from_source
from .services import MAINSTREAM_ADMIN_SOURCE_KEYS, MAINSTREAM_ADMIN_SOURCE_PRESETS

_CORE_ADMIN_SOURCE_KEYS: tuple[str, ...] = tuple(row["source"] for row in MAINSTREAM_ADMIN_SOURCE_PRESETS)

# 启动时默认启用拉取（参与定时连接器批量同步）；与 MAINSTREAM 内置源一致（3 路）。
# 扩容：每增加一个 key 前须本地 verify_source_local.py 通过，见 docs/DATA_SOURCE_ONBOARDING.md。
AUTO_ENABLE_PULL_SOURCE_KEYS: frozenset[str] = MAINSTREAM_ADMIN_SOURCE_KEYS


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


def _preset_by_source(source: str) -> dict | None:
    key = (source or "").strip().lower()
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        if row["source"] == key:
            return row
    return None


def mainstream_heat_fetch_url_ok(source: str, url: str) -> bool:
    """内置数据源 api_base 是否可走 connector_sync_items_v1 热度打包。"""
    src = (source or "").strip().lower()
    u = (url or "").strip()
    if not u:
        return False
    if src == "github":
        return github_trending_is_discovery_url(u)
    if src == "product_hunt":
        low = u.lower()
        return "api.producthunt.com" in low and "graphql" in low
    if src == "hacker_news":
        return hacker_news_algolia_is_search_url(u)
    if src == "newsapi":
        return newsapi_is_v2_url(u)
    if src == "thenewsapi":
        return thenewsapi_is_news_url(u)
    return False


def repair_mainstream_heat_fetch_admin_sources(db: Session) -> int:
    """内置源 api_base / scope_label 与热度打包路径对齐（含 HN firebase 等旧地址）。"""
    changed = 0
    for row in db.scalars(select(AdminSourceConfig)).all():
        preset = _preset_by_source(row.source)
        if not preset:
            continue
        src = (row.source or "").strip().lower()
        default_base = (preset.get("api_base") or "").strip()
        if not default_base:
            continue
        u = (row.api_base or "").strip()
        if not mainstream_heat_fetch_url_ok(src, u):
            row.api_base = default_base
            changed += 1
        sl = (preset.get("scope_label") or "").strip()
        if sl and not get_scope_labels_from_source(row):
            from .scope_labels_util import apply_scope_labels_to_row

            apply_scope_labels_to_row(row, [sl])
            changed += 1
        row.updated_at = datetime.utcnow()
    if changed:
        db.commit()
    return changed


def audit_mainstream_connector_paths(db: Session) -> list[dict]:
    """诊断内置源的 URL、连接器与板块解析。"""
    from .source_segment_resolve import resolve_admin_source_key_to_segments

    out: list[dict] = []
    for preset in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        src = preset["source"]
        row = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == src))
        api_base = (row.api_base or "").strip() if row else ""
        default_base = (preset.get("api_base") or "").strip()
        conn = db.scalar(
            select(ProductConnector).where(ProductConnector.admin_source_key == src).order_by(ProductConnector.id).limit(1)
        )
        cfg_url = ""
        if conn and isinstance(conn.config_json, dict):
            cfg_url = (conn.config_json.get("url") or "").strip()
        segments = resolve_admin_source_key_to_segments(db, src) if row else []
        out.append(
            {
                "source": src,
                "label": (row.preset_label if row else None) or preset.get("preset_label") or src,
                "configured": row is not None,
                "enabled": bool(row.enabled) if row else False,
                "api_base": api_base,
                "default_api_base": default_base,
                "heat_fetch_url_ok": mainstream_heat_fetch_url_ok(src, api_base),
                "connector_id": conn.id if conn else None,
                "connector_enabled": bool(conn.enabled) if conn else False,
                "connector_url": cfg_url,
                "connector_url_matches_admin": (not cfg_url) or cfg_url == api_base,
                "segment_count": len(segments),
                "expected_path": {
                    "github": "github.com/trending → api.github.com/repos（客户端关键词过滤）",
                    "product_hunt": "api.producthunt.com/v2/api/graphql",
                    "hacker_news": "hn.algolia.com/api/v1/search?tags=front_page",
                    "newsapi": NEWSAPI_TOP_HEADLINES_DEFAULT,
                    "thenewsapi": THENEWSAPI_TOP_DEFAULT,
                }.get(src, ""),
            }
        )
    return out


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
        from .source_query_auth import apply_connector_auth_defaults

        cfg = dict(c.config_json or {})
        changed = False
        if (cfg.get("url") or "").strip() != base:
            cfg["url"] = base
            changed = True
        new_cfg = apply_connector_auth_defaults(ask, cfg)
        if new_cfg != cfg:
            cfg = new_cfg
            changed = True
        if changed:
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
    """将内置主流数据源与绑定连接器设为启用（新建与已有库均生效）。"""
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

    自定义标识、旧版预置残留等都会被清掉；随后 ``ensure_mainstream_admin_sources`` 会补回内置行。
    """
    import logging

    from sqlalchemy import delete

    log = logging.getLogger(__name__)
    if not MAINSTREAM_ADMIN_SOURCE_KEYS:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0}
    keys = tuple(MAINSTREAM_ADMIN_SOURCE_KEYS)
    n_c = _delete_product_connectors_where(
        db,
        ProductConnector.admin_source_key.isnot(None),
        ~ProductConnector.admin_source_key.in_(keys),
    )
    ra = db.execute(delete(AdminSourceConfig).where(~AdminSourceConfig.source.in_(keys)))
    db.commit()
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
    n_c = _delete_product_connectors_where(db, ProductConnector.admin_source_key.in_(keys))
    ra = db.execute(delete(AdminSourceConfig).where(AdminSourceConfig.enabled.is_(False)))
    db.commit()
    n_a = int(ra.rowcount) if ra.rowcount is not None and ra.rowcount >= 0 else 0
    if n_c or n_a:
        log.info("pruned disabled admin sources: connectors=%s admin_sources=%s keys=%s", n_c, n_a, keys)
    return {"connectors_deleted": n_c, "admin_sources_deleted": n_a}


def _delete_product_connectors_where(db: Session, *where_clauses) -> int:
    """先删同步日志再删连接器，避免 product_connector_logs 外键阻塞启动清理。"""
    from sqlalchemy import delete, select

    from .product_models import ProductConnector, ProductConnectorLog, ProductSyncDiagnosticLog

    q = select(ProductConnector.id)
    for clause in where_clauses:
        q = q.where(clause)
    ids = tuple(db.scalars(q).all())
    if not ids:
        return 0
    db.execute(delete(ProductConnectorLog).where(ProductConnectorLog.connector_id.in_(ids)))
    db.execute(delete(ProductSyncDiagnosticLog).where(ProductSyncDiagnosticLog.connector_id.in_(ids)))
    r = db.execute(delete(ProductConnector).where(ProductConnector.id.in_(ids)))
    return int(r.rowcount) if r.rowcount is not None and r.rowcount >= 0 else 0


def _article_clauses_for_admin_source_keys(keys: tuple[str, ...]):
    from sqlalchemy import or_

    from .product_models import Article

    if not keys:
        return None
    return or_(*[Article.third_party_source.ilike(f"{k}%") for k in keys])


def prune_articles_for_admin_source_keys(db: Session, keys: tuple[str, ...]) -> int:
    """删除 third_party_source 以给定 admin source 开头的文章（含 TAAFT / Acquire 等下线源）。"""
    import logging

    from sqlalchemy import delete, func, select

    from .product_models import Article

    log = logging.getLogger(__name__)
    clause = _article_clauses_for_admin_source_keys(keys)
    if clause is None:
        return 0
    pending = int(db.scalar(select(func.count()).select_from(Article).where(clause)) or 0)
    if pending <= 0:
        return 0
    r = db.execute(delete(Article).where(clause))
    db.commit()
    n = int(r.rowcount) if r.rowcount is not None and r.rowcount >= 0 else 0
    if n:
        log.info("pruned articles for admin sources %s: count=%s", keys, n)
    return n


def prune_discontinued_bootstrap_admin_sources(db: Session) -> dict[str, int]:
    """删除已下线的内置数据源、绑定连接器及对应文章，与当前 MAINSTREAM 预设对齐。"""
    import logging

    from sqlalchemy import delete

    from .services import DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES

    log = logging.getLogger(__name__)
    if not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES:
        return {"connectors_deleted": 0, "admin_sources_deleted": 0, "articles_deleted": 0}
    keys = tuple(DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES)
    n_art = prune_articles_for_admin_source_keys(db, keys)
    n_c = _delete_product_connectors_where(db, ProductConnector.admin_source_key.in_(keys))
    ra = db.execute(delete(AdminSourceConfig).where(AdminSourceConfig.source.in_(keys)))
    db.commit()
    n_a = int(ra.rowcount) if ra.rowcount is not None and ra.rowcount >= 0 else 0
    if n_c or n_a or n_art:
        log.info(
            "pruned discontinued bootstrap sources: connectors=%s admin_sources=%s articles=%s",
            n_c,
            n_a,
            n_art,
        )
    return {"connectors_deleted": n_c, "admin_sources_deleted": n_a, "articles_deleted": n_art}
