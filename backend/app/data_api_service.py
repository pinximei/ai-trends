from __future__ import annotations

import json
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdminSetting, AdminSourceConfig, AdminUser, EvidenceSignal, Trend
from .product_models import ProductConnector
from .scope_labels_util import apply_scope_labels_to_row, get_scope_labels_from_source, normalize_scope_labels_from_payload
from .admin_source_fetch import normalize_fetch_limit
from .connector_heat_fetch import (
    github_trending_is_discovery_url,
    hacker_news_algolia_is_search_url,
    newsapi_is_v2_url,
    sync_github_trending_top_details,
    sync_hacker_news_top_details,
    sync_newsapi_top_headlines,
    sync_product_hunt_top_details,
    sync_thenewsapi_top_news,
    thenewsapi_is_news_url,
)
from .source_query_auth import (
    load_stored_api_key_for_source,
    merge_api_key_into_url,
    query_auth_for_source,
    source_uses_query_key_auth,
)
from .services import (
    ADMIN_SOURCE_PRESETS_HIDE_CARD_API_KEY,
    ADMIN_SOURCE_PRESETS_SHOW_APP_SECRET_FIELD,
    CONTENT_ROLE_LABEL_ZH,
)


class DataApiService:
    """Single gateway for all DB access."""

    def __init__(self, db: Session):
        self.db = db

    def list_admin_source_presets(self) -> list[dict]:
        """GET /api/admin/v1/sources/presets：全部来自 admin_source_configs，无静态 JSON / 代码内列表。"""
        rows = self.db.scalars(select(AdminSourceConfig).order_by(AdminSourceConfig.source.asc())).all()
        items: list[dict] = []
        for i in rows:
            sl = get_scope_labels_from_source(i)
            scope_primary = (sl[0] if sl else (i.scope_label or "")).strip()
            role = (i.content_role or "").strip() or "daily_editorial"
            label = (i.preset_label or "").strip() or i.source.replace("_", " ").title()
            show_api_key_field = i.source not in ADMIN_SOURCE_PRESETS_HIDE_CARD_API_KEY
            show_app_secret_field = i.source in ADMIN_SOURCE_PRESETS_SHOW_APP_SECRET_FIELD
            items.append(
                {
                    "source": i.source,
                    "label": label,
                    "api_base": i.api_base or "",
                    "frequency": "scheduled",
                    "scope_label": scope_primary,
                    "scope_labels": sl if sl else ([scope_primary] if scope_primary else []),
                    "notes": i.notes or "",
                    "enabled": bool(i.enabled),
                    "content_role": role,
                    "content_role_label_zh": CONTENT_ROLE_LABEL_ZH.get(role, role),
                    "show_api_key_field": show_api_key_field,
                    "show_app_secret_field": show_app_secret_field,
                    "fetch_limit": normalize_fetch_limit(getattr(i, "fetch_limit", None), source=i.source),
                }
            )
        return items

    def list_admin_sources(self, keyword: str = "") -> list[dict]:
        stmt = select(AdminSourceConfig).order_by(AdminSourceConfig.source.asc())
        if keyword:
            stmt = stmt.where(AdminSourceConfig.source.contains(keyword))
        items = self.db.scalars(stmt).all()
        connectors = self.db.scalars(
            select(ProductConnector)
            .where(ProductConnector.admin_source_key.isnot(None))
            .order_by(ProductConnector.id)
        ).all()
        by_key: dict[str, list[ProductConnector]] = {}
        for c in connectors:
            k = (c.admin_source_key or "").strip().lower()
            if k:
                by_key.setdefault(k, []).append(c)
        out: list[dict] = []
        for i in items:
            sk = i.source
            c_rows = by_key.get(sk, [])
            connectors_token_status = [
                {
                    "connector_id": c.id,
                    "name": c.name,
                    "enabled": c.enabled,
                    "has_api_key": bool(str((dict(c.config_json or {}).get("api_key") or "")).strip()),
                    "has_oauth_client_secret": bool(
                        str((dict(c.config_json or {}).get("oauth_client_secret") or "")).strip()
                    ),
                }
                for c in c_rows
            ]
            out.append(
                {
                    "source": i.source,
                    "enabled": i.enabled,
                    "frequency": "scheduled",
                    "api_base": i.api_base,
                    "api_key_masked": i.api_key_masked,
                    "app_secret_masked": getattr(i, "app_secret_masked", "") or "",
                    "admin_key_configured": bool((i.api_key_masked or "").strip()),
                    "connectors_token_status": connectors_token_status,
                    "scope_label": i.scope_label or "",
                    "scope_labels": get_scope_labels_from_source(i),
                    "notes": i.notes,
                    "fetch_limit": normalize_fetch_limit(getattr(i, "fetch_limit", None), source=i.source),
                    "updated_at": i.updated_at.isoformat(),
                }
            )
        return out

    def upsert_admin_source(self, payload: dict, mask_func) -> dict:
        source = payload["source"].strip().lower()
        if not source:
            raise ValueError("source required")
        item = self.db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == source))
        if not item:
            item = AdminSourceConfig(source=source)
            self.db.add(item)
        item.enabled = payload["enabled"]
        item.frequency = "scheduled"
        item.api_base = payload["api_base"].strip()
        raw_key = (payload.get("api_key") or "").strip()
        if raw_key:
            item.api_key_masked = mask_func(raw_key)
            # 同步实际只读连接器 config_json.api_key；避免运营只在「数据源」表单填钥而连接器仍为空。
            for c in self.db.scalars(
                select(ProductConnector).where(
                    ProductConnector.admin_source_key.isnot(None),
                    ProductConnector.admin_source_key == item.source,
                )
            ).all():
                cfg = dict(c.config_json or {})
                cfg["api_key"] = raw_key
                from .source_query_auth import apply_connector_auth_defaults

                c.config_json = apply_connector_auth_defaults(item.source, cfg)
        raw_secret = (payload.get("app_secret") or "").strip()
        if payload.get("clear_app_secret"):
            item.app_secret_masked = ""
            for c in self.db.scalars(
                select(ProductConnector).where(
                    ProductConnector.admin_source_key.isnot(None),
                    ProductConnector.admin_source_key == item.source,
                )
            ).all():
                cfg = dict(c.config_json or {})
                cfg.pop("oauth_client_secret", None)
                c.config_json = cfg
        elif raw_secret:
            item.app_secret_masked = mask_func(raw_secret)
            for c in self.db.scalars(
                select(ProductConnector).where(
                    ProductConnector.admin_source_key.isnot(None),
                    ProductConnector.admin_source_key == item.source,
                )
            ).all():
                cfg = dict(c.config_json or {})
                cfg["oauth_client_secret"] = raw_secret
                c.config_json = cfg
        item.notes = payload["notes"].strip()
        if "fetch_limit" in payload and payload.get("fetch_limit") is not None:
            item.fetch_limit = normalize_fetch_limit(int(payload["fetch_limit"]), source=source)
        elif not item.id:
            item.fetch_limit = normalize_fetch_limit(None, source=source)
        labels = normalize_scope_labels_from_payload(payload)
        apply_scope_labels_to_row(item, labels)
        item.updated_at = datetime.utcnow()
        self.db.commit()
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(self.db)
        labels = get_scope_labels_from_source(item)
        c_rows = self.db.scalars(
            select(ProductConnector).where(ProductConnector.admin_source_key == item.source).order_by(ProductConnector.id)
        ).all()
        connectors_token_status = [
            {
                "connector_id": c.id,
                "name": c.name,
                "enabled": c.enabled,
                    "has_api_key": bool(str((dict(c.config_json or {}).get("api_key") or "")).strip()),
                    "has_oauth_client_secret": bool(
                        str((dict(c.config_json or {}).get("oauth_client_secret") or "")).strip()
                    ),
                }
                for c in c_rows
            ]
        return {
            "source": item.source,
            "enabled": item.enabled,
            "frequency": item.frequency,
            "api_base": item.api_base,
            "api_key_masked": item.api_key_masked,
            "app_secret_masked": getattr(item, "app_secret_masked", "") or "",
            "admin_key_configured": bool((item.api_key_masked or "").strip()),
            "connectors_token_status": connectors_token_status,
            "scope_label": item.scope_label or "",
            "scope_labels": labels,
            "notes": item.notes,
            "fetch_limit": normalize_fetch_limit(item.fetch_limit, source=item.source),
            "updated_at": item.updated_at.isoformat(),
        }

    def delete_admin_source(self, source: str) -> str:
        source_key = source.strip().lower()
        if not source_key:
            raise ValueError("source required")
        item = self.db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == source_key))
        if not item:
            raise ValueError("source not found")
        self.db.delete(item)
        self.db.commit()
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(self.db)
        return source_key

    def test_source_connection(
        self,
        source: str | None,
        api_base: str | None,
        api_key: str | None,
        auth_mode: str = "bearer",
        key_param: str = "key",
    ) -> dict:
        """测试数据源连通与取数（按 source 适配 GET/POST 与鉴权方式）。"""
        sk = (source or "").strip().lower() or None
        ab = (api_base or "").strip() or None
        if not sk and not ab:
            raise ValueError("请提供 source（已保存的数据源标识）或 api_base（接口地址）")
        url = ""
        if sk:
            row = self.db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == sk))
            if not row:
                raise ValueError("数据源不存在")
            url = (row.api_base or "").strip()
        else:
            url = ab or ""
        if not url:
            raise ValueError("接口地址 api_base 为空，无法测试")
        headers: dict[str, str] = {
            "User-Agent": "AiTrends-Admin-SourceTest/1.0",
            "Accept": "application/json",
        }
        k = (api_key or "").strip()
        if not k and sk:
            k = load_stored_api_key_for_source(self.db, sk)
        if sk and source_uses_query_key_auth(sk):
            mode, kp = query_auth_for_source(sk)
        else:
            mode = (auth_mode or "bearer").strip().lower()
            kp = (key_param or "key").strip() or "key"
        if sk in ("newsapi", "thenewsapi") and not k:
            _, param = query_auth_for_source(sk)
            raise ValueError(
                f"{sk} 需要 API Key：请在卡片填写密钥并「保存」，或在测试前于密钥框输入一次（"
                f"请求 Query 参数 {param}）。"
            )
        ph_secret = ""
        if sk == "product_hunt":
            conn = self.db.scalar(
                select(ProductConnector)
                .where(ProductConnector.admin_source_key == "product_hunt")
                .order_by(ProductConnector.id)
                .limit(1)
            )
            if conn:
                cfg = dict(conn.config_json or {})
                if not k:
                    k = str(cfg.get("api_key") or "").strip()
                ph_secret = str(cfg.get("oauth_client_secret") or "").strip()
        if sk == "product_hunt":
            from .product_hunt_oauth import resolve_product_hunt_bearer

            try:
                bearer, _auth_mode_used = resolve_product_hunt_bearer(api_key=k, oauth_client_secret=ph_secret)
                headers["Authorization"] = f"Bearer {bearer}"
            except (ValueError, RuntimeError) as e:
                raise ValueError(str(e)) from e
        elif k:
            if mode == "private_token":
                headers["PRIVATE-TOKEN"] = k
            elif mode == "query_key":
                url = merge_api_key_into_url(url, api_key=k, key_param=kp)
            else:
                headers["Authorization"] = f"Bearer {k}"
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                # Product Hunt true data fetch: always use v2 GraphQL POST with a real query.
                if sk == "product_hunt":
                    if "Authorization" not in headers:
                        raise ValueError(
                            "product_hunt 需要 API Key（access_token）或同时填写 API Key（client_id）与 APP Secret（client_secret）"
                        )
                    code, body_text = sync_product_hunt_top_details(headers)
                    class _Resp:
                        status_code = code
                        text = body_text

                    r = _Resp()
                    url = "https://api.producthunt.com/v2/api/graphql"
                elif sk == "github" and github_trending_is_discovery_url(url):
                    code, body_text = sync_github_trending_top_details(url, headers)
                    class _RespGh:
                        status_code = code
                        text = body_text

                    r = _RespGh()
                elif sk == "hacker_news" and hacker_news_algolia_is_search_url(url):
                    code, body_text = sync_hacker_news_top_details(url, headers)
                    class _RespHn:
                        status_code = code
                        text = body_text

                    r = _RespHn()
                elif sk == "newsapi" and newsapi_is_v2_url(url):
                    code, body_text = sync_newsapi_top_headlines(url, headers, limit=3)
                    class _RespNewsapi:
                        status_code = code
                        text = body_text

                    r = _RespNewsapi()
                elif sk == "thenewsapi" and thenewsapi_is_news_url(url):
                    code, body_text = sync_thenewsapi_top_news(url, headers, limit=3)
                    class _RespThenewsapi:
                        status_code = code
                        text = body_text

                    r = _RespThenewsapi()
                elif sk == "anthropic":
                    # Anthropic Messages 仅支持 POST；用最小消息体做真实可用性测试。
                    if "Authorization" not in headers:
                        raise ValueError("anthropic 需要 API Key（Bearer）")
                    an_url = "https://api.anthropic.com/v1/messages"
                    payload = {
                        "model": "claude-3-5-haiku-latest",
                        "max_tokens": 16,
                        "messages": [{"role": "user", "content": "ping"}],
                    }
                    an_headers = {
                        **headers,
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01",
                    }
                    r = client.post(an_url, headers=an_headers, json=payload)
                    url = an_url
                else:
                    r = client.get(url, headers=headers)
            cap = (
                8000
                if sk == "product_hunt"
                or (sk == "github" and github_trending_is_discovery_url(url))
                or (sk == "hacker_news" and hacker_news_algolia_is_search_url(url))
                or (sk == "newsapi" and newsapi_is_v2_url(url))
                or (sk == "thenewsapi" and thenewsapi_is_news_url(url))
                else 600
            )
            snippet = (r.text or "")[:cap]
            code = r.status_code
            ok_http = 200 <= code < 300
            url_report = url[:512]
            if mode == "query_key" and k:
                from urllib.parse import urlsplit

                parts = urlsplit(url_report)
                url_report = f"{parts.scheme}://{parts.netloc}{parts.path}?…&{kp}=***"
            return {
                "http_status": code,
                "snippet": snippet,
                "ok": ok_http,
                "url_tested": url_report,
            }
        except Exception as e:
            return {
                "http_status": 0,
                "snippet": str(e)[:600],
                "ok": False,
                "url_tested": url[:512],
            }

    def get_overview_metrics(self) -> dict:
        return {
            "sources": self.db.query(AdminSourceConfig).count(),
            "admin_users": self.db.query(AdminUser).count(),
            "trends": self.db.query(Trend).count(),
            "signals": self.db.query(EvidenceSignal).count(),
        }

    def list_admin_users(self, role: str = "", keyword: str = "") -> list[dict]:
        stmt = select(AdminUser).order_by(AdminUser.created_at.asc())
        if role:
            stmt = stmt.where(AdminUser.role == role)
        if keyword:
            stmt = stmt.where(AdminUser.username.contains(keyword))
        items = self.db.scalars(stmt).all()
        return [
            {
                "username": i.username,
                "role": i.role,
                "enabled": i.enabled,
                "failed_attempts": i.failed_attempts,
                "locked_until": i.locked_until.isoformat() if i.locked_until else None,
                "created_at": i.created_at.isoformat(),
                "updated_at": i.updated_at.isoformat(),
            }
            for i in items
        ]

    def get_settings(self) -> dict:
        defaults = {
            "password_min_length": "10",
            "lock_minutes": "15",
            "max_failed_attempts": "5",
        }
        for key, value in defaults.items():
            item = self.db.scalar(select(AdminSetting).where(AdminSetting.key == key))
            if not item:
                self.db.add(AdminSetting(key=key, value=value, updated_at=datetime.utcnow()))
        self.db.commit()
        rows = self.db.scalars(select(AdminSetting)).all()
        settings = {r.key: r.value for r in rows}
        return {
            "password_min_length": int(settings.get("password_min_length", "10")),
            "lock_minutes": int(settings.get("lock_minutes", "15")),
            "max_failed_attempts": int(settings.get("max_failed_attempts", "5")),
        }

    def update_settings(self, payload: dict) -> dict:
        for key, value in payload.items():
            item = self.db.scalar(select(AdminSetting).where(AdminSetting.key == key))
            if not item:
                item = AdminSetting(key=key)
                self.db.add(item)
            item.value = str(value)
            item.updated_at = datetime.utcnow()
        self.db.commit()
        return self.get_settings()
