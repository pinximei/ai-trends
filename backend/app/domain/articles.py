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
    }
)
FEED_APPS_KEYS = frozenset(
    {
        "product_hunt",
        "huggingface",
        "huggingface_spaces",
        "mcp_skills",
        "docker_hub",
        "github",
        "pypi",
        "npm",
        "crates_io",
        "openai",
        "google_gemini",
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


def published_calendar_day(db: Session):
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", Article.published_at)
    return cast(Article.published_at, Date)
