"""文章域：入库指纹、列表去重指纹、数据源泳道、价值分、游标与分类解析。"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from datetime import datetime
from typing import Iterator
from urllib.parse import urlparse

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from ..product_models import Article

# 连接器单次 HTTP 正文保留上限（指纹、上游 id 解析等须在同一段「尽量完整」的 JSON 上完成）。
# 须覆盖 PyPI 单包元数据、crates.io、OpenAlex 等大块 JSON；过小会导致 json.loads 失败。
CONNECTOR_SNIPPET_MAX_CHARS = 524_288

# 送入大模型润色的片段上限（与上者分离，避免半兆 JSON 撑爆上下文与费用）。
CONNECTOR_LLM_SNIPPET_MAX_CHARS = 32_768

# 连接器「热度榜」条数：先拉榜单再逐条拉详情后入库（Product Hunt / Hugging Face Spaces 等）。
CONNECTOR_HEAT_TOP_N = 10

CONNECTOR_SYNC_ITEMS_V1_KEY = "connector_sync_items_v1"


def parse_connector_sync_item_snippets(snippet: str) -> list[str] | None:
    """若顶层为 ``connector_sync_items_v1`` 多段 pack，返回各段独立 JSON 字符串供逐条入库。"""
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if not s:
        return None
    try:
        root = json.loads(s)
    except Exception:
        return None
    if not isinstance(root, dict):
        return None
    raw_items = root.get(CONNECTOR_SYNC_ITEMS_V1_KEY)
    if not isinstance(raw_items, list) or not raw_items:
        return None
    out: list[str] = []
    for it in raw_items[:15]:
        if not isinstance(it, dict):
            continue
        chunk = it.get("snippet")
        if isinstance(chunk, str) and chunk.strip():
            out.append(chunk.strip()[:CONNECTOR_SNIPPET_MAX_CHARS])
    return out or None


# —— 指纹 ——


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def ingest_fingerprint(snippet: str) -> str:
    raw = normalize_ws((snippet or "")[:CONNECTOR_SNIPPET_MAX_CHARS])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def display_fingerprint(title: str, summary: str) -> str:
    def norm(x: str) -> str:
        x = (x or "").lower().strip()
        x = re.sub(r"\s+", " ", x)
        return x[:600]

    blob = norm(title) + "||" + norm((summary or "")[:800])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]


# —— 连接器片段 → 原始条目 URL（追溯用）——

# 人读「原文页」优先：避免根字段 ``url`` 常为 API 端点或 CDN，被误当作原文链接。
_URL_JSON_KEYS: tuple[str, ...] = (
    "html_url",
    "permalink",
    "story_url",
    "article_url",
    "web_url",
    "webUrl",
    "link",
    "canonical_url",
    "comments_url",
    "url",
    "href",
    "uri",
)


def _hostname(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_low_signal_original_url(url: str) -> bool:
    """非「原文入口」链接：对象存储/CDN/头像/API 等（解析辅助用，产品流程不再写入 source_original_url）。"""
    h = _hostname(url)
    if not h:
        return True
    if h == "api.github.com" or h.endswith(".githubusercontent.com"):
        return True
    markers = (
        "aliyuncs.com",
        "aliyuncs.cn",
        "myqcloud.com",
        "qcloud.com",
        "qiniucdn.com",
        "qiniudn.com",
        "clouddn.com",
        "cloudfront.net",
        "amazonaws.com",
        "googleusercontent.com",
        "twimg.com",
        "fbcdn.net",
        "azureedge.net",
        "cloudinary.com",
        "fastly.net",
        "fastly.com",
        "akamaized.net",
        "akamaihd.net",
        "imgix.net",
        "cdn.",
        ".cdn.",
    )
    return any(m in h for m in markers)


def _first_acceptable_http_url_in_text(s: str) -> str | None:
    for m in re.finditer(r"https?://[^\s\"'<>)\]]{4,2000}", s, re.I):
        u = m.group(0).rstrip(".,);]}")
        if not _is_low_signal_original_url(u):
            return u[:2048]
    return None


def _iter_urls_depth_first(obj: object, *, depth: int = 0) -> Iterator[str]:
    if depth > 8:
        return
    if isinstance(obj, str):
        t = obj.strip()
        if t.startswith(("http://", "https://")) and len(t) >= 12:
            yield t[:2048]
        return
    if isinstance(obj, dict):
        for k in _URL_JSON_KEYS:
            if k in obj:
                yield from _iter_urls_depth_first(obj[k], depth=depth + 1)
        for k, v in obj.items():
            if k in _URL_JSON_KEYS:
                continue
            yield from _iter_urls_depth_first(v, depth=depth + 1)
        return
    if isinstance(obj, list):
        for it in obj[:40]:
            yield from _iter_urls_depth_first(it, depth=depth + 1)


def _extract_url_from_json_obj(obj: object) -> str | None:
    for u in _iter_urls_depth_first(obj, depth=0):
        if not _is_low_signal_original_url(u):
            return u
    return None


COVER_IMAGE_SOURCE_KEYS = frozenset({"product_hunt", "huggingface_spaces"})
_COVER_URL_MAX = 2048


def _normalize_http_cover_url(url: str) -> str | None:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")) or len(u) < 12:
        return None
    return u[:_COVER_URL_MAX]


def _normalize_hf_space_thumbnail(raw: str, *, space_id: str) -> str | None:
    th = (raw or "").strip()
    if not th:
        return None
    if th.startswith(("http://", "https://")):
        return _normalize_http_cover_url(th)
    sid = (space_id or "").strip().strip("/")
    if not sid:
        return None
    path = th.lstrip("/")
    return _normalize_http_cover_url(f"https://huggingface.co/spaces/{sid}/resolve/main/{path}")


def extract_cover_image_url(admin_source_key: str, snippet: str) -> str | None:
    """
    从连接器片段解析列表/详情封面图 URL。
    - product_hunt: ``thumbnail.url``，否则 ``media`` 中首张 image
    - huggingface_spaces: ``cardData.thumbnail``（相对路径转 resolve/main）
    """
    k = (admin_source_key or "").strip().lower()
    if k not in COVER_IMAGE_SOURCE_KEYS:
        return None
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if not s:
        return None
    try:
        payload = json.loads(s)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    if k == "product_hunt":
        thumb = payload.get("thumbnail")
        if isinstance(thumb, dict):
            u = _normalize_http_cover_url(str(thumb.get("url") or ""))
            if u:
                return u
        media = payload.get("media")
        if isinstance(media, list):
            for item in media:
                if not isinstance(item, dict):
                    continue
                if str(item.get("type") or "").strip().lower() == "image":
                    u = _normalize_http_cover_url(str(item.get("url") or ""))
                    if u:
                        return u
        return None

    if k == "huggingface_spaces":
        card = payload.get("cardData")
        if isinstance(card, dict):
            return _normalize_hf_space_thumbnail(
                str(card.get("thumbnail") or ""),
                space_id=str(payload.get("id") or ""),
            )
    return None


def extract_source_original_url_from_connector_snippet(snippet: str) -> str | None:
    """
    从连接器片段中解析可点击 http(s) URL（单测与可选脚本用）。

    产品文章入库与公开 API 不再使用本字段；库表 ``source_original_url`` 可为历史数据保留。
    """
    s = (snippet or "").strip()
    if not s:
        return None
    head = s[:CONNECTOR_SNIPPET_MAX_CHARS]
    try:
        payload = json.loads(head)
    except Exception:
        return _first_acceptable_http_url_in_text(head)
    u = _extract_url_from_json_obj(payload)
    if u:
        return u[:2048]
    return _first_acceptable_http_url_in_text(head)


# —— 连接器片段 → 上游条目 ID（与改写稿 id 对应）——


def _normalize_upstream_id_value(val: object) -> str | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    if isinstance(val, str):
        s = val.strip()
        if 1 <= len(s) <= 512:
            return s
    return None


def _extract_external_id_from_dict(d: dict) -> str | None:
    """从单条业务对象上取常见主键字段（浅层）。"""
    for k in (
        "node_id",
        "objectID",
        "object_id",
        "objectId",
        "arxiv_id",
        "story_id",
        "uuid",
        "sha",
        "databaseId",
        "database_id",
    ):
        if k in d:
            sid = _normalize_upstream_id_value(d[k])
            if sid:
                return sid
    if "id" in d:
        sid = _normalize_upstream_id_value(d["id"])
        if sid:
            return sid
    if "slug" in d:
        s = str(d.get("slug") or "").strip()
        if 1 <= len(s) <= 200:
            return s
    return None


def extract_github_engagement_from_snippet(snippet: str) -> dict[str, int | None]:
    """从 GitHub 仓库 JSON 片段解析总 star 与今日 star 增速（Trending 同步写入）。"""
    out: dict[str, int | None] = {"stars_total": None, "stars_today": None}
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    try:
        obj = json.loads(s)
    except Exception:
        return out
    if not isinstance(obj, dict):
        return out
    try:
        total = int(obj.get("stargazers_count") or 0)
        if total >= 0:
            out["stars_total"] = total
    except (TypeError, ValueError):
        pass
    today_raw = obj.get("trending_stars_today")
    if today_raw is None:
        tr = obj.get("_aisoul_trending")
        if isinstance(tr, dict):
            today_raw = tr.get("stars_today")
    try:
        if today_raw is not None:
            today = int(today_raw)
            if today >= 0:
                out["stars_today"] = today
    except (TypeError, ValueError):
        pass
    return out


def _github_repo_page_url_from_payload(payload: dict) -> str | None:
    """GitHub 仓库页（非 issues/releases 子路径）。"""
    fn = str(payload.get("full_name") or "").strip().strip("/")
    if fn and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", fn):
        return f"https://github.com/{fn}"[:2048]
    html = str(payload.get("html_url") or "").strip()
    if html.startswith(("http://", "https://")) and "github.com/" in html.lower():
        m = re.match(r"^(https?://github\.com/[^/]+/[^/]+)", html, re.I)
        if m:
            return m.group(1)[:2048]
    return None


def extract_connector_detail_link_rows(admin_source_key: str, snippet: str) -> list[tuple[str, str]]:
    """从连接器片段提取详情「数据支撑」应展示的 (标签, URL) 列表。"""
    k = (admin_source_key or "").strip().lower()
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if not s:
        return []
    try:
        payload = json.loads(s)
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []

    rows: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, url: str) -> None:
        u = (url or "").strip()
        if not u.startswith(("http://", "https://")) or len(u) < 12:
            return
        u = u[:2048]
        if u in seen:
            return
        seen.add(u)
        rows.append((label, u))

    if k == "github":
        repo = _github_repo_page_url_from_payload(payload)
        if repo:
            add("GitHub 仓库", repo)
        hp = str(payload.get("homepage") or "").strip()
        if hp.startswith(("http://", "https://")):
            add("项目主页", hp)
        return rows

    if k == "hacker_news":
        link = (payload.get("url") or "").strip()
        if not link and payload.get("objectID"):
            link = f"https://news.ycombinator.com/item?id={payload.get('objectID')}"
        if link:
            add("讨论链接", link)
        return rows

    if k == "arxiv":
        abs_u = str(payload.get("abs_url") or "").strip()
        if not abs_u and payload.get("arxiv_id"):
            abs_u = f"https://arxiv.org/abs/{str(payload.get('arxiv_id')).strip()}"
        pdf_u = str(payload.get("pdf_url") or "").strip()
        if abs_u:
            add("arXiv 摘要页", abs_u)
        if pdf_u:
            add("PDF", pdf_u)
        return rows

    if k == "product_hunt":
        for label, key in (("官网", "website"), ("Product Hunt", "url")):
            u = str(payload.get(key) or "").strip()
            if u.startswith(("http://", "https://")):
                add(label, u)
        return rows

    if k == "huggingface_spaces":
        sid = str(payload.get("id") or "").strip().strip("/")
        if sid:
            add("Space", f"https://huggingface.co/spaces/{sid}")
        return rows

    u = extract_source_original_url_from_connector_snippet(s)
    if u:
        add("原文链接", u)
    return rows


def extract_connector_primary_url(admin_source_key: str, snippet: str) -> str | None:
    """连接器条目主链接（写入 source_original_url、详情页顶栏）。"""
    rows = extract_connector_detail_link_rows(admin_source_key, snippet)
    return rows[0][1] if rows else None


def _markdown_links_block(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    lines = ["", "**相关链接**", ""]
    for label, url in rows:
        lines.append(f"- [{label}]({url})")
    return "\n".join(lines)


def ensure_connector_links_in_polish_tabs(
    admin_source_key: str,
    snippet: str,
    tabs: list,
) -> None:
    """保证「数据支撑」tab 含可点击 Markdown 链接（不依赖 LLM 是否写出）。"""
    rows = extract_connector_detail_link_rows(admin_source_key, snippet)
    if not rows:
        return
    data_tab: dict | None = None
    for t in tabs:
        if isinstance(t, dict) and str(t.get("label") or "").strip() == FEED_CARD_TAB_DATA:
            data_tab = t
            break
    if not data_tab:
        return
    body = str(data_tab.get("body_md") or "").strip()
    missing = [(lab, u) for lab, u in rows if u not in body]
    if not missing:
        return
    block = _markdown_links_block(missing)
    data_tab["body_md"] = (body + block).strip() if body else block.strip()


def enrich_published_tabs_with_source_url(
    tabs: list[dict[str, str]],
    *,
    source_original_url: str | None,
    admin_source_key: str,
) -> list[dict[str, str]]:
    """已发布文章读详情时：若 tab 内缺链接但库里有 source_original_url，补一段链接块。"""
    url = (source_original_url or "").strip()
    if not url.startswith(("http://", "https://")):
        return tabs
    ak = (admin_source_key or "").strip().lower()
    label = "GitHub 仓库" if ak == "github" else "原文链接"
    out: list[dict[str, str]] = []
    for t in tabs:
        row = dict(t)
        if str(row.get("label") or "").strip() == FEED_CARD_TAB_DATA:
            body = str(row.get("body_md") or "").strip()
            if url not in body:
                block = _markdown_links_block([(label, url)])
                row["body_md"] = (body + block).strip() if body else block.strip()
        out.append(row)
    return out


def extract_source_external_id_from_connector_snippet(snippet: str) -> str | None:
    """
    从连接器 JSON 中解析上游「原始条目」的稳定标识（如 HN Algolia 的 objectID、GitHub 的 node_id 或数字 id）。

    与 ``Article.id``（改写后入库主键）并列存储，便于后台/运营把改写稿与原始接口对象对应起来。
    """
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    try:
        payload = json.loads(s)
    except Exception:
        return None
    if isinstance(payload, list):
        for it in payload[:8]:
            if isinstance(it, dict):
                sid = _extract_external_id_from_dict(it)
                if sid:
                    return sid
        return None
    if isinstance(payload, dict):
        hits = payload.get("hits")
        if isinstance(hits, list) and hits:
            h0 = hits[0]
            if isinstance(h0, dict):
                sid = _extract_external_id_from_dict(h0)
                if sid:
                    return sid
        items = payload.get("items")
        if isinstance(items, list) and items:
            i0 = items[0]
            if isinstance(i0, dict):
                sid = _extract_external_id_from_dict(i0)
                if sid:
                    return sid
        data = payload.get("data")
        if isinstance(data, dict):
            sid = _extract_external_id_from_dict(data)
            if sid:
                return sid
        return _extract_external_id_from_dict(payload)
    return None


# —— 价值（规则，非 LLM）——

VALUE_SCORE_MIN = 38.0

# 前台筛选与入库：固定 10 个大类 + 「其他」，每篇文章只展示/归入其中一类（合并细标签）
FACET_PRIMARY_CATEGORIES: tuple[str, ...] = (
    "大模型",
    "开源工具",
    "应用产品",
    "数据算力",
    "安全合规",
    "政策市场",
    "论文研究",
    "平台API",
    "Agent",
    "多模态",
)
FACET_CATEGORY_OTHER = "其他"
FACET_ALL_LABELS: frozenset[str] = frozenset((*FACET_PRIMARY_CATEGORIES, FACET_CATEGORY_OTHER))
FACET_DISPLAY_ORDER: tuple[str, ...] = (*FACET_PRIMARY_CATEGORIES, FACET_CATEGORY_OTHER)

# (canonical, keyword_substrings) — 按顺序匹配，专用规则在前
_CATEGORY_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Agent", ("agent", "智能体", "工作流", "自动化")),
    ("平台API", ("api", "sdk", "开发者", "云平台", "接口")),
    ("论文研究", ("论文", "研究", "学术", "arxiv")),
    ("政策市场", ("政策", "监管", "市场", "融资", "并购")),
    ("安全合规", ("安全", "对齐", "合规", "隐私", "风险")),
    ("数据算力", ("数据", "算力", "芯片", "训练", "gpu", "集群")),
    ("应用产品", ("应用", "产品", "发布", "上架", "product")),
    ("开源工具", ("开源", "工具", "生态", "仓库")),
    ("多模态", ("多模态", "图像", "语音", "视频", "生成")),
    ("大模型", ("大模型", "推理", "模型", "llm", "基座")),
)


def map_raw_label_to_canonical(raw: str) -> str:
    """将模型或历史库中的任意短标签映射到 10+其他 之一。"""
    s = normalize_ws(raw)
    if not s:
        return FACET_CATEGORY_OTHER
    if s in FACET_ALL_LABELS:
        return s
    low = s.lower()
    for canon, keys in _CATEGORY_KEYWORD_RULES:
        for k in keys:
            if k.lower() in low or k in s:
                return canon
    return FACET_CATEGORY_OTHER


def primary_canonical_from_raw_labels(labels: list[str]) -> str:
    """多条旧分类合并为一条主类：优先首个非「其他」的映射。"""
    if not labels:
        return FACET_CATEGORY_OTHER
    mapped = [map_raw_label_to_canonical(x) for x in labels]
    for m in mapped:
        if m != FACET_CATEGORY_OTHER:
            return m
    return FACET_CATEGORY_OTHER


def display_categories_for_article(ai_categories_json: str | None) -> list[str]:
    """公开列表/详情展示用：始终返回恰好一个规范大类。"""
    raw = parse_category_labels_json(ai_categories_json)
    return [primary_canonical_from_raw_labels(raw)]


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


# —— 跨平台统一热度（单一 heat_score 量纲：对数归一 + 按数据源权重，便于横向比较与后续叠加因子）——


def _heat_log_norm(x: float, *, cap: float) -> float:
    """将非负计数压到 [0,1]，大平台间量级差用 log1p 拉齐。"""
    if cap <= 0 or x <= 0 or not math.isfinite(x):
        return 0.0
    return min(1.0, math.log1p(float(x)) / math.log1p(float(cap)))


_ENGAGEMENT_BUCKETS = frozenset(
    {
        "stars",
        "forks",
        "issues",
        "votes",
        "comments",
        "likes",
        "trending",
        "hn_points",
        "reddit_score",
        "downloads",
        "views",
    }
)


def _heat_accum_numeric(out: dict[str, float], bucket: str, v: object) -> None:
    if bucket not in out or isinstance(v, bool) or v is None:
        return
    if isinstance(v, int):
        if v < 0 or v > 2**53:
            return
        x = float(v)
    elif isinstance(v, float):
        if not math.isfinite(v) or v < 0:
            return
        x = v
    else:
        return
    out[bucket] = max(out[bucket], x)


def _heat_map_key_to_bucket(key: str) -> str | None:
    nk = str(key or "").strip().lower()
    if nk in ("stargazers_count", "stars", "star_count", "watchers_count", "watchers"):
        return "stars"
    if nk in ("forks", "forks_count", "fork_count"):
        return "forks"
    if nk in ("open_issues_count", "open_issues"):
        return "issues"
    if nk in ("votescount", "vote_count", "votes", "upvotes", "ups"):
        return "votes"
    if nk in ("commentscount", "comments_count", "num_comments", "comment_count", "numcomments", "children"):
        return "comments"
    if nk in ("likes", "like_count", "likescount"):
        return "likes"
    if nk in ("trendingscore", "trending_score", "trending_stars_today", "stars_today", "stars_gained_today"):
        return "trending"
    if nk == "points":
        return "hn_points"
    if nk in ("score", "reddit_score"):
        return "reddit_score"
    if nk in ("download_count", "downloads", "downloadcount"):
        return "downloads"
    if nk in ("view_count", "viewcount", "views", "playback_count", "play_count"):
        return "views"
    return None


def _walk_engagement_for_signals(obj: object, out: dict[str, float], depth: int) -> None:
    if depth > 14:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            b = _heat_map_key_to_bucket(k)
            if b:
                _heat_accum_numeric(out, b, v)
            if isinstance(v, (dict, list)):
                _walk_engagement_for_signals(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:80]:
            _walk_engagement_for_signals(item, out, depth + 1)


def extract_engagement_signals(snippet: str) -> dict[str, float]:
    """从连接器 JSON 片段中尽力抽取各平台「可比的」互动计数（越大越热）。"""
    out = {b: 0.0 for b in _ENGAGEMENT_BUCKETS}
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if len(s) < 2:
        return out
    try:
        root = json.loads(s)
    except Exception:
        return out
    _walk_engagement_for_signals(root, out, 0)
    return out


def _recency_boost_from_snippet(snippet: str, *, admin_source_key: str) -> float:
    """从片段中的 ISO 时间字段估计「多新」，弥补 arXiv 等无互动计数源（0–90 分）。"""
    k = (admin_source_key or "").strip().lower()
    if k not in ("arxiv", "newsapi", "finnhub", "youtube_data", "mapbox"):
        return 0.0
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    try:
        root = json.loads(s)
    except Exception:
        return 0.0
    if not isinstance(root, dict):
        return 0.0
    raw_ts = (root.get("updated") or root.get("published") or root.get("created_at") or "").strip()
    if not raw_ts:
        return 0.0
    try:
        ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    age_h = max(0.0, (datetime.utcnow() - ts).total_seconds() / 3600.0)
    if age_h <= 24:
        return 90.0
    if age_h <= 72:
        return 65.0
    if age_h <= 168:
        return 40.0
    if age_h <= 720:
        return 18.0
    return 0.0


def _connector_rank_boost(*, rank: int, pool_size: int) -> float:
    """连接器当次 TopN 内的榜内名次（#1 最高），与上游 API 排序一致。"""
    n = max(1, int(pool_size or CONNECTOR_HEAT_TOP_N))
    r = max(0, min(int(rank), n - 1))
    return 160.0 * float(n - r) / float(n)


