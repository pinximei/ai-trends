import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, AdminSession, AdminSourceConfig, EvidenceSignal, PipelineRun, RemovalRequest, Trend
from .scope_labels_util import dump_scope_labels_json


# 后台「数据源」预设：仅当库中尚无该 source 时插入，不覆盖运营已改过的行。
# 仅保留与「AI 资讯 / 模型 / 学术」直接相关、免密钥且响应足够长的公开端点；其它请在后台手动添加。
# scope_label：标明所属领域/板块，便于与「行业→板块」前台结构对应。
MAINSTREAM_ADMIN_SOURCE_PRESETS: list[dict] = [
    {
        "source": "github",
        "enabled": True,
        "api_base": "https://api.github.com/repos/octocat/Hello-World",
        "api_key_masked": "",
        "scope_label": "AI｜通用·开源协作",
        "notes": "公开仓库元数据 JSON（免 Key，有速率限制）。高配额可填 PAT 并改为 issues/releases 等路径。",
    },
    {
        "source": "huggingface",
        "enabled": True,
        "api_base": "https://huggingface.co/api/models?limit=3",
        "api_key_masked": "",
        "scope_label": "AI｜大模型/生态",
        "notes": "Hugging Face Hub 公开模型列表；私有或提配额请填 HF_TOKEN。",
    },
    {
        "source": "huggingface_spaces",
        "enabled": True,
        "api_base": "https://huggingface.co/api/spaces?limit=3",
        "api_key_masked": "",
        "scope_label": "AI｜Spaces·应用",
        "notes": "Spaces 公开列表；私有 Space 请填 HF_TOKEN。",
    },
    {
        "source": "hacker_news",
        "enabled": True,
        "api_base": "https://hacker-news.firebaseio.com/v0/topstories.json",
        "api_key_masked": "",
        "scope_label": "通用·技术资讯",
        "notes": "Hacker News 官方 Firebase API：热门 story id 列表（免 Key）。勿用 maxitem 单数字端点（响应过短无法入库）。",
    },
    {
        "source": "arxiv",
        "enabled": True,
        "api_base": "https://export.arxiv.org/api/query?search_query=all&start=0&max_results=1",
        "api_key_masked": "",
        "scope_label": "学术·论文",
        "notes": "arXiv 开放元数据与摘要，免 Key。",
    },
    {
        "source": "openalex",
        "enabled": True,
        "api_base": "https://api.openalex.org/works?per_page=3",
        "api_key_masked": "",
        "scope_label": "学术·开放图谱",
        "notes": "OpenAlex 开放学术图谱，免 Key；polite pool 建议按文档加 polite 参数（可选）。",
    },
]

# 与 admin GET /api/admin/v1/sources/presets 展示名一致；供前端静态回退 JSON 与后端共用逻辑。
PRESET_SOURCE_LABELS: dict[str, str] = {
    "github": "GitHub",
    "huggingface": "Hugging Face",
    "huggingface_spaces": "Hugging Face Spaces",
    "hacker_news": "Hacker News",
    "arxiv": "arXiv",
    "openalex": "OpenAlex",
}

# 历史上由 ensure_mainstream_admin_sources 写入、但已从 MAINSTREAM_ADMIN_SOURCE_PRESETS 撤下的 source。
# 应用启动时会删除 admin_source_configs 对应行及 admin_source_key 相同的 ProductConnector。
# 注意：若自建数据源使用了与下列相同的 source 标识，也会被一并删除；请改用不与内置冲突的标识。
DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES: frozenset[str] = frozenset(
    {
        "product_hunt",
        "mcp_skills",
        "newsapi",
        "openai",
        "google_gemini",
        "finnhub",
        "youtube_data",
        "mapbox",
        "stackoverflow",
        "open_meteo",
        "coingecko",
        "pypi",
        "npm",
        "alphavantage",
        "docker_hub",
        "crates_io",
    }
)
assert not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES.intersection(
    {row["source"] for row in MAINSTREAM_ADMIN_SOURCE_PRESETS}
), "DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES overlaps MAINSTREAM_ADMIN_SOURCE_PRESETS"


def build_admin_source_preset_items() -> list[dict]:
    """供 /api/admin/v1/sources/presets 与前端静态回退文件生成。"""
    items: list[dict] = []
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        src = row["source"]
        sl = row.get("scope_label") or ""
        items.append(
            {
                "source": src,
                "label": PRESET_SOURCE_LABELS.get(src, src.replace("_", " ").title()),
                "api_base": row["api_base"],
                "frequency": "scheduled",
                "scope_label": sl,
                "scope_labels": [sl] if sl else [],
                "notes": row.get("notes") or "",
                "enabled": bool(row.get("enabled", True)),
            }
        )
    return items


def ensure_mainstream_admin_sources(db: Session) -> int:
    """补全主流数据源行；已存在的 source 不修改。"""
    n = 0
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        source = row["source"]
        exists = db.scalar(select(AdminSourceConfig.id).where(AdminSourceConfig.source == source))
        if exists:
            continue
        sl = row.get("scope_label") or ""
        db.add(
            AdminSourceConfig(
                source=source,
                enabled=row["enabled"],
                frequency="scheduled",
                api_base=row["api_base"],
                api_key_masked=row["api_key_masked"],
                scope_label=sl,
                scope_labels_json=dump_scope_labels_json([sl]) if sl else "[]",
                notes=row["notes"],
                updated_at=datetime.utcnow(),
            )
        )
        n += 1
    if n:
        db.commit()
    return n


def envelope(data, message="ok", code=0, request_id=None):
    return {
        "code": code,
        "message": message,
        "data": data,
        "request_id": request_id or str(uuid.uuid4()),
    }


