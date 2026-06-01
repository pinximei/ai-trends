"""文章域：入库指纹、列表去重指纹、数据源泳道、价值分、游标与分类解析。"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

from sqlalchemy import Date, and_, case, cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from ..product_models import Article

# 连接器单次 HTTP 正文保留上限（指纹、上游 id 解析等须在同一段「尽量完整」的 JSON 上完成）。
# 须覆盖 PyPI 单包元数据、crates.io、OpenAlex 等大块 JSON；过小会导致 json.loads 失败。
CONNECTOR_SNIPPET_MAX_CHARS = 524_288

# 送入大模型润色的片段上限（经 llm_snippet_compact 压缩后仍受此限制）。
# 2026-05-29 曾降至 10240 省 token，导致 GitHub README/长稿润色不足；恢复 32768。
CONNECTOR_LLM_SNIPPET_MAX_CHARS = 32_768

# 连接器「热度榜」条数：先拉榜单再逐条拉详情后入库（Product Hunt / Hugging Face Spaces 等）。
CONNECTOR_HEAT_TOP_N = 10

CONNECTOR_SYNC_ITEMS_V1_KEY = "connector_sync_items_v1"

_PUBLISH_TIME_KEYS = ("publishedAt", "published_at", "created_at", "updated_at", "pubDate")


def _parse_iso_to_naive_utc(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.utcfromtimestamp(ts)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _published_at_from_item_dict(data: dict) -> datetime | None:
    for key in _PUBLISH_TIME_KEYS:
        if key in data:
            parsed = _parse_iso_to_naive_utc(data.get(key))
            if parsed is not None:
                return parsed
    return None


def connector_snippet_published_at_utc(snippet: str) -> datetime | None:
    """从连接器单条 JSON 片段解析源站发布时间；失败则返回 None（入库用同步时刻）。"""
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if not s:
        return None
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    found = _published_at_from_item_dict(data)
    if found is not None:
        return found
    items = data.get(CONNECTOR_SYNC_ITEMS_V1_KEY)
    if isinstance(items, list):
        for row in items:
            if not isinstance(row, dict):
                continue
            inner_s = (row.get("snippet") or "").strip()
            if not inner_s:
                continue
            try:
                inner = json.loads(inner_s)
            except json.JSONDecodeError:
                continue
            if isinstance(inner, dict):
                found = _published_at_from_item_dict(inner)
                if found is not None:
                    return found
    return None


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


COVER_IMAGE_SOURCE_KEYS = frozenset({"product_hunt", "huggingface_spaces", "newsapi", "thenewsapi"})
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

    if k == "newsapi":
        u = _normalize_http_cover_url(str(payload.get("urlToImage") or ""))
        return u

    if k == "thenewsapi":
        u = _normalize_http_cover_url(str(payload.get("image_url") or ""))
        return u

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

    if k == "taaft":
        u = str(payload.get("url") or payload.get("listing_url") or "").strip()
        if u.startswith(("http://", "https://")):
            add("TAAFT", u)
        return rows

    if k == "acquire":
        u = str(payload.get("url") or "").strip()
        if u.startswith(("http://", "https://")):
            add("Acquire 列表", u)
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
# 公开应用泳道额外纳入：变现向主类（原先进资讯泳道）及对应数据源
MONETIZATION_APPS_CATEGORIES: frozenset[str] = frozenset({"已验证变现", "变现案例"})
MONETIZATION_SOURCE_KEYS: frozenset[str] = frozenset({"acquire"})

FACET_PRIMARY_CATEGORIES: tuple[str, ...] = (
    "模型层(谨慎)",
    "开源客户端(好抄)",
    "应用产品",
    "高价值复刻",
    "已验证变现",
    "变现案例",
    "数据算力",
    "安全合规",
    "政策市场",
    "Agent",
    "多模态",
)

# 历史 LLM/库内标签 → 当前规范大类
_LEGACY_CATEGORY_ALIASES: dict[str, str] = {
    "大模型": "模型层(谨慎)",
    "开源工具": "开源客户端(好抄)",
    "论文研究": "模型层(谨慎)",
    "易复刻": "高价值复刻",
    "高可复刻": "高价值复刻",
}

REPLICATION_TIER_ALLOWED: frozenset[str] = frozenset({"S", "A", "B", "C"})


def normalize_replication_tier(raw: object) -> str | None:
    """LLM 变现价值档位：S=高变现价值 … C=低变现；兼容旧「可复刻」别名。"""
    s = str(raw or "").strip().upper()
    if not s:
        return None
    alias = {
        "易": "S",
        "易复刻": "S",
        "高可复刻": "S",
        "高价值": "S",
        "高变现": "S",
        "极高": "S",
        "极易": "S",
        "较高可复刻": "A",
        "较高变现": "A",
        "可复刻": "A",
        "A级": "A",
        "B级": "B",
        "低可复刻": "C",
        "难": "C",
        "困难": "C",
    }
    s = alias.get(s, s)
    if s in REPLICATION_TIER_ALLOWED:
        return s
    if s and s[0] in REPLICATION_TIER_ALLOWED:
        return s[0]
    return None
FACET_CATEGORY_OTHER = "其他"
FACET_ALL_LABELS: frozenset[str] = frozenset((*FACET_PRIMARY_CATEGORIES, FACET_CATEGORY_OTHER))
FACET_DISPLAY_ORDER: tuple[str, ...] = (*FACET_PRIMARY_CATEGORIES, FACET_CATEGORY_OTHER)

# (canonical, keyword_substrings) — 按顺序匹配，专用规则在前
_CATEGORY_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("变现案例", ("acquire", "并购", "出售", "arr", "mrr", "估值", "退出")),
    ("已验证变现", ("付费", "订阅", "营收", "变现", "商业化", "saas 收入")),
    ("高价值复刻", ("高价值", "高可复刻", "易复刻", "变现", "付费", "订阅", "定价", "side project")),
    ("Agent", ("agent", "智能体", "工作流", "自动化")),
    ("政策市场", ("政策", "监管", "市场", "融资")),
    ("安全合规", ("安全", "对齐", "合规", "隐私", "风险")),
    ("数据算力", ("数据", "算力", "芯片", "训练", "gpu", "集群")),
    ("应用产品", ("应用", "产品", "发布", "上架", "product", "launch")),
    ("开源客户端(好抄)", ("开源", "客户端", "desktop", "electron", "tauri", "flutter", "chrome")),
    ("多模态", ("多模态", "图像", "语音", "视频", "生成")),
    ("模型层(谨慎)", ("大模型", "推理", "模型", "llm", "基座", "论文", "研究")),
)


def map_raw_label_to_canonical(raw: str) -> str:
    """将模型或历史库中的任意短标签映射到 10+其他 之一。"""
    s = normalize_ws(raw)
    if not s:
        return FACET_CATEGORY_OTHER
    if s in _LEGACY_CATEGORY_ALIASES:
        return _LEGACY_CATEGORY_ALIASES[s]
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
    elif k == "taaft":
        eng = 360.0 * _heat_log_norm(sig["views"], cap=2_000_000.0) + 140.0 * _heat_log_norm(sig["likes"], cap=50_000.0)
    elif k == "acquire":
        arr = 0.0
        try:
            root = json.loads((snippet or "")[:CONNECTOR_SNIPPET_MAX_CHARS])
            if isinstance(root, dict) and root.get("arr_usd") is not None:
                arr = float(root.get("arr_usd") or 0)
        except Exception:
            arr = 0.0
        eng = 400.0 * _heat_log_norm(max(0.0, arr), cap=100_000.0)
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
        "thenewsapi",
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
# Agent / 模型层主类与正文中的模型/Agent 信号仍一律视为 news。
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
        "模型层(谨慎)",
        "数据算力",
        "安全合规",
        "政策市场",
        "多模态",
        "变现案例",
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


def parse_replication_tiers_csv(raw: str | None) -> list[str] | None:
    """逗号分隔可复刻档位，如 ``S,A``；非法档位忽略。"""
    if not raw or not str(raw).strip():
        return None
    out: list[str] = []
    for part in str(raw).split(","):
        p = part.strip().upper()
        if p in REPLICATION_TIER_ALLOWED:
            out.append(p)
    return out or None


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
    from ..text_display import sanitize_stored_text_field

    try:
        v = json.loads(raw)
        if not isinstance(v, list):
            return []
        out: list[dict[str, str]] = []
        for item in v[:8]:
            if not isinstance(item, dict):
                continue
            label = sanitize_stored_text_field(str(item.get("label") or "").strip(), max_len=128)
            summary = sanitize_stored_text_field(str(item.get("summary") or "").strip(), max_len=2000)
            body_md = sanitize_stored_text_field(str(item.get("body_md") or "").strip(), max_len=50000)
            if not label or not summary or not body_md:
                continue
            out.append({"label": label, "summary": summary, "body_md": body_md})
        return out
    except Exception:
        return []


def build_connector_data_tab_markdown(admin_source_key: str, snippet: str) -> str:
    """从连接器片段生成规范「数据支撑」Markdown 表（规则兜底，避免仅 | 字段 | 内容 | 占位）。"""
    from ..text_display import format_connector_snippet_plain

    sk = (admin_source_key or "").strip().lower()
    plain_lines = format_connector_snippet_plain(snippet, admin_source_key=sk, max_len=8000)
    if not plain_lines:
        return ""
    rows: list[tuple[str, str]] = []
    for line in plain_lines.splitlines():
        line = line.strip()
        if "：" in line:
            a, _, b = line.partition("：")
            if a.strip() and b.strip():
                rows.append((a.strip(), b.strip()))
        elif ":" in line:
            a, _, b = line.partition(":")
            if a.strip() and b.strip():
                rows.append((a.strip(), b.strip()))
    if not rows:
        return f"## 数据支撑\n\n{plain_lines}"
    md = ["## 数据支撑", "", "| 指标 | 内容 |", "| --- | --- |"]
    for lab, val in rows[:14]:
        val_esc = val.replace("|", "\\|").replace("\n", " ")
        md.append(f"| {lab} | {val_esc} |")
    link_rows = extract_connector_detail_link_rows(sk, snippet)
    if link_rows:
        md.append("")
        md.append("**相关链接**")
        md.append("")
        for lab, url in link_rows:
            md.append(f"- [{lab}]({url})")
    return "\n".join(md)


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
    "thenewsapi": DETAIL_PROFILE_NEWS_WIRE,
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

# 模型偶发仍输出的旧 Tab 名 → 入库/展示时统一改成规范名（只改 label，正文不动）
TAB_LABEL_ALIASES: dict[str, str] = {
    "复刻评估": "变现评估",
    "功能亮点": "数据支撑",
    "要点": "数据支撑",
}


def normalize_tab_label(raw_label: str) -> str:
    lab = (raw_label or "").strip()
    return TAB_LABEL_ALIASES.get(lab, lab)


def canonical_feed_card_tab_label(raw_label: str) -> str:
    """同 normalize_tab_label（保留旧函数名供各处 import）。"""
    return normalize_tab_label(raw_label)


def required_feed_card_tab_labels(feed_kind: str) -> tuple[str, ...]:
    """应用泳道：描述 + 变现评估 + 数据支撑；资讯仍为描述 + 数据支撑。"""
    from .replication_analysis import FEED_CARD_TAB_REPLICATION

    fk = (feed_kind or "news").strip().lower()
    if fk == "apps":
        return (FEED_CARD_TAB_DESCRIPTION, FEED_CARD_TAB_REPLICATION, FEED_CARD_TAB_DATA)
    return (FEED_CARD_TAB_DESCRIPTION, FEED_CARD_TAB_DATA)


def feed_card_highlights_tab_label(raw_label: str) -> bool:
    return normalize_tab_label(raw_label) == FEED_CARD_TAB_DATA


# 资讯/社区源（原文偏短）：略放宽 tab 字数门槛，仍要求双 tab + 单合法大类。
_NEWS_API_RELAXED_SOURCES = frozenset(
    {"newsapi", "thenewsapi", "finnhub", "hacker_news", "arxiv"}
)

# 快讯类上游：仅有 title/url、无正文摘要时不应调用 LLM（避免入库后前台只剩链接表）。
NEWS_WIRE_UPSTREAM_SOURCES = frozenset(
    {"newsapi", "thenewsapi", "finnhub", "hacker_news", "youtube_data", "mapbox"}
)

# 上游素材（description / story_text / 二次拉取正文）至少可读字数（汉字 + 英文词），不含标题与 URL。
# 快讯多为英文，不能用「仅汉字」衡量。
NEWS_WIRE_UPSTREAM_MIN_CHARS = 60
# 兼容旧名（测试/脚本引用）
NEWS_WIRE_UPSTREAM_MIN_CJK = NEWS_WIRE_UPSTREAM_MIN_CHARS

# 润色稿 feed_kind=news 时，去 URL 后除总字数外还须达到的汉字数（避免英文字段名凑字数）。
PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS = 48
# apps 稿：「描述」「变现评估」tab 单独验汉字（勿用全文或其它 tab 凑过）。
PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_DESC = 48
PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_REPL = 24
# Product Hunt 入库前：上游 tagline/description 等可读字数下限。
PRODUCT_HUNT_UPSTREAM_MIN_CHARS = 35

_CONNECTOR_UPSTREAM_TEXT_KEYS = (
    "description",
    "readme_md",
    "story_text",
    "content",
    "snippet",
    "abstract",
    "summary",
    "article_body",
)


_URL_IN_TEXT_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]+\)")
# 发布/连接器入库：去掉 URL 与链接占位后，至少须有的可读字数（汉字或 ≥3 字母英文词）。
PUBLISH_MIN_SUBSTANTIVE_CHARS = 80

_LINK_ONLY_BOILERPLATE_PHRASES = (
    "相关链接",
    "原文链接",
    "完整拆解见",
    "连接器同步快照",
    "HTTP 200",
    "HTTP 404",
    "暂无返回内容",
)


def strip_urls_and_markdown_links(text: str) -> str:
    """去掉 Markdown 链接与裸 URL，用于判断「仅链接」稿。"""
    s = (text or "").strip()
    if not s:
        return ""
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _URL_IN_TEXT_RE.sub(" ", s)
    for phrase in _LINK_ONLY_BOILERPLATE_PHRASES:
        s = s.replace(phrase, " ")
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`[^`]+`", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def polish_substantive_cjk_count(text: str) -> int:
    """去 URL/链接后的汉字数。"""
    s = strip_urls_and_markdown_links(text)
    if not s:
        return 0
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def polish_substantive_char_count(text: str) -> int:
    """去 URL/链接后的有效字数：汉字 + 连续英文词（≥3 字母）。"""
    s = strip_urls_and_markdown_links(text)
    if not s:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", s))
    latin = sum(len(w) for w in re.findall(r"[A-Za-z]{3,}", s))
    return cjk + latin


def connector_snippet_upstream_text_blob(snippet: str) -> str:
    """连接器单条 JSON 中可供扩写的上游正文字段（不含 title/url 占位）。"""
    s = (snippet or "").strip()[:CONNECTOR_SNIPPET_MAX_CHARS]
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except Exception:
        return s[:4000]
    if not isinstance(obj, dict):
        return ""
    parts: list[str] = []
    for key in _CONNECTOR_UPSTREAM_TEXT_KEYS:
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    return "\n".join(parts)


def connector_upstream_material_char_count(snippet: str) -> int:
    """快讯 snippet 上游正文字段的可读字数（汉字 + 英文词）。"""
    return polish_substantive_char_count(connector_snippet_upstream_text_blob(snippet))


def connector_upstream_has_ingest_material(
    snippet: str,
    admin_source_key: str,
    *,
    min_chars: int = NEWS_WIRE_UPSTREAM_MIN_CHARS,
) -> tuple[bool, str]:
    """
    快讯源入库前：上游须有可读摘要/正文，避免 LLM 从 title+url 硬凑「仅链接」稿。
    非 NEWS_WIRE 源不校验（GitHub/PH 等由专用打包提供厚素材）。
    """
    sk = (admin_source_key or "").strip().lower()
    if sk == "github":
        got = connector_upstream_material_char_count(snippet)
        has_readme = False
        try:
            obj = json.loads((snippet or "").strip())
            if isinstance(obj, dict):
                has_readme = bool(str(obj.get("readme_md") or "").strip())
        except json.JSONDecodeError:
            pass
        if got >= 40:
            return True, ""
        if has_readme and got >= 12:
            return True, ""
        return (
            False,
            f"GitHub 上游过薄（去 URL 后 {got} 字；无 readme_md 或 description 过短），"
            "请配置 GitHub Token 并确认 Trending 拉取成功",
        )
    if sk == "product_hunt":
        got = connector_upstream_material_char_count(snippet)
        if got >= int(PRODUCT_HUNT_UPSTREAM_MIN_CHARS):
            return True, ""
        return (
            False,
            f"Product Hunt 上游过薄（description/tagline 等去 URL 后仅 {got} 字，"
            f"至少需 {PRODUCT_HUNT_UPSTREAM_MIN_CHARS} 字才润色入库）",
        )
    if sk not in NEWS_WIRE_UPSTREAM_SOURCES:
        return True, ""
    got = connector_upstream_material_char_count(snippet)
    if got >= int(min_chars):
        return True, ""
    return (
        False,
        f"上游素材过薄（description/story_text 等去 URL 后仅 {got} 字可读内容，"
        f"快讯源至少需 {min_chars} 字才入库）",
    )


def polish_tab_body_by_label(data: dict, label: str) -> str:
    """润色 JSON 中指定 Tab 的 body_md。"""
    tabs = data.get("tabs")
    if not isinstance(tabs, list):
        return ""
    want = (label or "").strip()
    for t in tabs:
        if not isinstance(t, dict):
            continue
        if str(t.get("label") or "").strip() == want:
            return str(t.get("body_md") or "").strip()
    return ""


def collect_polish_text_blob(data: dict) -> str:
    """合并标题、摘要、正文与各 Tab 文案。"""
    parts: list[str] = []
    for key in ("title", "summary", "body_md"):
        v = str(data.get(key) or "").strip()
        if v:
            parts.append(v)
    tabs = data.get("tabs")
    if isinstance(tabs, list):
        for t in tabs:
            if not isinstance(t, dict):
                continue
            for key in ("label", "summary", "body_md"):
                v = str(t.get(key) or "").strip()
                if v:
                    parts.append(v)
    return "\n".join(parts)


def polish_payload_has_substantive_content(
    data: dict, *, min_chars: int = PUBLISH_MIN_SUBSTANTIVE_CHARS
) -> bool:
    """润色 JSON 入库前：除链接/占位摘要外须有可读正文。"""
    blob = collect_polish_text_blob(data)
    stripped = strip_urls_and_markdown_links(blob)
    total = polish_substantive_char_count(stripped)
    if total < int(min_chars):
        return False
    fk = str(data.get("feed_kind") or "news").strip().lower()
    if fk == "news":
        cjk = polish_substantive_cjk_count(stripped)
        if cjk < PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS:
            return False
    if fk == "apps":
        from ..text_display import body_is_connector_kv_metadata

        desc_body = polish_tab_body_by_label(data, FEED_CARD_TAB_DESCRIPTION)
        if polish_substantive_cjk_count(desc_body) < PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_DESC:
            return False
        if body_is_connector_kv_metadata(desc_body):
            return False
        from .replication_analysis import FEED_CARD_TAB_REPLICATION

        repl_body = polish_tab_body_by_label(data, FEED_CARD_TAB_REPLICATION)
        if polish_substantive_cjk_count(repl_body) < PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_REPL:
            return False
        if body_is_connector_kv_metadata(repl_body):
            return False
    return True


def stored_article_text_blob(
    *,
    title: str = "",
    summary: str = "",
    body: str = "",
    ai_tabs_json: str | None = None,
) -> str:
    """已存文章字段合并为一段文本，供实质内容检测。"""
    parts: list[str] = []
    for v in (title, summary, body):
        s = str(v or "").strip()
        if s:
            parts.append(s)
    for t in parse_article_tabs_json(ai_tabs_json):
        for key in ("summary", "body_md"):
            s = str(t.get(key) or "").strip()
            if s:
                parts.append(s)
    return "\n".join(parts)


def stored_article_has_substantive_content(
    *,
    title: str = "",
    summary: str = "",
    body: str = "",
    ai_tabs_json: str | None = None,
    feed_kind: str = "news",
    min_chars: int = PUBLISH_MIN_SUBSTANTIVE_CHARS,
) -> bool:
    """后台发布或读库校验：无实质内容不得 status=published。"""
    blob = stored_article_text_blob(
        title=title, summary=summary, body=body, ai_tabs_json=ai_tabs_json
    )
    stripped = strip_urls_and_markdown_links(blob)
    if polish_substantive_char_count(stripped) < int(min_chars):
        return False
    fk = (feed_kind or "news").strip().lower()
    if fk == "news" and polish_substantive_cjk_count(stripped) < PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS:
        return False
    return True


def substantive_content_reject_message(
    *,
    got: int,
    min_chars: int = PUBLISH_MIN_SUBSTANTIVE_CHARS,
    got_cjk: int | None = None,
    feed_kind: str = "news",
) -> str:
    fk = (feed_kind or "news").strip().lower()
    extra = ""
    if fk == "news" and got_cjk is not None and got_cjk < PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS:
        extra = (
            f" 资讯稿还须至少 {PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS} 个汉字（当前 {got_cjk}），"
            "不能仅靠英文元数据或链接表凑字数。"
        )
    elif fk == "apps":
        extra = (
            f" 应用稿「描述」须至少 {PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_DESC} 个汉字，"
            f"「变现评估」须至少 {PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_REPL} 个汉字，"
            "且不得用产品/标语/投票/官网等字段表充当正文。"
        )
    return (
        f"无实质内容不能入库/发布：去掉链接与 URL 后正文仅 {got} 字，"
        f"至少需要 {min_chars} 字可读说明。{extra}"
    )


def publish_polish_length_thresholds(admin_source_key: str | None = None) -> dict[str, int]:
    """返回 validate_llm_polish_for_publish / 诊断文案共用的最低字数。"""
    sk = (admin_source_key or "").strip().lower()
    if sk in _NEWS_API_RELAXED_SOURCES:
        return {
            "desc_summary": 56,
            "desc_body": 96,
            "repl_summary": 48,
            "repl_body": 120,
            "hi_summary": 10,
            "hi_body": 48,
            "tab_body_total": 240,
            "body_md_min": 80,
            "body_md_short_tabs_total": 420,
        }
    return {
        "desc_summary": 72,
        "desc_body": 120,
        "repl_summary": 52,
        "repl_body": 180,
        "hi_summary": 12,
        "hi_body": 60,
        "tab_body_total": 380,
        "body_md_min": 120,
        "body_md_short_tabs_total": 600,
    }


def validate_llm_polish_for_publish(data: dict, *, admin_source_key: str | None = None) -> bool:
    """连接器入库：必须含合格分类、可读摘要与足够厚的总览/分 tab 正文。"""
    th = publish_polish_length_thresholds(admin_source_key)
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
    raw_cat = clean_cats[0]
    if raw_cat not in FACET_ALL_LABELS and raw_cat not in _LEGACY_CATEGORY_ALIASES:
        return False
    fk = str(data.get("feed_kind") or "news").strip().lower()
    if fk not in ("news", "apps"):
        fk = "news"
    need_labels = required_feed_card_tab_labels(fk)
    from .replication_analysis import (
        FEED_CARD_TAB_REPLICATION,
        normalize_replication_analysis,
        validate_replication_analysis_for_publish,
    )

    tabs = data.get("tabs")
    if not isinstance(tabs, list):
        return False
    if len(tabs) != len(need_labels):
        return False
    from ..text_display import (
        body_is_connector_kv_metadata,
        polish_content_has_connector_api_leak,
    )

    tab_body_total = 0
    labels: list[str] = []
    for t in tabs:
        if not isinstance(t, dict):
            return False
        lab = str(t.get("label") or "").strip()
        summ = str(t.get("summary") or "").strip()
        body = str(t.get("body_md") or "").strip()
        labels.append(lab)
        if lab == need_labels[0]:
            min_summ, min_body = th["desc_summary"], th["desc_body"]
        elif lab == FEED_CARD_TAB_REPLICATION:
            min_summ, min_body = th.get("repl_summary", 64), th.get("repl_body", 180)
        else:
            min_summ, min_body = th["hi_summary"], th["hi_body"]
        if len(lab) < 2 or len(summ) < min_summ or len(body) < min_body:
            return False
        if polish_content_has_connector_api_leak(summ) or polish_content_has_connector_api_leak(body):
            return False
        if lab in (FEED_CARD_TAB_DESCRIPTION, FEED_CARD_TAB_REPLICATION):
            if body_is_connector_kv_metadata(body):
                return False
            min_cjk = (
                PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_DESC
                if lab == FEED_CARD_TAB_DESCRIPTION
                else PUBLISH_MIN_SUBSTANTIVE_CJK_APPS_REPL
            )
            if fk == "apps" and polish_substantive_cjk_count(body) < min_cjk:
                return False
            if fk == "news" and lab == FEED_CARD_TAB_DESCRIPTION:
                if polish_substantive_cjk_count(body) < PUBLISH_MIN_SUBSTANTIVE_CJK_NEWS:
                    return False
        tab_body_total += len(body)
    if labels != list(need_labels):
        return False
    if fk == "apps":
        norm = normalize_replication_analysis(data.get("replication_analysis"))
        if not validate_replication_analysis_for_publish(norm):
            return False
    if tab_body_total < th["tab_body_total"]:
        return False
    if len(body_md) < th["body_md_min"] and tab_body_total < th["body_md_short_tabs_total"]:
        return False
    if polish_content_has_connector_api_leak(body_md):
        return False
    if not polish_payload_has_substantive_content(data):
        return False
    return True


def article_freshness_datetime(
    *,
    published_at: datetime | None,
    updated_at: datetime | None,
) -> datetime | None:
    """公开列表排序/时间窗：以最近入库或连接器刷新为准，避免上游旧 ``published_at`` 把稿挤出窗口。"""
    if published_at is None:
        return updated_at
    if updated_at is None:
        return published_at
    return updated_at if updated_at > published_at else published_at


def article_freshness_for_row(a: Article) -> datetime | None:
    return article_freshness_datetime(published_at=a.published_at, updated_at=a.updated_at)


def parse_replication_analysis_json(raw: str | None):
    from .replication_analysis import parse_replication_analysis_json as _parse

    return _parse(raw)


def estimated_hours_mvp_label(data: dict | None) -> str | None:
    from .replication_analysis import estimated_hours_mvp_label as _label

    return _label(data)


def article_freshness_sql_expr() -> ColumnElement:
    """SQL 版 ``article_freshness_datetime``，供筛选与 ORDER BY。"""
    return case(
        (
            and_(
                Article.published_at.isnot(None),
                Article.updated_at.isnot(None),
                Article.updated_at > Article.published_at,
            ),
            Article.updated_at,
        ),
        (Article.published_at.isnot(None), Article.published_at),
        else_=Article.updated_at,
    )


def published_calendar_day(db: Session):
    """按 UTC 日历日分组公开 feed（与列表 ``display_at`` 一致，用展示时效而非仅源站发布时间）。"""
    fe = article_freshness_sql_expr()
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m-%d", fe)
    return cast(fe, Date)