def unified_connector_heat(
    *,
    admin_source_key: str,
    snippet: str,
    value_score: float,
    sync_unix: float,
    connector_rank: int = 0,
    connector_pool_size: int = CONNECTOR_HEAT_TOP_N,
) -> float:
    """
    连接器入库用的统一热度（heat_score），量纲约 0–900+，便于跨源排序：

    1. **平台互动**（主）：各源 votes/stars/points/likes 等 log 归一后加权（见分支权重）。
    2. **榜内名次**：当次同步 TopN 内排名（#1 高于 #10），与 Product Hunt/HN/GitHub 拉取顺序一致。
    3. **时效**：论文/快讯类用片段内 published/updated 时间加分。
    4. **信息完整度**：rule_value_score（片段长度等）仅作弱信号，避免「长 JSON 压过真热门」。
    5. **微小时序**：同分略新者优先（极小 tie）。

    运营可在后台 PATCH heat_score 覆盖。
    """
    sig = extract_engagement_signals(snippet)
    k = (admin_source_key or "").strip().lower()
    vs = max(0.0, min(100.0, float(value_score or 0.0)))
    rank_boost = _connector_rank_boost(rank=connector_rank, pool_size=connector_pool_size)
    recency = _recency_boost_from_snippet(snippet, admin_source_key=k)
    if k == "github":
        eng = (
            420.0 * _heat_log_norm(sig["stars"], cap=80_000.0)
            + 280.0 * _heat_log_norm(sig["trending"], cap=50_000.0)
            + 240.0 * _heat_log_norm(sig["forks"], cap=12_000.0)
            + 120.0 * _heat_log_norm(sig["issues"], cap=8_000.0)
            + 100.0 * _heat_log_norm(sig["comments"], cap=6_000.0)
        )
    elif k == "product_hunt":
        eng = (
            520.0 * _heat_log_norm(sig["votes"], cap=10_000.0)
            + 300.0 * _heat_log_norm(sig["comments"], cap=5_000.0)
        )
    elif k == "huggingface_spaces":
        eng = (
            460.0 * _heat_log_norm(sig["likes"], cap=80_000.0)
            + 280.0 * _heat_log_norm(sig["trending"], cap=2_000_000.0)
            + 90.0 * _heat_log_norm(sig["downloads"], cap=5_000_000.0)
            + 70.0 * _heat_log_norm(sig["views"], cap=50_000_000.0)
        )
    elif k == "hacker_news":
        eng = (
            500.0 * _heat_log_norm(sig["hn_points"], cap=12_000.0)
            + 320.0 * _heat_log_norm(sig["comments"], cap=6_000.0)
        )
    elif k == "arxiv":
        eng = 380.0 * _heat_log_norm(sig["views"], cap=500_000.0)
    else:
        eng = 540.0 * max(
            _heat_log_norm(sig["stars"], cap=120_000.0),
            _heat_log_norm(sig["votes"], cap=12_000.0),
            _heat_log_norm(sig["likes"], cap=100_000.0),
            _heat_log_norm(sig["hn_points"], cap=12_000.0),
            _heat_log_norm(sig["reddit_score"], cap=80_000.0),
            _heat_log_norm(sig["trending"], cap=2_000_000.0),
            _heat_log_norm(sig["views"], cap=80_000_000.0),
            _heat_log_norm(sig["downloads"], cap=8_000_000.0),
        )
    tie = (float(sync_unix) % 86_400_000.0) * 1e-7
    return float(max(0.0, eng + rank_boost + recency + 0.12 * vs + tie))


