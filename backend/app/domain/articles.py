"""文章域：入库指纹、列表去重指纹、数据源泳道、价值分、游标与分类解析。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from ..product_models import Article

# —— 指纹 ——


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def ingest_fingerprint(snippet: str) -> str:
    raw = normalize_ws((snippet or "")[:12000])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def display_fingerprint(title: str, summary: str) -> str:
    def norm(x: str) -> str:
        x = (x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        return x[:600]

    blob = norm(title) + "||" + norm((summary or "")[:800])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


# —— 价值（规则，非 LLM）——

VALUE_SCORE_MIN = 38.0

# LLM 入库 categories：约十来条（不宜过少或过多）
PUBLISH_CATEGORY_COUNT_MIN = 8
PUBLISH_CATEGORY_COUNT_MAX = 12


def rule_value_score(*, snippet: str, summary: str, http_status: int) -> float:
    if http_status < 200 or http_status >= 300:
        return 0.0
    s = (snippet or "").strip()
    if len(s) < 80:
        return 0.0
    score = 32.0
    if len(s) >= 400:
        score += 28.0
    elif len(s) >= 200:
        score += 18.0
    summ = (summary or "").strip()
    if len(summ) >= 60:
        score += 12.0
    if len(summ) >= 140:
        score += 8.0
    low = s.lower()
    if "401" in s or "403" in s or "unauthorized" in low or "forbidden" in low:
        score -= 45.0
    if "rate limit" in low or "too many requests" in low:
        score -= 35.0
    if low.count("error") >= 3 and len(s) < 500:
        score -= 25.0
    return max(0.0, min(100.0, score))


def ingest_duplicate_exists(db: Session, *, industry_id: int, ingest_fp: str) -> bool:
    if not ingest_fp:
        return False
    q = select(Article.id).where(Article.industry_id == industry_id, Article.ingest_fingerprint == ingest_fp).limit(1)
    return db.scalar(q) is not None


# —— 泳道（与 admin_source_key 一致）——

# 资讯：模型/API、代码托管、论文与行情等（非「上架应用」发现类）
FEED_NEWS_KEYS = frozenset(
    {
        "hacker_news",
        "newsapi",
        "stackoverflow",
        "arxiv",
        "openalex",
        "youtube_data",
        "finnhub",
        "alphavantage",
        "coingecko",
        "open_meteo",
        "mapbox",
        "github",
        "huggingface",
        "mcp_skills",
        "docker_hub",
        "pypi",
        "npm",
        "crates_io",
        "openai",
        "google_gemini",
    }
)
# 应用：产品上架/可运行应用发现（与「Agent 发版、GitHub 仓库」类资讯区分）
FEED_APPS_KEYS = frozenset(
    {
        "product_hunt",
        "huggingface_spaces",
    }
)


def admin_source_key(third_party_source: str | None) -> str:
    if not third_party_source:
        return ""
    return str(third_party_source).strip().split(" / ", 1)[0].strip().lower()


def feed_lane(admin_key: str) -> str:
    k = (admin_key or "").strip().lower()
    if not k or k == "未绑定数据源":
        return "news"
    if k in FEED_APPS_KEYS:
        return "apps"
    if k in FEED_NEWS_KEYS:
        return "news"
    return "news"


# —— 游标与排除集 ——


def decode_feed_cursor(raw: str | None) -> tuple[datetime, int] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        s = str(raw).strip()
        pad = s + "=" * (-len(s) % 4)
        obj = json.loads(base64.urlsafe_b64decode(pad.encode("ascii")).decode("utf-8"))
        ts = str(obj["t"]).replace("Z", "")
        t = datetime.fromisoformat(ts)
        return (t, int(obj["id"]))
    except Exception:
        return None


def encode_feed_cursor(pub: datetime, aid: int) -> str:
    ts = pub.isoformat()
    if not ts.endswith("+00:00"):
        ts = ts + "Z"
    payload = {"t": ts, "id": aid}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def parse_segment_ids_csv(raw: str | None) -> list[int] | None:
    if not raw or not str(raw).strip():
        return None
    out: list[int] = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out or None


def parse_exclude_fingerprints(raw: str | None, max_n: int = 120) -> set[str]:
    if not raw or not str(raw).strip():
        return set()
    out: set[str] = set()
    for part in str(raw).split(","):
        p = part.strip().lower()
        if len(p) == 20 and all(c in "0123456789abcdef" for c in p):
            out.add(p)
        if len(out) >= max_n:
            break
    return out


def parse_category_labels_json(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()][:12]
    except Exception:
        pass
    return []


def parse_article_tabs_json(raw: str | None) -> list[dict[str, str]]:
    """解析 product_articles.ai_tabs_json → [{label, summary, body_md}, ...]。"""
    if not raw or not str(raw).strip():
        return []
    try:
        v = json.loads(raw)
        if not isinstance(v, list):
            return []
        out: list[dict[str, str]] = []
        for item in v[:8]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            summary = str(item.get("summary") or "").strip()
            body_md = str(item.get("body_md") or "").strip()
            if not label or not summary or not body_md:
                continue
            out.append({"label": label[:128], "summary": summary[:2000], "body_md": body_md[:50000]})
        return out
    except Exception:
        return []


def ui_shape_warnings_for_stored_article(
    *,
    ai_categories_json: str | None,
    ai_tabs_json: str | None,
    body: str | None,
    summary: str | None,
) -> list[str]:
    """
    检查已落库字段与公开站（列表 + 详情 tab + Markdown）的契合度；返回人类可读告警文案，空列表表示无问题。
    供管理端自检或 CI 调用；不抛异常。
    """
    warns: list[str] = []
    raw_tabs = (ai_tabs_json or "").strip()
    tabs = parse_article_tabs_json(ai_tabs_json)
    if raw_tabs and len(tabs) < 2:
        warns.append("ai_tabs_json 存在但解析后有效 tab 少于 2 个，详情页将回退为单栏「全文」或仅展示 body")
    cats = parse_category_labels_json(ai_categories_json)
    if len(cats) < PUBLISH_CATEGORY_COUNT_MIN:
        warns.append(
            f"ai_categories_json 中有效分类少于 {PUBLISH_CATEGORY_COUNT_MIN} 个，与入库规范（约十来条）不一致"
        )
    if len(cats) > PUBLISH_CATEGORY_COUNT_MAX:
        warns.append(
            f"ai_categories_json 中有效分类多于 {PUBLISH_CATEGORY_COUNT_MAX} 个，与入库规范（约十来条）不一致"
        )
    if not tabs and not (body or "").strip():
        warns.append("无 tabs 且无 body，详情 Markdown 区域将为空")
    if tabs and len((summary or "").strip()) < 4:
        warns.append("摘要过短可能影响列表卡片展示")
    return warns


def validate_llm_polish_for_publish(data: dict) -> bool:
    """连接器入库：必须含合格分类与分 tab 正文（全部由模型生成）。"""
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    if not title or not summary:
        return False
    cats = data.get("categories")
    if not isinstance(cats, list):
        return False
    clean_cats = [str(x).strip() for x in cats if str(x).strip()]
    if len(clean_cats) < PUBLISH_CATEGORY_COUNT_MIN or len(clean_cats) > PUBLISH_CATEGORY_COUNT_MAX:
        return False
    tabs = data.get("tabs")
    if not isinstance(tabs, list) or len(tabs) < 2 or len(tabs) > 6:
        return False
    for t in tabs:
        if not isinstance(t, dict):
            return False
        lab = str(t.get("label") or "").strip()
        summ = str(t.get("summary") or "").strip()
        body = str(t.get("body_md") or "").strip()
        if len(lab) < 2 or len(summ) < 8 or len(body) < 16:
            return False
    return True


def published_calendar_day(db: Session):
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", Article.published_at)
    return cast(Article.published_at, Date)
