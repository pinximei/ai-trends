import json
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditLog, AdminSession, AdminSourceConfig, EvidenceSignal, PipelineRun, RemovalRequest, Trend
from .scope_labels_util import dump_scope_labels_json


# 后台「数据源」预设：仅当库中尚无该 source 时插入，不覆盖运营已改过的行。
# scope_label：标明所属领域/板块，便于与「行业→板块」前台结构对应。
# frequency「daily_07:00」：每日一次，默认 07:00（具体执行依赖后续调度/运维时区约定）。
# api_base：优先选用 GET 即可探测连通性的路径；业务集成时可在表单中改回官方文档中的根路径。
MAINSTREAM_ADMIN_SOURCE_PRESETS: list[dict] = [
    {
        "source": "github",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.github.com/zen",
        "api_key_masked": "",
        "scope_label": "AI｜通用·开源协作",
        "notes": "【模板】GitHub REST；下方为连通性探测（/zen）。正式调用请用 api.github.com 文档中的路径；高配额建议填 PAT。",
    },
    {
        "source": "huggingface",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://huggingface.co/api/models?limit=1",
        "api_key_masked": "",
        "scope_label": "AI｜大模型/生态",
        "notes": "【模板】Hugging Face Hub；读私有或提配额请在下方填 HF_TOKEN。",
    },
    {
        "source": "huggingface_spaces",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://huggingface.co/api/spaces?limit=1",
        "api_key_masked": "",
        "scope_label": "AI｜Spaces·应用",
        "notes": "【模板】Hugging Face Spaces；线上推理请用各 Space 的 Gradio/专用 URL，或配 HF_TOKEN。",
    },
    {
        "source": "reddit",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://www.reddit.com/r/all/hot.json?limit=1",
        "api_key_masked": "",
        "scope_label": "通用·社区",
        "notes": "【模板】下方为公开 JSON 用于探测；OAuth 应用集成请改用 oauth.reddit.com 与开发者凭据（reddit.com/prefs/apps）。",
    },
    {
        "source": "hacker_news",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://hacker-news.firebaseio.com/v0/maxitem.json",
        "api_key_masked": "",
        "scope_label": "通用·技术资讯",
        "notes": "Hacker News 官方 Firebase JSON API，免 Key。",
    },
    {
        "source": "product_hunt",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.producthunt.com/v2/api/graphql",
        "api_key_masked": "",
        "scope_label": "产品·创投",
        "notes": "【模板】Product Hunt GraphQL v2；请先用 client_id/client_secret 换取 access_token，再把 access_token 作为 Bearer Token 填到下方测试与调用。",
    },
    {
        "source": "mcp_skills",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://registry.npmjs.org/react/latest",
        "api_key_masked": "",
        "scope_label": "AI｜Agent·MCP/Skills",
        "notes": "【模板】npm 包元数据用于探测；MCP 请将可访问的 HTTP/SSE Base 填在下方；stdio 类需自建网关。",
    },
    {
        "source": "gitlab",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://gitlab.com/api/v4/version",
        "api_key_masked": "",
        "scope_label": "AI｜通用·开源协作",
        "notes": "【模板】GitLab REST v4；自建实例请改为 https://你的域名/api/v4/... ；需鉴权时填 Token，认证选 GitLab PAT。",
    },
    {
        "source": "stackoverflow",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.stackexchange.com/2.3/info?site=stackoverflow",
        "api_key_masked": "",
        "scope_label": "开发·问答",
        "notes": "Stack Exchange API；公开配额可用，可选填 app key 提高限额。",
    },
    {
        "source": "arxiv",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://export.arxiv.org/api/query?search_query=all&start=0&max_results=1",
        "api_key_masked": "",
        "scope_label": "学术·论文",
        "notes": "arXiv 开放元数据与摘要，免 Key。",
    },
    {
        "source": "open_meteo",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41&current_weather=true",
        "api_key_masked": "",
        "scope_label": "气象·公开数据",
        "notes": "气象与空气质量等，免 Key、非商用友好。",
    },
    {
        "source": "coingecko",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.coingecko.com/api/v3/ping",
        "api_key_masked": "",
        "scope_label": "加密·行情",
        "notes": "加密资产行情；公开 tier 有速率限制，Pro 填 Key。",
    },
    {
        "source": "newsapi",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://newsapi.org/v2/top-headlines?country=us",
        "api_key_masked": "",
        "scope_label": "新闻·聚合",
        "notes": "新闻聚合；无 Key 时探测可能为 401，填 Key 后保存再测。",
    },
    {
        "source": "pypi",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://pypi.org/pypi/pip/json",
        "api_key_masked": "",
        "scope_label": "AI｜工具链·Python",
        "notes": "PyPI 包元数据 JSON API，免 Key。",
    },
    {
        "source": "npm",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://registry.npmjs.org/react/latest",
        "api_key_masked": "",
        "scope_label": "AI｜工具链·Node",
        "notes": "npm Registry 元数据，免 Key。",
    },
    # —— 以下为常用第三方：默认仅占位，密钥请在后台「数据源」表单中填写后保存。 —
    {
        "source": "openai",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.openai.com/v1/models",
        "api_key_masked": "",
        "scope_label": "AI｜大模型·OpenAI",
        "notes": "OpenAI HTTP API；无 Key 时列表接口多为 401；在 platform.openai.com 创建密钥后填入下方再测。",
    },
    {
        "source": "anthropic",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.anthropic.com/v1/messages",
        "api_key_masked": "",
        "scope_label": "AI｜大模型·Anthropic",
        "notes": "Anthropic Messages 为 POST；GET 探测常为 405（仍视为可达）；在 console.anthropic.com 获取 API Key。",
    },
    {
        "source": "google_gemini",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://generativelanguage.googleapis.com/v1beta/models",
        "api_key_masked": "",
        "scope_label": "AI｜大模型·Google",
        "notes": "Google AI Studio / Gemini；无 Key 时常为 403；填 Key 后保存再测。",
    },
    {
        "source": "openweather",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.openweathermap.org/data/2.5/weather?q=London",
        "api_key_masked": "",
        "scope_label": "气象·天气",
        "notes": "OpenWeatherMap；无 Key 多为 401；在 openweathermap.org 注册后填 API Key。",
    },
    {
        "source": "finnhub",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://finnhub.io/api/v1/quote?symbol=AAPL",
        "api_key_masked": "",
        "scope_label": "财经·股票",
        "notes": "Finnhub；无 Token 多为 401；finnhub.io 注册免费 Token 后填入再测。",
    },
    {
        "source": "alphavantage",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo",
        "api_key_masked": "",
        "scope_label": "财经·时间序列",
        "notes": "Alpha Vantage；模板使用官方 demo key 便于探测；生产请在 alphavantage.co 申请 Key。",
    },
    {
        "source": "youtube_data",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://www.googleapis.com/youtube/v3/videos?part=snippet&id=dQw4w9WgXcQ",
        "api_key_masked": "",
        "scope_label": "内容·视频",
        "notes": "YouTube Data API v3；无 Key 多为 403；Google Cloud 启用接口后填 API Key。",
    },
    {
        "source": "mapbox",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.mapbox.com",
        "api_key_masked": "",
        "scope_label": "地理·地图",
        "notes": "Mapbox；根路径可探测；地理编码等请在 URL 中带 access_token。",
    },
    {
        "source": "docker_hub",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://hub.docker.com/v2/repositories/library/ubuntu/",
        "api_key_masked": "",
        "scope_label": "AI｜工具链·容器",
        "notes": "Docker Hub 公开镜像元数据；高配额可填访问令牌。",
    },
    {
        "source": "crates_io",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://crates.io/api/v1/crates/serde",
        "api_key_masked": "",
        "scope_label": "AI｜工具链·Rust",
        "notes": "crates.io（Rust）包元数据；公开只读一般免 Key。",
    },
    {
        "source": "openalex",
        "enabled": True,
        "frequency": "daily_07:00",
        "api_base": "https://api.openalex.org/works?per_page=1",
        "api_key_masked": "",
        "scope_label": "学术·开放图谱",
        "notes": "OpenAlex 开放学术图谱；polite pool 建议填邮箱 polite 参数（可选）。",
    },
]

# 与 admin GET /api/admin/v1/sources/presets 展示名一致；供前端静态回退 JSON 与后端共用逻辑。
PRESET_SOURCE_LABELS: dict[str, str] = {
    "github": "GitHub",
    "gitlab": "GitLab",
    "huggingface": "Hugging Face",
    "huggingface_spaces": "Hugging Face Spaces",
    "reddit": "Reddit",
    "hacker_news": "Hacker News",
    "product_hunt": "Product Hunt",
    "stackoverflow": "Stack Overflow",
    "arxiv": "arXiv",
    "open_meteo": "Open-Meteo",
    "coingecko": "CoinGecko",
    "newsapi": "NewsAPI",
    "pypi": "PyPI",
    "npm": "npm",
    "mcp_skills": "MCP / Skills",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google_gemini": "Google Gemini",
    "openweather": "OpenWeather",
    "finnhub": "Finnhub",
    "alphavantage": "Alpha Vantage",
    "youtube_data": "YouTube Data",
    "mapbox": "Mapbox",
    "docker_hub": "Docker Hub",
    "crates_io": "crates.io",
    "openalex": "OpenAlex",
}


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
                "frequency": row["frequency"],
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
                frequency=row["frequency"],
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