def unified_editorial_heat(*, sync_unix: float, quality_hint: float = 58.0) -> float:
    """无连接器片段时（后台手建稿）：落在统一量纲的中低段，避免与自然高互动稿件倒挂。"""
    qh = max(0.0, min(100.0, float(quality_hint)))
    tie = (float(sync_unix) % 86_400_000.0) * 1e-7
    return float(95.0 + 0.22 * qh + tie)


def ingest_duplicate_exists(db: Session, *, industry_id: int, ingest_fp: str) -> bool:
    if not ingest_fp:
        return False
    q = select(Article.id).where(Article.industry_id == industry_id, Article.ingest_fingerprint == ingest_fp).limit(1)
    return db.scalar(q) is not None


def ingest_duplicate_by_source_external_id_exists(
    db: Session, *, industry_id: int, source_external_id: str | None
) -> bool:
    """同一行业下已存在相同上游条目 id 的已存文章时跳过入库（防接口微差导致整段 JSON 指纹不同）。"""
    sid = (source_external_id or "").strip()
    if not sid:
        return False
    sid = sid[:512]
    q = select(Article.id).where(
        Article.industry_id == industry_id,
        Article.source_external_id == sid,
    ).limit(1)
    return db.scalar(q) is not None


# —— 泳道（与 admin_source_key 一致）——