def seed_if_empty(db: Session):
    if db.scalar(select(Trend.id).limit(1)):
        return
    trend_templates = [
        (
            "workflow-automation-agent",
            78.2,
            0.84,
            "growth",
            {"adoption": 0.30, "persistence": 0.25, "cross_source": 0.15, "burst": 0.20, "novelty": 0.10},
            124,
        ),
        (
            "customer-support-agent",
            73.4,
            0.79,
            "emerging",
            {"adoption": 0.22, "persistence": 0.20, "cross_source": 0.18, "burst": 0.25, "novelty": 0.15},
            96,
        ),
        (
            "multimodal-content-agent",
            69.1,
            0.76,
            "emerging",
            {"adoption": 0.18, "persistence": 0.21, "cross_source": 0.19, "burst": 0.23, "novelty": 0.19},
            88,
        ),
    ]
    periods = [
        ("day", "2026-04-14", 0.97),
        ("week", "2026-04-06", 1.0),
        ("month", "2026-04-01", 1.03),
        ("quarter", "2026-04-01", 1.06),
        ("year", "2026-01-01", 1.1),
    ]
    trends = []
    for period_type, period_start, factor in periods:
        for trend_key, score, conf, stage, components, sample_size in trend_templates:
            trends.append(
                Trend(
                    trend_key=trend_key,
                    period_type=period_type,
                    period_start=period_start,
                    trend_score=round(score * factor, 1),
                    confidence=conf,
                    lifecycle_stage=stage,
                    score_components_json=json.dumps(components),
                    sample_size=sample_size,
                )
            )
    evidences = [
        EvidenceSignal(
            signal_id="sig_001",
            trend_key="workflow-automation-agent",
            source="github",
            evidence_url="https://github.com/example/workflow-agent",
            evidence_score=0.88,
            source_diversity=0.60,
            label_stability=0.80,
        ),
        EvidenceSignal(
            signal_id="sig_002",
            trend_key="customer-support-agent",
            source="huggingface",
            evidence_url="https://huggingface.co/spaces/example/support-agent",
            evidence_score=0.81,
            source_diversity=0.55,
            label_stability=0.77,
        ),
        EvidenceSignal(
            signal_id="sig_003",
            trend_key="multimodal-content-agent",
            source="github",
            evidence_url="https://github.com/example/multimodal-content-agent",
            evidence_score=0.79,
            source_diversity=0.52,
            label_stability=0.74,
        ),
        EvidenceSignal(
            signal_id="sig_004",
            trend_key="workflow-automation-agent",
            source="design-showcase",
            evidence_url="https://images.unsplash.com/photo-1518770660439-4636190af475",
            evidence_score=0.75,
            source_diversity=0.48,
            label_stability=0.72,
        ),
        EvidenceSignal(
            signal_id="sig_005",
            trend_key="multimodal-content-agent",
            source="video-demo",
            evidence_url="https://www.w3schools.com/html/mov_bbb.mp4",
            evidence_score=0.77,
            source_diversity=0.51,
            label_stability=0.76,
        ),
    ]
    db.add_all(trends)
    db.add_all(evidences)
    db.commit()


def clear_business_data(db: Session):
    db.query(EvidenceSignal).delete()
    db.query(Trend).delete()
    db.query(RemovalRequest).delete()
    db.query(PipelineRun).delete()
    db.query(AdminSourceConfig).delete()
    db.query(AuditLog).delete()
    db.query(AdminSession).delete()
    db.commit()


def clear_product_ingest_data(db: Session) -> dict[str, int]:
    """清空连接器入库产生的资源数据（文章、指标点、同步日志、热门快照、LLM 用量），并重置各连接器上次同步时间。

    同时移除由数据源合并生成的「领域」行业（slug=domains）及其下属板块与关联指标/分类侧数据；连接器配置与数据源账号、演示用 ``ai`` 等行业保留。
    """
    from .product_models import (
        Article,
        HotSnapshot,
        LlmUsageLog,
        MetricPoint,
        ProductConnector,
        ProductConnectorLog,
    )
    from .taxonomy_from_sources import clear_merged_domains_taxonomy

    n_logs = int(db.query(ProductConnectorLog).delete() or 0)
    n_points = int(db.query(MetricPoint).delete() or 0)
    n_articles = int(db.query(Article).delete() or 0)
    n_hot = int(db.query(HotSnapshot).delete() or 0)
    n_llm = int(db.query(LlmUsageLog).delete() or 0)
    tax = clear_merged_domains_taxonomy(db)
    for c in db.scalars(select(ProductConnector)).all():
        c.last_sync_at = None
        c.last_error = None
    db.commit()
    return {
        "product_connector_logs": n_logs,
        "product_metric_points": n_points,
        "product_articles": n_articles,
        "product_hot_snapshots": n_hot,
        "product_llm_usage_logs": n_llm,
        **tax,
    }


def seed_demo_bundle(db: Session):
    seed_if_empty(db)
    ensure_mainstream_admin_sources(db)


def get_or_create_run(db: Session, req):
    existing = db.scalar(
        select(PipelineRun).where(PipelineRun.idempotency_key == req.idempotency_key).order_by(PipelineRun.started_at.desc())
    )
    if existing:
        return existing
    run = PipelineRun(
        run_id=f"run_{uuid.uuid4().hex[:12]}",
        job_type=req.job_type,
        status="running",
        idempotency_key=req.idempotency_key,
        started_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_removal_ticket(db: Session, req):
    ticket_id = f"t_{uuid.uuid4().hex[:10]}"
    token = uuid.uuid4().hex[:16]
    item = RemovalRequest(
        ticket_id=ticket_id,
        token=token,
        request_type=req.request_type,
        requester_contact=req.requester_contact,
        target_signal_id=req.target_signal_id,
        reason=req.reason,
        status="submitted",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
