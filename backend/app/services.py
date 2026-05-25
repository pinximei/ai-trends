import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, AdminSession, AdminSourceConfig, EvidenceSignal, PipelineRun, RemovalRequest, Trend
from .admin_source_fetch import PRESET_FETCH_LIMIT, default_fetch_limit_for_source, normalize_fetch_limit
from .scope_labels_util import dump_scope_labels_json


# 预设条目 content_role（后台展示与运营选型；与入库「一篇稿」能力无关）：
# - daily_editorial：条目型资讯/动态（报道、RSS、问答帖、仓库 issue 等）
# - academic：论文/著作记录
CONTENT_ROLE_LABEL_ZH: dict[str, str] = {
    "daily_editorial": "条目型内容（资讯/RSS/问答/动态）",
    "academic": "学术论文元数据",
    "runnable_apps": "可运行应用（Spaces 等演示入口）",
    "app_launches": "应用首发（Product Hunt）",
    "monetization_listing": "变现案例 / 商业资产",
}


# 独立开发者向内置 5 路（含 NewsAPI / TheNewsAPI 新闻聚合）
MAINSTREAM_ADMIN_SOURCE_PRESETS: list[dict] = [
    {
        "source": "github",
        "preset_label": "GitHub（客户端）",
        "enabled": True,
        "api_base": "https://github.com/trending?since=daily",
        "api_key_masked": "",
        "scope_label": "AI｜客户端·开源",
        "content_role": "daily_editorial",
        "notes": "Trending 日榜 → 仅保留 desktop/tauri/electron/flutter/chrome-extension/client/gui 等客户端向仓库。",
        "fetch_limit": PRESET_FETCH_LIMIT["github"],
    },
    {
        "source": "product_hunt",
        "preset_label": "Product Hunt",
        "enabled": True,
        "api_base": "https://api.producthunt.com/v2/api/graphql",
        "api_key_masked": "",
        "scope_label": "AI｜应用发现",
        "content_role": "app_launches",
        "notes": "Product Hunt GraphQL v2；PT 日榜按票数 Top N（默认 30，可在卡片配置）。",
        "fetch_limit": PRESET_FETCH_LIMIT["product_hunt"],
    },
    {
        "source": "hacker_news",
        "preset_label": "Hacker News",
        "enabled": True,
        "api_base": "https://hn.algolia.com/api/v1/search?tags=front_page",
        "api_key_masked": "",
        "scope_label": "AI｜社区资讯",
        "content_role": "daily_editorial",
        "notes": "Algolia HN front_page，按 points Top N。",
        "fetch_limit": PRESET_FETCH_LIMIT["hacker_news"],
    },
    {
        "source": "newsapi",
        "preset_label": "NewsAPI",
        "enabled": True,
        "api_base": "https://newsapi.org/v2/top-headlines?country=us&category=technology&pageSize=10",
        "api_key_masked": "",
        "scope_label": "AI｜新闻聚合",
        "content_role": "daily_editorial",
        "notes": "NewsAPI v2 top-headlines（US 科技最新 Top 10，无关键词过滤）。Query 参数 apiKey。",
        "fetch_limit": PRESET_FETCH_LIMIT["newsapi"],
    },
    {
        "source": "thenewsapi",
        "preset_label": "TheNewsAPI",
        "enabled": True,
        "api_base": "https://api.thenewsapi.com/v1/news/top?locale=us&language=en&categories=tech&limit=10",
        "api_key_masked": "",
        "scope_label": "AI｜新闻聚合",
        "content_role": "daily_editorial",
        "notes": "TheNewsAPI：上游单次约 3 条；建议在卡片开启「单独设置同步频率」（如每 2 小时），否则仅随整批每日拉一次。",
        "fetch_limit": PRESET_FETCH_LIMIT["thenewsapi"],
    },
]

# 可选变现向数据源：默认关闭，后台卡片手动启用；不参与定时整批拉取。
OPTIONAL_MONETIZATION_SOURCE_PRESETS: list[dict] = [
    {
        "source": "taaft",
        "preset_label": "TAAFT（新工具）",
        "enabled": False,
        "api_base": "https://theresanaiforthat.com/new/",
        "api_key_masked": "",
        "scope_label": "AI｜应用发现",
        "content_role": "app_launches",
        "notes": "There's An AI For That 新工具列表；无 Key，HTML 解析。启用后在管理后台手动同步或单独频率。",
        "fetch_limit": 15,
    },
    {
        "source": "acquire",
        "preset_label": "Acquire（AI 资产）",
        "enabled": False,
        "api_base": "https://us-central1-microacquire.cloudfunctions.net/v1-search",
        "api_key_masked": "",
        "scope_label": "AI｜变现案例",
        "content_role": "monetization_listing",
        "notes": "MicroAcquire v1-search，筛选 AI 相关出售/收购线索；无 Key。默认关闭。",
        "fetch_limit": 10,
    },
]