# 资讯：模型/API、代码托管、论文等（非「上架应用」发现类）；键与仍支持或历史 admin_source 对齐。
FEED_NEWS_KEYS = frozenset(
    {
        "newsapi",
        "youtube_data",
        "finnhub",
        "mapbox",
        "github",
        "hacker_news",
        "arxiv",
        "mcp_skills",
        "openai",
        "google_gemini",
    }
)
# 应用：来自下列数据源的条目经 ``feed_lane_for_article`` 二次判别后进 apps；
# Agent / 大模型主类与正文中的模型/Agent 信号仍一律视为 news。
FEED_APPS_KEYS = frozenset(
    {
        "product_hunt",
        "huggingface_spaces",
    }
)

# 规范大类：在此集合中的一律不进「应用」泳道（仅对 FEED_APPS_KEYS 源二次筛选）
_FEED_PRIMARY_FORCE_NEWS: frozenset[str] = frozenset(
    {
        "Agent",
        "大模型",
        "论文研究",
        "平台API",
        "开源工具",
        "数据算力",
        "安全合规",
        "政策市场",
        "多模态",
    }
)


def _feed_lane_text_blob(
    *,
    title: str,
    summary: str,
    ai_tabs_json: str | None,
    max_chars: int = 12000,
) -> str:
    parts: list[str] = [title or "", summary or ""]
    for t in parse_article_tabs_json(ai_tabs_json)[:5]:
        parts.append(str(t.get("summary") or ""))
        parts.append(str(t.get("body_md") or "")[:1600])
    return normalize_ws("\n".join(parts))[:max_chars]


