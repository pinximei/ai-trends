import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, AdminSession, AdminSourceConfig, EvidenceSignal, PipelineRun, RemovalRequest, Trend
from .scope_labels_util import dump_scope_labels_json


# 预设条目 content_role（后台展示与运营选型；与入库「一篇稿」能力无关）：
# - daily_editorial：条目型资讯/动态（报道、RSS、问答帖、仓库 issue 等）
# - academic：论文/著作记录
CONTENT_ROLE_LABEL_ZH: dict[str, str] = {
    "daily_editorial": "条目型内容（资讯/RSS/问答/动态）",
    "academic": "学术论文元数据",
    "runnable_apps": "可运行应用（Spaces 等演示入口）",
    "app_launches": "应用首发（Product Hunt）",
}


# 后台「数据源」预设：仅当库中尚无该 source 时插入，不覆盖运营已改过的行。
# 下列含 **免 Key** 与 **需 OAuth** 的模板：Product Hunt 须在连接器或「测试连接」中提供 **Bearer access_token**。
MAINSTREAM_ADMIN_SOURCE_PRESETS: list[dict] = [
    {
        "source": "github",
        "preset_label": "GitHub",
        "enabled": True,
        "api_base": "https://api.github.com/repos/microsoft/vscode/issues?state=all&per_page=8&sort=updated",
        "api_key_masked": "",
        "scope_label": "AI｜通用·开源协作",
        "content_role": "daily_editorial",
        "notes": "公开仓库 **Issues 列表** JSON（免 Key，有速率限制）。更接近「仓库动态」；可改为其它 org/repo 路径。",
    },
    {
        "source": "huggingface_spaces",
        "preset_label": "Hugging Face Spaces",
        "enabled": True,
        "api_base": "https://huggingface.co/api/spaces?limit=24",
        "api_key_masked": "",
        "scope_label": "AI｜Spaces·应用",
        "content_role": "runnable_apps",
        "notes": "Spaces 公开列表 JSON：用于 **应用/可运行演示** 发现（免 Key）；私有 Space 请填 HF_TOKEN。后台请 **启用** 对应连接器并配置 LLM，稿件才会进「应用」泳道。",
    },
    {
        "source": "product_hunt",
        "preset_label": "Product Hunt",
        "enabled": True,
        "api_base": "https://api.producthunt.com/v2/api/graphql",
        "api_key_masked": "",
        "scope_label": "AI｜应用发现",
        "content_role": "app_launches",
        "notes": "Product Hunt **GraphQL v2**（同步与测试连接走 POST，见连接器逻辑）。须在连接器 ``config_json`` 填 **Bearer access_token**（Developer OAuth），或在「测试连接」粘贴临时 Token。无 Token 时探测可能为 401，属正常。",
    },
    {
        "source": "hacker_news",
        "preset_label": "Hacker News",
        "enabled": True,
        "api_base": "https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=20",
        "api_key_masked": "",
        "scope_label": "通用·技术资讯",
        "content_role": "daily_editorial",
        "notes": "HN Algolia 公开搜索 JSON：含标题/链接/时间等 **条目型** 字段（免 Key）。",
    },
    {
        "source": "stackoverflow",
        "preset_label": "Stack Overflow",
        "enabled": True,
        "api_base": "https://api.stackexchange.com/2.3/questions?order=desc&sort=activity&site=stackoverflow&pagesize=10",
        "api_key_masked": "",
        "scope_label": "开发·问答",
        "content_role": "daily_editorial",
        "notes": "Stack Overflow **最新问题** JSON（标题+摘要等）；可选填 app key 提高配额。",
    },
    {
        "source": "arxiv",
        "preset_label": "arXiv",
        "enabled": True,
        "api_base": "https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=lastUpdatedDate&sortOrder=descending&max_results=5",
        "api_key_masked": "",
        "scope_label": "学术·论文",
        "content_role": "academic",
        "notes": "arXiv **cs.AI** 按最近更新排序的 Atom（论文条目+摘要）。",
    },
    {
        "source": "openalex",
        "preset_label": "OpenAlex",
        "enabled": True,
        "api_base": "https://api.openalex.org/works?per_page=5&sort=cited_by_count:desc",
        "api_key_masked": "",
        "scope_label": "学术·开放图谱",
        "content_role": "academic",
        "notes": "OpenAlex 著作 JSON；偏 **学术条目**，不是大众门户资讯；polite pool 可按文档加 polite 参数（可选）。",
    },
    {
        "source": "rss_arstechnica",
        "preset_label": "Ars Technica RSS",
        "enabled": True,
        "api_base": "https://feeds.arstechnica.com/arstechnica/index",
        "api_key_masked": "",
        "scope_label": "通用·科技媒体",
        "content_role": "daily_editorial",
        "notes": "Ars Technica **RSS（XML）**：站点文章条目；单连接器仍合成一篇稿，可改为你方站点/栏目 Feed。",
    },
    {
        "source": "rss_theverge",
        "preset_label": "The Verge RSS",
        "enabled": True,
        "api_base": "https://www.theverge.com/rss/index.xml",
        "api_key_masked": "",
        "scope_label": "通用·科技媒体",
        "content_role": "daily_editorial",
        "notes": "The Verge **RSS（XML）**：站点文章条目。",
    },
]

# 历史上由 ensure_mainstream_admin_sources 写入、但已从产品移除的 source；启动时删库内对应行及同 admin_source_key 的连接器。
# 勿把仍保留在 MAINSTREAM_ADMIN_SOURCE_PRESETS 中的标识放进本集合，否则会误删运营已配置的 Key。
DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES: frozenset[str] = frozenset(
    {
        "mcp_skills",
        "newsapi",
        "openai",
        "google_gemini",
        "finnhub",
        "youtube_data",
        "mapbox",
    }
)
assert not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES.intersection(
    {row["source"] for row in MAINSTREAM_ADMIN_SOURCE_PRESETS}
), "DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES overlaps MAINSTREAM_ADMIN_SOURCE_PRESETS"


def sync_catalog_preset_metadata(db: Session) -> int:
    """将内置目录中的 preset_label / content_role 写入主流 source，仅当对应列为空（便于运营日后自定义）。"""
    n = 0
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        src = row["source"]
        item = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == src))
        if not item:
            continue
        pl = (row.get("preset_label") or "").strip() or src.replace("_", " ").title()
        cr = str(row.get("content_role") or "daily_editorial").strip() or "daily_editorial"
        changed = False
        if not (item.preset_label or "").strip():
            item.preset_label = pl
            changed = True
        if not (item.content_role or "").strip():
            item.content_role = cr
            changed = True
        if changed:
            n += 1
    if n:
        db.commit()
    return n


def ensure_mainstream_admin_sources(db: Session) -> int:
    """补全主流数据源行；已存在的 source 不修改。"""
    n = 0
    for row in MAINSTREAM_ADMIN_SOURCE_PRESETS:
        source = row["source"]
        exists = db.scalar(select(AdminSourceConfig.id).where(AdminSourceConfig.source == source))
        if exists:
            continue
        sl = row.get("scope_label") or ""
        pl = (row.get("preset_label") or "").strip() or source.replace("_", " ").title()
        cr = str(row.get("content_role") or "daily_editorial").strip() or "daily_editorial"
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
                preset_label=pl,
                content_role=cr,
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
            source="hacker_news",
            evidence_url="https://news.ycombinator.com/item?id=1",
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