BUILTIN_ADMIN_SOURCE_PRESETS: list[dict] = MAINSTREAM_ADMIN_SOURCE_PRESETS + OPTIONAL_MONETIZATION_SOURCE_PRESETS

# 当前产品保留的内置数据源标识；启动时用于删库中「多余」行（含可选变现源）。
BUILTIN_ADMIN_SOURCE_KEYS: frozenset[str] = frozenset(row["source"] for row in BUILTIN_ADMIN_SOURCE_PRESETS)

# 参与默认定时拉取的 5 路（与 MAINSTREAM 一致）。
MAINSTREAM_ADMIN_SOURCE_KEYS: frozenset[str] = frozenset(row["source"] for row in MAINSTREAM_ADMIN_SOURCE_PRESETS)

OPTIONAL_MONETIZATION_SOURCE_KEYS: frozenset[str] = frozenset(
    row["source"] for row in OPTIONAL_MONETIZATION_SOURCE_PRESETS
)

# 历史上由 ensure_mainstream_admin_sources 写入、但已从产品移除的 source；启动时删库内对应行及同 admin_source_key 的连接器。
# 勿把仍保留在 MAINSTREAM_ADMIN_SOURCE_PRESETS 中的标识放进本集合，否则会误删运营已配置的 Key。
DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES: frozenset[str] = frozenset(
    {
        "mcp_skills",
        "openai",
        "google_gemini",
        "finnhub",
        "youtube_data",
        "mapbox",
        "stackoverflow",
        "openalex",
        "rss_arstechnica",
        "rss_theverge",
        "huggingface_spaces",
        "arxiv",
    }
)
assert not DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES.intersection(
    BUILTIN_ADMIN_SOURCE_KEYS
), "DISCONTINUED_BOOTSTRAP_ADMIN_SOURCES overlaps BUILTIN_ADMIN_SOURCE_PRESETS"

# 后台数据源卡片：下列预置 source 的公开模板可不填 Key 即可拉取；卡片上隐藏「API Key」输入。
# 其余预置（如 product_hunt）及运营自增的任意标识默认显示密钥框。
ADMIN_SOURCE_PRESETS_HIDE_CARD_API_KEY: frozenset[str] = frozenset(
    {
        "github",
        "hacker_news",
        "taaft",
        "acquire",
    }
)

# 凭据形态：当前内置 5 路；旧预置已进 DISCONTINUED 并由启动任务删库。
# 后台第二输入框「APP Secret」仅对 ADMIN_SOURCE_PRESETS_SHOW_APP_SECRET_FIELD 为真时展示（当前仅 product_hunt）。
# 后台卡片在「Bearer Access Token」之外另展示「OAuth Client Secret」输入的预置（Developer OAuth 换 token 用）。
ADMIN_SOURCE_PRESETS_SHOW_APP_SECRET_FIELD: frozenset[str] = frozenset({"product_hunt"})


def sync_catalog_preset_metadata(db: Session) -> int:
    """将内置目录中的 preset_label / content_role 写入主流 source，仅当对应列为空（便于运营日后自定义）。"""
    n = 0
    for row in BUILTIN_ADMIN_SOURCE_PRESETS:
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


def repair_mainstream_fetch_limits(db: Session) -> int:
    """将内置源的 fetch_limit 对齐预设默认（仅当未配置或仍为旧默认 10 且预设非 10）。"""
    n = 0
    for row in BUILTIN_ADMIN_SOURCE_PRESETS:
        src = row["source"]
        item = db.scalar(select(AdminSourceConfig).where(AdminSourceConfig.source == src))
        if not item:
            continue
        want = int(row.get("fetch_limit") or default_fetch_limit_for_source(src))
        cur = int(item.fetch_limit or 0)
        if cur <= 0 or (cur == 10 and want != 10):
            item.fetch_limit = want
            n += 1
    if n:
        db.commit()
    return n


def ensure_mainstream_admin_sources(db: Session) -> int:
    """补全内置数据源行（含默认关闭的变现可选源）；已存在的 source 不修改。"""
    n = 0
    for row in BUILTIN_ADMIN_SOURCE_PRESETS:
        source = row["source"]
        exists = db.scalar(select(AdminSourceConfig.id).where(AdminSourceConfig.source == source))
        if exists:
            continue
        sl = row.get("scope_label") or ""
        pl = (row.get("preset_label") or "").strip() or source.replace("_", " ").title()
        cr = str(row.get("content_role") or "daily_editorial").strip() or "daily_editorial"
        fl = normalize_fetch_limit(row.get("fetch_limit"), source=source)
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
                fetch_limit=fl,
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
            source="github",
            evidence_url="https://github.com/microsoft/vscode/issues",
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
    from .sync_diagnostic_log import clear_all as clear_sync_diagnostic_logs
    from .taxonomy_from_sources import clear_merged_domains_taxonomy

    n_diag = clear_sync_diagnostic_logs(db)
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
        "product_sync_diagnostic_logs": n_diag,
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