def _blob_suggests_agent_or_model_news(blob: str) -> bool:
    """Agent、模型、学术/API 工具链等倾向 → 不进应用泳道。"""
    if not blob.strip():
        return False
    low = normalize_ws(blob).lower()
    zh = blob
    if re.search(r"\bagents?\b", low):
        return True
    if re.search(r"\b(llm|mcp|langchain|langgraph|rag)\b", low):
        return True
    if re.search(r"\b(model weights|foundation model|open-weights)\b", low):
        return True
    for s in (
        "智能体",
        "多智能体",
        "大模型",
        "语言模型",
        "基座模型",
        "推理模型",
        "开源模型",
        "模型发布",
        "微调",
        "论文",
        "arxiv",
    ):
        if s.lower() in low or s in zh:
            return True
    if re.search(r"gpt-[34]\b", low) or "gpt-4o" in low:
        return True
    if "fine-tun" in low:
        return True
    return False


def admin_source_key(third_party_source: str | None) -> str:
    if not third_party_source:
        return ""
    return str(third_party_source).strip().split(" / ", 1)[0].strip().lower()


def feed_lane(admin_key: str) -> str:
    """按数据源默认泳道（连接器入口）；公开列表请以 ``feed_lane_for_article`` 为准。"""
    k = (admin_key or "").strip().lower()
    if not k or k == "未绑定数据源":
        return "news"
    if k in FEED_APPS_KEYS:
        return "apps"
    if k in FEED_NEWS_KEYS:
        return "news"
    return "news"


