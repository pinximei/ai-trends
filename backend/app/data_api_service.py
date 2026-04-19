from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AdminSetting, AdminSourceConfig, AdminUser, AuditLog, EvidenceSignal, RemovalRequest, Trend
from .scope_labels_util import apply_scope_labels_to_row, get_scope_labels_from_source, normalize_scope_labels_from_payload

VALID_PERIODS = {"day", "week", "month", "quarter", "year"}


class DataApiService:
    """Single gateway for all DB access."""

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard_summary(self) -> dict:
        total_trends = self.db.query(Trend).count()
        updated_at = self.db.scalar(select(Trend.updated_at).order_by(Trend.updated_at.desc()))
        return {
            "active_use_cases": total_trends,
            "new_apps": total_trends * 3,
            "emerging_trends": self.db.query(Trend).filter(Trend.lifecycle_stage == "emerging").count(),
            "declining_trends": self.db.query(Trend).filter(Trend.lifecycle_stage == "declining").count(),
            "updated_at": str(updated_at) if updated_at else None,
        }

    def get_trends(self, period: str) -> dict:
        if period not in VALID_PERIODS:
            raise ValueError("invalid period")
        items = self.db.scalars(select(Trend).order_by(Trend.trend_score.desc())).all()
        factor = {"day": 0.96, "week": 1.0, "month": 1.03, "quarter": 1.06, "year": 1.1}[period]
        return {
            "items": [
                {
                    "trend_key": t.trend_key,
                    "trend_score": round(t.trend_score * factor, 1),
                    "confidence": t.confidence,
                    "lifecycle_stage": t.lifecycle_stage,
                    "score_components": t.score_components_json,
                    "algo_version": t.algo_version,
                    "taxonomy_version": t.taxonomy_version,
                    "sample_size": t.sample_size,
                    "period": period,
                }
                for t in items
            ],
            "cursor": None,
        }

    def get_trend_detail(self, trend_key: str) -> dict | None:
        trend = self.db.scalar(select(Trend).where(Trend.trend_key == trend_key))
        if not trend:
            return None
        evidences = self.db.scalars(select(EvidenceSignal).where(EvidenceSignal.trend_key == trend_key)).all()
        return {
            "trend_key": trend.trend_key,
            "trend_score": trend.trend_score,
            "score_components": trend.score_components_json,
            "algo_version": trend.algo_version,
            "taxonomy_version": trend.taxonomy_version,
            "lifecycle_stage": trend.lifecycle_stage,
            "sample_size": trend.sample_size,
            "evidence_count": len(evidences),
        }

    def get_inspirations(self, period: str) -> dict:
        if period not in VALID_PERIODS:
            raise ValueError("invalid period")
        items = self.db.scalars(select(EvidenceSignal).where(EvidenceSignal.status == "active")).all()
        cutoff_days = {"day": 1, "week": 7, "month": 30, "quarter": 91, "year": 365}[period]
        cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
        payload = []
        for item in items:
            created = item.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                continue
            payload.append(
                {
                    "signal_id": item.signal_id,
                    "title": item.trend_key.replace("-", " ").title(),
                    "source": item.source,
                    "trend_key": item.trend_key,
                    "evidence_score": item.evidence_score,
                }
            )
        if not payload:
            for item in items[:6]:
                payload.append(
                    {
                        "signal_id": item.signal_id,
                        "title": item.trend_key.replace("-", " ").title(),
                        "source": item.source,
                        "trend_key": item.trend_key,
                        "evidence_score": item.evidence_score,
                    }
                )
        return {"items": payload, "cursor": None, "period": period}

    def get_evidence(self, signal_id: str) -> dict | None:
        item = self.db.scalar(select(EvidenceSignal).where(EvidenceSignal.signal_id == signal_id))
        if not item:
            return None
        return {
            "signal_id": item.signal_id,
            "trend_key": item.trend_key,
            "source": item.source,
            "evidence_url": item.evidence_url,
            "source_diversity": item.source_diversity,
            "label_stability": item.label_stability,
            "trace": "trend_scores -> trend_features -> evidence_signals -> normalized_events -> raw_events",
        }

    def get_content_briefing(self, period: str = "week", trend_limit: int = 5, signal_limit: int = 12, lang: str = "zh") -> dict:
        if period not in VALID_PERIODS:
            raise ValueError("invalid period")

        trend_cap = max(1, min(trend_limit, 10))
        trends = self.db.scalars(
            select(Trend).where(Trend.period_type == period).order_by(Trend.trend_score.desc()).limit(trend_cap)
        ).all()
        trend_selection_mode = "period_match"
        if not trends:
            trends = self.db.scalars(select(Trend).order_by(Trend.trend_score.desc()).limit(trend_cap)).all()
            trend_selection_mode = "fallback_global"
        signals = self.db.scalars(select(EvidenceSignal).where(EvidenceSignal.status == "active").order_by(EvidenceSignal.evidence_score.desc())).all()
        if not trends:
            return {
                "title": "暂无可生成文章的数据" if lang == "zh" else "No data available for briefing",
                "summary": "当前数据库中没有趋势数据，请先初始化模拟数据或接入采集任务。"
                if lang == "zh"
                else "No trends in current database. Seed demo data or run ingestion first.",
                "period": period,
                "generated_at": datetime.utcnow().isoformat(),
                "hero": {"kicker": "AISoul Briefing", "headline": "No data", "subheadline": "Seed data and retry"},
                "sections": [],
                "facts": [],
                "media": [],
            }

        cutoff_days = {"day": 1, "week": 7, "month": 30, "quarter": 91, "year": 365}[period]
        cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
        recent_signals: list[EvidenceSignal] = []
        for s in signals:
            created = s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
            if created >= cutoff:
                recent_signals.append(s)
        signal_selection_mode = "in_window"
        if not recent_signals:
            recent_signals = signals[:signal_limit]
            signal_selection_mode = "fallback_global"
        else:
            recent_signals = recent_signals[:signal_limit]

        signals_by_trend: dict[str, list[EvidenceSignal]] = defaultdict(list)
        for s in recent_signals:
            signals_by_trend[s.trend_key].append(s)

        top = trends[0]
        facts: list[dict] = []
        for t in trends:
            facts.append(
                {
                    "kind": "trend",
                    "id": t.trend_key,
                    "text": f"{t.trend_key} score={t.trend_score:.1f}, confidence={t.confidence:.2f}, sample={t.sample_size}, stage={t.lifecycle_stage}",
                    "source": "trend_scores_periodic",
                    "url": "",
                }
            )
        for s in recent_signals:
            facts.append(
                {
                    "kind": "signal",
                    "id": s.signal_id,
                    "text": f"{s.signal_id} from {s.source}, trend={s.trend_key}, evidence_score={s.evidence_score:.2f}",
                    "source": s.source,
                    "url": s.evidence_url,
                }
            )

        sections: list[dict] = []
        sections.append(
            {
                "title": "核心结论" if lang == "zh" else "Key findings",
                "content": (
                    (
                        f"按当前简报数据集排序，`{top.trend_key}` 位列第一。"
                        f"趋势分数 {top.trend_score:.1f}，置信度 {top.confidence:.2f}，样本量 {top.sample_size}。"
                        "结论仅来自已采集事实与可回溯信号。"
                    )
                    if lang == "zh"
                    else (
                        f"Based on the current briefing dataset ranking, `{top.trend_key}` is ranked first. "
                        f"Trend score {top.trend_score:.1f}, confidence {top.confidence:.2f}, sample size {top.sample_size}. "
                        "The statements are generated from collected facts and traceable signals only."
                    )
                ),
                "citations": [f["id"] for f in facts if f["kind"] == "trend"][:3],
            }
        )

        for t in trends[:3]:
            trend_signals = signals_by_trend.get(t.trend_key, [])
            signal_lines = (
                "；".join([f"{s.signal_id}({s.source}, score={s.evidence_score:.2f})" for s in trend_signals[:4]])
                if trend_signals
                else "该趋势在本周期可用信号较少，需继续采样。"
            )
            sections.append(
                {
                    "title": f"趋势解读：{t.trend_key}" if lang == "zh" else f"Trend interpretation: {t.trend_key}",
                    "content": (
                        f"生命周期 `{t.lifecycle_stage}`，趋势分数 `{t.trend_score:.1f}`，置信度 `{t.confidence:.2f}`。关联信号：{signal_lines}"
                        if lang == "zh"
                        else (
                            f"Lifecycle `{t.lifecycle_stage}`, trend score `{t.trend_score:.1f}`, confidence `{t.confidence:.2f}`. "
                            f"Related signals: {signal_lines}"
                        )
                    ),
                    "citations": [s.signal_id for s in trend_signals[:4]],
                }
            )

        media: list[dict] = []
        for s in recent_signals:
            url = (s.evidence_url or "").strip()
            if not url:
                continue
            media_type = "link"
            low = url.lower()
            if low.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                media_type = "image"
            elif low.endswith((".mp4", ".webm", ".mov")):
                media_type = "video"
            media.append(
                {
                    "type": media_type,
                    "title": f"{s.signal_id} · {s.trend_key}",
                    "url": url,
                    "source": s.source,
                }
            )

        summary = (
            f"本次简报共纳入 {len(trends)} 个趋势与 {len(recent_signals)} 条信号。所有结论均附事实引用，可回溯到具体 signal 与来源链接。"
            if lang == "zh"
            else f"This briefing includes {len(trends)} trends and {len(recent_signals)} signals. Every statement is citation-backed and traceable."
        )
        return {
            "title": f"AISoul {period.title()} Briefing",
            "summary": summary,
            "period": period,
            "generated_at": datetime.utcnow().isoformat(),
            "hero": {
                "kicker": "基于证据的 AI 简报" if lang == "zh" else "Evidence-based AI Briefing",
                "headline": (
                    f"{top.trend_key.replace('-', ' ').title()} 在当前简报中排名第一"
                    if lang == "zh"
                    else f"{top.trend_key.replace('-', ' ').title()} ranks first in current briefing"
                ),
                "subheadline": (
                    "内容仅根据已追踪事实生成，所有结论带引用与来源链接。"
                    if lang == "zh"
                    else "Generated from tracked facts only, with citations and source links."
                ),
            },
            "selection": {
                "trend_selection_mode": trend_selection_mode,
                "signal_selection_mode": signal_selection_mode,
            },
            "sections": sections,
            "facts": facts,
            "media": media[:8],
        }

    def list_admin_sources(self, keyword: str = "") -> list[dict]:
        stmt = select(AdminSourceConfig).order_by(AdminSourceConfig.source.asc())
        if keyword:
            stmt = stmt.where(AdminSourceConfig.source.contains(keyword))
        items = self.db.scalars(stmt).all()
        return [
            {
                "source": i.source,
                "enabled": i.enabled,
                "frequency": i.frequency,
                "api_base": i.api_base,
                "api_key_masked": i.api_key_masked,
                "scope_label": i.scope_label or "",
                "scope_labels": get_scope_labels_from_source(i),
                "notes": i.notes,
                "updated_at": i.updated_at.isoformat(),
            }
            for i in items
        ]

    def upsert_admin_source(self, payload: dict, mask_func) -> dict:
        source = payload["source"].strip().lower()
        if not source:
            raise ValueError("source required")
        item = self.db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == source))
        if not item:
            item = AdminSourceConfig(source=source)
            self.db.add(item)
        item.enabled = payload["enabled"]
        item.frequency = payload["frequency"].strip() or "daily_07:00"
        item.api_base = payload["api_base"].strip()
        if payload["api_key"].strip():
            item.api_key_masked = mask_func(payload["api_key"])
        item.notes = payload["notes"].strip()
        labels = normalize_scope_labels_from_payload(payload)
        apply_scope_labels_to_row(item, labels)
        item.updated_at = datetime.utcnow()
        self.db.commit()
        from .taxonomy_from_sources import sync_product_taxonomy_from_admin_sources

        sync_product_taxonomy_from_admin_sources(self.db)
        labels = get_scope_labels_from_source(item)
        return {
            "source": item.source,
            "enabled": item.enabled,
            "frequency": item.frequency,
            "api_base": item.api_base,
            "api_key_masked": item.api_key_masked,
            "scope_label": item.scope_label or "",
            "scope_labels": labels,
            "notes": item.notes,
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
    ) -> dict:
        """GET 请求 api_base；密钥可选 Bearer 或 GitLab PRIVATE-TOKEN。"""
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
            "User-Agent": "AISoul-Admin-SourceTest/1.0",
            "Accept": "application/json",
        }
        k = (api_key or "").strip()
        if k:
            mode = (auth_mode or "bearer").strip().lower()
            if mode == "private_token":
                headers["PRIVATE-TOKEN"] = k
            else:
                headers["Authorization"] = f"Bearer {k}"
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                r = client.get(url, headers=headers)
            snippet = (r.text or "")[:600]
            code = r.status_code
            # 2xx–3xx：正常；401/403：服务可达但需密钥；405：常见为仅支持 POST 的端点；429：限流但服务可达。
            ok_http = (200 <= code < 400) or code in (401, 403, 405, 429)
            return {
                "http_status": code,
                "snippet": snippet,
                "ok": ok_http,
                "url_tested": url[:512],
            }
        except Exception as e:
            return {
                "http_status": 0,
                "snippet": str(e)[:600],
                "ok": False,
                "url_tested": url[:512],
            }

    def list_removal_requests(self, status: str = "", keyword: str = "") -> list[dict]:
        stmt = select(RemovalRequest).order_by(RemovalRequest.submitted_at.desc())
        if status:
            stmt = stmt.where(RemovalRequest.status == status)
        if keyword:
            stmt = stmt.where(RemovalRequest.ticket_id.contains(keyword))
        items = self.db.scalars(stmt).all()
        return [
            {
                "ticket_id": i.ticket_id,
                "status": i.status,
                "request_type": i.request_type,
                "target_signal_id": i.target_signal_id,
                "reason": i.reason,
                "requester_contact": i.requester_contact,
                "submitted_at": i.submitted_at.isoformat(),
            }
            for i in items
        ]

    def resolve_removal_request(self, ticket_id: str) -> dict | None:
        item = self.db.scalar(select(RemovalRequest).where(RemovalRequest.ticket_id == ticket_id))
        if not item:
            return None
        item.status = "executed"
        self.db.commit()
        return {"ticket_id": ticket_id, "status": item.status}

    def get_overview_metrics(self) -> dict:
        return {
            "sources": self.db.query(AdminSourceConfig).count(),
            "tickets": self.db.query(RemovalRequest).count(),
            "pending_tickets": self.db.query(RemovalRequest).filter(RemovalRequest.status != "executed").count(),
            "admin_users": self.db.query(AdminUser).count(),
            "audit_logs": self.db.query(AuditLog).count(),
            "trends": self.db.query(Trend).count(),
            "signals": self.db.query(EvidenceSignal).count(),
        }

    def list_audit_logs(self, limit: int = 50) -> list[dict]:
        count = max(1, min(limit, 200))
        items = self.db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(count)).all()
        return [
            {
                "actor": i.actor,
                "action": i.action,
                "target": i.target,
                "detail": i.detail,
                "request_id": i.request_id,
                "created_at": i.created_at.isoformat(),
            }
            for i in items
        ]

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

    def query_trends(self, keyword: str = "", lifecycle: str = "", limit: int = 50) -> list[dict]:
        count = max(1, min(limit, 200))
        stmt = select(Trend).order_by(Trend.updated_at.desc()).limit(count)
        if keyword:
            stmt = stmt.where(Trend.trend_key.contains(keyword))
        if lifecycle:
            stmt = stmt.where(Trend.lifecycle_stage == lifecycle)
        items = self.db.scalars(stmt).all()
        return [
            {
                "trend_key": t.trend_key,
                "lifecycle_stage": t.lifecycle_stage,
                "trend_score": t.trend_score,
                "confidence": t.confidence,
                "sample_size": t.sample_size,
                "updated_at": t.updated_at.isoformat(),
            }
            for t in items
        ]

    def query_signals(self, keyword: str = "", source: str = "", status: str = "", limit: int = 80) -> list[dict]:
        count = max(1, min(limit, 200))
        stmt = select(EvidenceSignal).order_by(EvidenceSignal.created_at.desc()).limit(count)
        if keyword:
            stmt = stmt.where(EvidenceSignal.signal_id.contains(keyword) | EvidenceSignal.trend_key.contains(keyword))
        if source:
            stmt = stmt.where(EvidenceSignal.source == source)
        if status:
            stmt = stmt.where(EvidenceSignal.status == status)
        items = self.db.scalars(stmt).all()
        return [
            {
                "signal_id": i.signal_id,
                "trend_key": i.trend_key,
                "source": i.source,
                "status": i.status,
                "evidence_score": i.evidence_score,
                "created_at": i.created_at.isoformat(),
            }
            for i in items
        ]

    def update_trend_ops(self, trend_key: str, payload: dict) -> dict | None:
        item = self.db.scalar(select(Trend).where(Trend.trend_key == trend_key))
        if not item:
            return None
        if payload.get("lifecycle_stage") is not None:
            item.lifecycle_stage = payload["lifecycle_stage"]
        if payload.get("trend_score") is not None:
            item.trend_score = float(payload["trend_score"])
        item.updated_at = datetime.utcnow()
        self.db.commit()
        return {
            "trend_key": item.trend_key,
            "lifecycle_stage": item.lifecycle_stage,
            "trend_score": item.trend_score,
            "updated_at": item.updated_at.isoformat(),
        }

    def update_signal_ops(self, signal_id: str, payload: dict) -> dict | None:
        item = self.db.scalar(select(EvidenceSignal).where(EvidenceSignal.signal_id == signal_id))
        if not item:
            return None
        if payload.get("status") is not None:
            item.status = payload["status"]
        self.db.commit()
        return {
            "signal_id": item.signal_id,
            "status": item.status,
            "trend_key": item.trend_key,
            "source": item.source,
        }

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