def feed_lane_for_article(
    admin_key: str,
    *,
    title: str = "",
    summary: str = "",
    ai_categories_json: str | None = None,
    ai_tabs_json: str | None = None,
) -> str:
    """公开站泳道：``FEED_APPS_KEYS``（Product Hunt、Hugging Face Spaces）在排除主类强制 news 与正文 Agent/模型信号后
    默认进 apps；其余数据源与 ``feed_lane`` 一致。
    """
    k = (admin_key or "").strip().lower()
    if not k or k == "未绑定数据源":
        return "news"
    if k not in FEED_APPS_KEYS:
        return feed_lane(k)

    primary = primary_canonical_from_raw_labels(parse_category_labels_json(ai_categories_json))
    if primary in _FEED_PRIMARY_FORCE_NEWS:
        return "news"

    blob = _feed_lane_text_blob(title=title, summary=summary, ai_tabs_json=ai_tabs_json)
    if _blob_suggests_agent_or_model_news(blob):
        return "news"
    return "apps"


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
            return [str(x).strip() for x in v if str(x).strip()][:40]
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
    if not cats:
        warns.append("ai_categories_json 无有效分类，前台将显示为「其他」")
    elif len(cats) > 1:
        warns.append(
            "ai_categories_json 含多条标签；公开站已合并为单一大类展示，建议新稿仅保留规范列表中一条"
        )
    if not tabs and not (body or "").strip():
        warns.append("无 tabs 且无 body，详情 Markdown 区域将为空")
    if tabs and len((summary or "").strip()) < 4:
        warns.append("摘要过短可能影响列表卡片展示")
    return warns


# —— 公开详情页版式（与 admin_source_key 对应，前台按 profile 分栏渲染）——

DETAIL_PROFILE_PRODUCT_LAUNCH = "product_launch"
DETAIL_PROFILE_AI_SPACE = "ai_space"
DETAIL_PROFILE_OPEN_SOURCE = "open_source"
DETAIL_PROFILE_NEWS_WIRE = "news_wire"
DETAIL_PROFILE_PLATFORM_API = "platform_api"
DETAIL_PROFILE_NEWS_ARTICLE = "news_article"
DETAIL_PROFILE_APP_PRODUCT = "app_product"

_DETAIL_PROFILE_BY_SOURCE: dict[str, str] = {
    "product_hunt": DETAIL_PROFILE_PRODUCT_LAUNCH,
    "huggingface_spaces": DETAIL_PROFILE_AI_SPACE,
    "github": DETAIL_PROFILE_OPEN_SOURCE,
    "newsapi": DETAIL_PROFILE_NEWS_WIRE,
    "finnhub": DETAIL_PROFILE_NEWS_WIRE,
    "youtube_data": DETAIL_PROFILE_NEWS_WIRE,
    "mapbox": DETAIL_PROFILE_NEWS_WIRE,
    "openai": DETAIL_PROFILE_PLATFORM_API,
    "google_gemini": DETAIL_PROFILE_PLATFORM_API,
    "mcp_skills": DETAIL_PROFILE_PLATFORM_API,
    "hacker_news": DETAIL_PROFILE_NEWS_WIRE,
    "arxiv": DETAIL_PROFILE_NEWS_ARTICLE,
}


def article_detail_profile(admin_source_key: str, feed_kind: str) -> str:
    """返回详情页结构 profile id（前端与 LLM 提示共用）。"""
    k = (admin_source_key or "").strip().lower()
    if k in _DETAIL_PROFILE_BY_SOURCE:
        return _DETAIL_PROFILE_BY_SOURCE[k]
    fk = (feed_kind or "news").strip().lower()
    return DETAIL_PROFILE_APP_PRODUCT if fk == "apps" else DETAIL_PROFILE_NEWS_ARTICLE


FEED_CARD_TAB_DESCRIPTION = "描述"
FEED_CARD_TAB_DATA = "数据支撑"
# 旧稿 tab 名，列表卡片与详情仍可读
FEED_CARD_TAB_LEGACY_HIGHLIGHTS = frozenset({"功能亮点", "要点"})


def required_feed_card_tab_labels(feed_kind: str) -> tuple[str, str]:
    del feed_kind  # 应用/资讯统一：描述 + 数据支撑
    return (FEED_CARD_TAB_DESCRIPTION, FEED_CARD_TAB_DATA)


def feed_card_highlights_tab_label(raw_label: str) -> bool:
    """是否对应列表卡片「亮点/要点」槽位（含旧 label）。"""
    lab = (raw_label or "").strip()
    return lab == FEED_CARD_TAB_DATA or lab in FEED_CARD_TAB_LEGACY_HIGHLIGHTS


def validate_llm_polish_for_publish(data: dict) -> bool:
    """连接器入库：必须含合格分类、可读摘要与足够厚的总览/分 tab 正文。"""
    title = str(data.get("title") or "").strip()
    summary = str(data.get("summary") or "").strip()
    body_md = str(data.get("body_md") or "").strip()
    if not title or not summary:
        return False
    if len(summary) < 36:
        return False
    if "同步资源" in title and "·" in title:
        return False
    cats = data.get("categories")
    if not isinstance(cats, list):
        return False
    clean_cats = [str(x).strip() for x in cats if str(x).strip()]
    if len(clean_cats) != 1:
        return False
    if clean_cats[0] not in FACET_ALL_LABELS:
        return False
    fk = str(data.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    need_desc, need_hi = required_feed_card_tab_labels(fk)
    tabs = data.get("tabs")
    if not isinstance(tabs, list) or len(tabs) != 2:
        return False
    tab_body_total = 0
    labels: list[str] = []
    for t in tabs:
        if not isinstance(t, dict):
            return False
        lab = str(t.get("label") or "").strip()
        summ = str(t.get("summary") or "").strip()
        body = str(t.get("body_md") or "").strip()
        labels.append(lab)
        min_summ = 72 if lab == need_desc else 12
        min_body = 120 if lab == need_desc else 60
        if len(lab) < 2 or len(summ) < min_summ or len(body) < min_body:
            return False
        tab_body_total += len(body)
    if labels != [need_desc, need_hi]:
        legacy_ok = labels == [need_desc, "功能亮点"] if fk == "apps" else labels == [need_desc, "要点"]
        if not legacy_ok:
            return False
    if tab_body_total < 280:
        return False
    if len(body_md) < 120 and tab_body_total < 500:
        return False
    return True


def published_calendar_day(db: Session):
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", Article.published_at)
    return cast(Article.published_at, Date)
