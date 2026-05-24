"""连接器两阶段取数：先按热度取前 N 条，再逐条拉详情，打包为 ``connector_sync_items_v1`` 供入库。"""
from __future__ import annotations

import base64
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx

from .domain.articles import CONNECTOR_HEAT_TOP_N, CONNECTOR_SNIPPET_MAX_CHARS

PH_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"
# Product Hunt 日榜按旧金山日历日计；与官网 Daily / 邮件 Top10 对齐，勿用 order:RANKING（全局历史排名）。
PH_LAUNCH_TZ = ZoneInfo("America/Los_Angeles")
GITHUB_TRENDING_DEFAULT = "https://github.com/trending?since=daily"
_GITHUB_TRENDING_HOSTS = frozenset({"github.com", "www.github.com"})
_GITHUB_TRENDING_SKIP_SLUGS = frozenset(
    {
        "trending",
        "features",
        "enterprise",
        "pricing",
        "login",
        "signup",
        "topics",
        "collections",
        "sponsors",
        "customer-stories",
        "readme",
        "security",
        "about",
    }
)

# 单条详情写入 pack 前的上限，避免 10 条撑爆总 snippet
_PER_ITEM_SNIPPET_MAX = min(48_000, CONNECTOR_SNIPPET_MAX_CHARS // 10)
_README_MD_MAX = 24_000

# GitHub Trending：仅保留「可复刻客户端 / 桌面 / 插件」向仓库
GITHUB_CLIENT_KEYWORDS: tuple[str, ...] = (
    "desktop-app",
    "desktop app",
    "desktop",
    "tauri",
    "electron",
    "flutter",
    "chrome-extension",
    "chrome extension",
    "browser extension",
    "client",
    "gui",
    "cross-platform",
    "cross platform",
    "macos",
    "windows",
    "linux",
    "native",
    "swift",
    "kotlin",
    "react native",
    "vscode",
    "vs code",
    "mobile app",
    "ios app",
    "android app",
    "wpf",
    "qt",
    "gtk",
)

TAAFT_NEW_DEFAULT = "https://theresanaiforthat.com/new/"
ACQUIRE_PORTAL_DEFAULT = "https://acquire.com/"
ACQUIRE_SEARCH_API_DEFAULT = "https://us-central1-microacquire.cloudfunctions.net/v1-search"
# 与 Acquire 官网 JS 中 anon 搜索一致的 __meta.cookie（公开页嵌入值）
_ACQUIRE_SEARCH_META_COOKIE = "lockModeAccess=SZL1hM0m5b35UBOJTDts262pOk"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _http_get_text(url: str, headers: dict[str, str], *, timeout: float = 45.0) -> tuple[int, str]:
    """GET HTML；优先 curl_cffi 模拟浏览器（绕过 TAAFT Cloudflare）。"""
    h = {
        **headers,
        "User-Agent": _BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    host = (urlsplit(url).netloc or "").lower()
    needs_browser = "theresanaiforthat.com" in host
    last_code, last_text = 0, ""
    for attempt in range(3):
        try:
            from curl_cffi import requests as cf_requests

            r = cf_requests.get(
                url,
                headers=h,
                impersonate="chrome131",
                timeout=timeout,
                allow_redirects=True,
            )
            last_code, last_text = int(r.status_code or 0), r.text or ""
            if last_code == 200 and (not needs_browser or "theresanaiforthat.com/ai/" in last_text):
                return last_code, last_text
            if last_code == 403 and attempt < 2:
                time.sleep(1.5 + attempt)
                continue
            if not needs_browser and 200 <= last_code < 300:
                return last_code, last_text
        except Exception:
            if attempt < 2:
                time.sleep(1.0)
                continue
        if not needs_browser:
            break
    if needs_browser:
        return last_code or 403, last_text
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(url, headers=h)
        return r.status_code, r.text or ""


def acquire_search_api_is_url(url: str) -> bool:
    p = urlsplit((url or "").strip())
    host = (p.netloc or "").lower()
    return "microacquire.cloudfunctions.net" in host and "/v1-search" in (p.path or "")


def _decode_github_readme_body(readme_json: dict[str, Any]) -> str:
    enc = str(readme_json.get("encoding") or "").strip().lower()
    raw = readme_json.get("content") or ""
    if enc == "base64" and isinstance(raw, str):
        try:
            return base64.b64decode(raw).decode("utf-8", errors="replace")
        except (ValueError, UnicodeDecodeError):
            return ""
    if isinstance(raw, str):
        return raw
    return ""


def _attach_github_readme(
    client: httpx.Client,
    api_url: str,
    api_headers: dict[str, str],
    repo: dict[str, Any],
) -> None:
    """GET /repos/{owner}/{repo}/readme，解码正文供 LLM 理解项目用途。"""
    md = ""
    try:
        rr = client.get(
            f"{api_url}/readme",
            headers={**api_headers, "Accept": "application/vnd.github.raw+json"},
        )
        if rr.status_code == 200 and (rr.text or "").strip():
            md = (rr.text or "")[:_README_MD_MAX]
        else:
            rr2 = client.get(f"{api_url}/readme", headers={**api_headers, "Accept": "application/json"})
            if 200 <= rr2.status_code < 300:
                try:
                    readme = rr2.json()
                except json.JSONDecodeError:
                    readme = None
                if isinstance(readme, dict):
                    md = _decode_github_readme_body(readme)[:_README_MD_MAX]
        if md.strip():
            repo["readme_md"] = md
    except Exception:
        return


def github_trending_is_discovery_url(url: str) -> bool:
    """``github.com/trending`` 为 HTML 发现页；``api.github.com`` 为 REST 直拉。"""
    p = urlsplit((url or "").strip())
    host = (p.netloc or "").lower().split(":", 1)[0]
    if host not in _GITHUB_TRENDING_HOSTS:
        return False
    path = (p.path or "").strip("/").lower()
    return path == "trending" or path.startswith("trending/")


def _github_valid_repo_slug(slug: str) -> bool:
    s = (slug or "").strip().strip("/")
    if s.count("/") != 1:
        return False
    owner, repo = s.split("/", 1)
    if not owner or not repo:
        return False
    if owner.lower() in _GITHUB_TRENDING_SKIP_SLUGS or repo.lower() in _GITHUB_TRENDING_SKIP_SLUGS:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", s))


def github_matches_client_filter(repo: dict[str, Any]) -> bool:
    """Repository topics + description + 仓库名 须命中客户端/桌面/插件向关键词之一。"""
    topics = [str(t).lower() for t in (repo.get("topics") or []) if t]
    blob = " ".join(topics) + " " + str(repo.get("description") or "").lower()
    blob += " " + str(repo.get("full_name") or repo.get("name") or "").lower().replace("/", " ")
    return any(k in blob for k in GITHUB_CLIENT_KEYWORDS)


def _github_trending_chunk_description(chunk: str) -> str:
    p = re.search(r"<p[^>]*>([^<]{8,480})</p>", chunk, flags=re.IGNORECASE)
    if not p:
        return ""
    return re.sub(r"\s+", " ", p.group(1)).strip()


def _github_minimal_repo_from_trending_row(row: dict[str, Any]) -> dict[str, Any]:
    """无 GitHub API 详情时，用 Trending HTML 字段拼最小仓库 JSON（供入库价值分与 LLM）。"""
    slug = str(row.get("full_name") or "").strip()
    owner, _, name = slug.partition("/")
    desc = str(row.get("description") or "").strip()
    stars_today = row.get("stars_today")
    repo: dict[str, Any] = {
        "full_name": slug,
        "name": name or slug,
        "owner": {"login": owner} if owner else {},
        "html_url": f"https://github.com/{slug}",
        "description": desc or f"GitHub Trending client-oriented repo {slug}",
        "topics": [],
        "stargazers_count": 0,
        "language": "",
    }
    if stars_today is not None:
        repo["trending_stars_today"] = stars_today
    return repo


def taaft_list_is_new_tools_url(url: str) -> bool:
    p = urlsplit((url or "").strip())
    host = (p.netloc or "").lower()
    if "theresanaiforthat.com" not in host:
        return False
    path = (p.path or "").strip("/").lower()
    return path in ("new", "new/") or path.startswith("new/")


def acquire_portal_is_list_url(url: str) -> bool:
    u = (url or "").strip()
    if acquire_search_api_is_url(u):
        return True
    p = urlsplit(u)
    host = (p.netloc or "").lower()
    return "acquire.com" in host


def _github_trending_since(url: str) -> str:
    q = dict(parse_qsl(urlsplit((url or "").strip()).query, keep_blank_values=True))
    since = str(q.get("since") or "daily").strip().lower()
    return since if since in {"daily", "weekly", "monthly"} else "daily"


def parse_github_trending_repos(html: str, *, limit: int = CONNECTOR_HEAT_TOP_N) -> list[dict[str, Any]]:
    """从 Trending HTML 解析 ``owner/repo`` 与可选的 ``N stars today``（按页面顺序）。"""
    if not (html or "").strip():
        return []
    chunks = re.split(r"<article\b", html, flags=re.IGNORECASE)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks[1:]:
        m = re.search(r'href="/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"', chunk)
        if not m:
            continue
        slug = m.group(1).split("?")[0].strip("/")
        if not _github_valid_repo_slug(slug) or slug in seen:
            continue
        seen.add(slug)
        stars_today: int | None = None
        sm = re.search(r"([\d,]+)\s+stars?\s+today", chunk, flags=re.IGNORECASE)
        if sm:
            try:
                stars_today = int(sm.group(1).replace(",", ""))
            except ValueError:
                stars_today = None
        out.append(
            {
                "full_name": slug,
                "stars_today": stars_today,
                "rank": len(out) + 1,
                "description": _github_trending_chunk_description(chunk),
            }
        )
        if len(out) >= limit:
            break
    return out


def sync_github_trending_top_details(discovery_url: str, headers: dict[str, str]) -> tuple[int, str]:
    """GET Trending HTML → 解析榜单 → 对每个 repo GET ``api.github.com/repos/{owner}/{repo}``。"""
    n = CONNECTOR_HEAT_TOP_N
    url = (discovery_url or "").strip() or GITHUB_TRENDING_DEFAULT
    since = _github_trending_since(url)
    html_headers = {
        **headers,
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": headers.get("User-Agent") or "AiTrends-GitHubTrending/1.0",
    }
    api_headers = {
        **headers,
        "Accept": "application/vnd.github+json",
        "User-Agent": headers.get("User-Agent") or "AiTrends-GitHubTrending/1.0",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(url, headers=html_headers)
            if r.status_code < 200 or r.status_code >= 300:
                return r.status_code, (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
            ranked = parse_github_trending_repos(r.text or "", limit=max(n * 4, 30))
            if not ranked:
                return r.status_code, json.dumps(
                    {"connector_sync_items_v1": [], "note": "trending_parse_empty", "since": since},
                    ensure_ascii=False,
                )
            payloads: list[dict[str, Any]] = []
            has_auth = bool((api_headers.get("Authorization") or "").strip())
            api_pause_s = 0.15 if has_auth else 1.25
            for row in ranked:
                slug = str(row.get("full_name") or "").strip()
                if not slug:
                    continue
                api_url = f"https://api.github.com/repos/{slug}"
                if payloads:
                    time.sleep(api_pause_s)
                r2 = client.get(api_url, headers=api_headers)
                if r2.status_code == 403 and not has_auth:
                    time.sleep(3.0)
                    r2 = client.get(api_url, headers=api_headers)
                repo: dict[str, Any] | None = None
                if 200 <= r2.status_code < 300:
                    try:
                        parsed = json.loads(r2.text or "{}")
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        repo = parsed
                elif not has_auth:
                    repo = _github_minimal_repo_from_trending_row(row)
                if not repo:
                    continue
                if not github_matches_client_filter(repo):
                    continue
                extra: dict[str, Any] = {"since": since, "rank": row.get("rank"), "discovery_url": url}
                if row.get("stars_today") is not None:
                    extra["stars_today"] = row["stars_today"]
                repo["_aisoul_trending"] = extra
                if row.get("stars_today") is not None:
                    repo["trending_stars_today"] = row["stars_today"]
                _attach_github_readme(client, api_url, api_headers, repo)
                payloads.append(repo)
            if not payloads and ranked:
                for row in ranked[:n]:
                    repo = _github_minimal_repo_from_trending_row(row)
                    extra = {"since": since, "rank": row.get("rank"), "discovery_url": url, "filter_fallback": True}
                    repo["_aisoul_trending"] = extra
                    if row.get("stars_today") is not None:
                        repo["trending_stars_today"] = row["stars_today"]
                    payloads.append(repo)
                    if len(payloads) >= n:
                        break
            if not payloads:
                return r.status_code, json.dumps(
                    {"connector_sync_items_v1": [], "note": "repo_api_empty", "since": since},
                    ensure_ascii=False,
                )
            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in payloads
                ],
                "note": f"github_trending_{since}",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def huggingface_api_spaces_is_list_index(url: str) -> bool:
    """``/api/spaces`` 列表（可带 query）；``/api/spaces/owner/name`` 为单条详情，不走热度打包。"""
    p = urlsplit((url or "").strip())
    segs = [x for x in p.path.strip("/").split("/") if x]
    return len(segs) == 2 and segs[0] == "api" and segs[1] == "spaces"


def _trim_pack_json(obj: dict[str, Any]) -> str:
    raw = json.dumps(obj, ensure_ascii=False)
    if len(raw) <= CONNECTOR_SNIPPET_MAX_CHARS:
        return raw
    items = obj.get("connector_sync_items_v1")
    if not isinstance(items, list):
        return raw[:CONNECTOR_SNIPPET_MAX_CHARS]
    while len(items) > 1 and len(raw) > CONNECTOR_SNIPPET_MAX_CHARS:
        items.pop()
        raw = json.dumps(obj, ensure_ascii=False)
    if len(raw) > CONNECTOR_SNIPPET_MAX_CHARS:
        return raw[:CONNECTOR_SNIPPET_MAX_CHARS]
    return raw


def _post_ph_graphql(client: httpx.Client, headers: dict[str, str], query: str) -> tuple[int, dict[str, Any] | None]:
    h = {**headers, "Content-Type": "application/json"}
    r = client.post(PH_GRAPHQL_URL, headers=h, json={"query": query})
    try:
        body = json.loads(r.text or "{}")
    except Exception:
        return r.status_code, None
    if not isinstance(body, dict):
        return r.status_code, None
    return r.status_code, body


def _ph_day_start_utc_iso(*, days_ago: int = 0) -> str:
    """Product Hunt 日榜起点：America/Los_Angeles 当日 00:00 转 UTC ISO。"""
    now_pt = datetime.now(PH_LAUNCH_TZ)
    day_pt = (now_pt - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    return day_pt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ph_posts_list_query(*, n: int, posted_after: str, posted_before: str | None = None) -> str:
    before = f', postedBefore: "{posted_before}"' if posted_before else ""
    return (
        f'{{ posts(first: {n}, order: VOTES, featured: true, postedAfter: "{posted_after}"{before}) '
        f"{{ edges {{ node {{ id slug name tagline votesCount featuredAt }} }} }} }}"
    )


def _ph_parse_post_nodes(body: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not body or body.get("errors"):
        return []
    posts = (body.get("data") or {}).get("posts") or {}
    nodes: list[dict[str, Any]] = []
    for e in posts.get("edges") or []:
        if isinstance(e, dict) and isinstance(e.get("node"), dict):
            nodes.append(e["node"])
    return nodes


def _ph_fetch_daily_featured_posts(
    client: httpx.Client, headers: dict[str, str], *, n: int
) -> tuple[int, list[dict[str, Any]], str]:
    """
    对齐 PH 邮件/Leaderboard「昨日 Top launches」：PT 昨日 00:00–今日 00:00 窗口内精选按票数 Top N。
    （须 postedBefore，否则会把今日 featured 产品混进昨日榜。）
    返回 (http_code, nodes, note)。
    """
    posted_after = _ph_day_start_utc_iso(days_ago=1)
    posted_before = _ph_day_start_utc_iso(days_ago=0)
    code, body = _post_ph_graphql(
        client,
        headers,
        _ph_posts_list_query(n=n, posted_after=posted_after, posted_before=posted_before),
    )
    nodes = _ph_parse_post_nodes(body)
    if nodes:
        return code or 200, nodes[:n], "ph_leaderboard_pt_yesterday_votes"
    if body and body.get("errors"):
        err = json.dumps(body, ensure_ascii=False)[:2000]
        return code or 502, [], err
    return 200, [], "no_posts"


def sync_product_hunt_top_details(headers: dict[str, str]) -> tuple[int, str]:
    """PT 日榜精选 + 按票数 Top N（对齐官网 Daily / 邮件），再对每个 slug 拉详情。"""
    n = CONNECTOR_HEAT_TOP_N
    try:
        with httpx.Client(timeout=45.0) as client:
            code, nodes, list_note = _ph_fetch_daily_featured_posts(client, headers, n=n)
            if list_note.startswith("{") and "errors" in list_note:
                return (code or 502, list_note)
            if not nodes:
                return code, json.dumps({"connector_sync_items_v1": [], "note": "no_posts"}, ensure_ascii=False)

            slugs: list[str] = []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                slug = str(node.get("slug") or "").strip()
                if slug:
                    slugs.append(slug)
            if not slugs:
                return code, json.dumps({"connector_sync_items_v1": [], "note": "no_slugs"}, ensure_ascii=False)

            detail_frag = (
                "{ id slug name tagline description votesCount commentsCount website url createdAt featuredAt "
                "makers { name username } thumbnail { url } media { type url } "
                "topics(first: 8) { edges { node { name } } } }"
            )
            payloads: list[dict[str, Any]] = []
            for slug in slugs:
                q = f"query {{ post(slug: {json.dumps(slug)}) {detail_frag} }}"
                c2, b2 = _post_ph_graphql(client, headers, q)
                if c2 and (c2 < 200 or c2 >= 300):
                    continue
                if not b2 or b2.get("errors"):
                    continue
                post = (b2.get("data") or {}).get("post")
                if not isinstance(post, dict):
                    continue
                payloads.append(post)

            if not payloads:
                return code, json.dumps({"connector_sync_items_v1": [], "note": "detail_fetch_empty"}, ensure_ascii=False)

            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in payloads
                ],
                "note": list_note,
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def _hf_list_pool_limit(url: str) -> tuple[str, int]:
    """返回用于发现排序的列表 URL，并保证 limit 足够大以便按 trendingScore 截前 N。"""
    parts = urlsplit(url.strip() or "https://huggingface.co/api/spaces?trending=true")
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("trending", "true")
    try:
        lim = int(str(q.get("limit") or "80").strip() or "80")
    except ValueError:
        lim = 80
    lim = max(CONNECTOR_HEAT_TOP_N, min(lim, 120))
    q["limit"] = str(lim)
    path = parts.path or "/api/spaces"
    if not path.rstrip("/").endswith("/spaces"):
        if "/api/spaces" not in path:
            path = "/api/spaces"
    u = urlunsplit((parts.scheme or "https", parts.netloc or "huggingface.co", path, urlencode(q), ""))
    return u, lim


HN_ALGOLIA_SEARCH_DEFAULT = "https://hn.algolia.com/api/v1/search?tags=front_page"
NEWSAPI_TOP_HEADLINES_DEFAULT = (
    "https://newsapi.org/v2/everything?q=artificial+intelligence&language=en"
    "&sortBy=publishedAt&pageSize=20"
)
THENEWSAPI_TOP_DEFAULT = (
    "https://api.thenewsapi.com/v1/news/top?locale=us&language=en&categories=tech"
    "&search=artificial+intelligence&limit=10"
)
_AI_NEWS_KEYWORDS: tuple[str, ...] = (
    "artificial intelligence",
    "machine learning",
    " openai",
    " chatgpt",
    "anthropic",
    " deepseek",
    " llm",
    " generative ai",
    " gemini",
    " copilot",
    "nvidia ai",
    " ai ",
    " ai,",
    " ai.",
)


def hacker_news_algolia_is_search_url(url: str) -> bool:
    """Algolia HN Search API（列表发现）；非 ``firebaseio.com`` 单条 item API。"""
    p = urlsplit((url or "").strip().lower())
    return "hn.algolia.com" in (p.netloc or "") and "/api/" in (p.path or "")


def newsapi_is_v2_url(url: str) -> bool:
    p = urlsplit((url or "").strip().lower())
    return "newsapi.org" in (p.netloc or "") and "/v2/" in (p.path or "")


def thenewsapi_is_news_url(url: str) -> bool:
    p = urlsplit((url or "").strip().lower())
    return "thenewsapi.com" in (p.netloc or "") and "/v1/news/" in (p.path or "")


def _news_text_ai_relevant(title: str, description: str) -> bool:
    blob = f"{title} {description}".lower()
    return any(k in blob for k in _AI_NEWS_KEYWORDS)


def _normalize_newsapi_article(art: dict[str, Any]) -> dict[str, Any]:
    src = art.get("source") if isinstance(art.get("source"), dict) else {}
    return {
        "source": "newsapi",
        "title": (art.get("title") or "").strip(),
        "url": (art.get("url") or "").strip(),
        "description": (art.get("description") or art.get("content") or "").strip()[:8000],
        "publishedAt": art.get("publishedAt"),
        "urlToImage": art.get("urlToImage"),
        "author": art.get("author"),
        "source_name": (src.get("name") or src.get("id") or "").strip(),
        "uuid": (art.get("url") or "").strip(),
    }


def _normalize_thenewsapi_article(art: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "thenewsapi",
        "title": (art.get("title") or "").strip(),
        "url": (art.get("url") or "").strip(),
        "description": (art.get("description") or art.get("snippet") or "").strip()[:8000],
        "published_at": art.get("published_at"),
        "image_url": art.get("image_url"),
        "source_name": (art.get("source") or "").strip(),
        "uuid": (art.get("uuid") or art.get("url") or "").strip(),
        "categories": art.get("categories"),
        "relevance_score": art.get("relevance_score"),
    }


def _merge_query(url: str, extra: dict[str, str]) -> str:
    parts = urlsplit((url or "").strip())
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    for k, v in extra.items():
        if v:
            q[k] = v
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, urlencode(q), parts.fragment))


def _newsapi_pack_from_body(body: dict[str, Any], *, n: int) -> tuple[list[dict[str, Any]], str]:
    articles = body.get("articles")
    if not isinstance(articles, list) or not articles:
        return [], "no_articles"
    normed: list[dict[str, Any]] = []
    for art in articles:
        if not isinstance(art, dict):
            continue
        row = _normalize_newsapi_article(art)
        if not row["title"] or not row["url"]:
            continue
        if not _news_text_ai_relevant(row["title"], row["description"]):
            continue
        normed.append(row)
    normed = normed[:n]
    if not normed:
        return [], "no_ai_articles"
    return normed, "newsapi_ok"


def sync_newsapi_top_headlines(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """NewsAPI v2（优先 everything；top-headlines 空结果时自动回退）。"""
    n = CONNECTOR_HEAT_TOP_N
    raw_url = (url or "").strip() or NEWSAPI_TOP_HEADLINES_DEFAULT
    h = {**headers, "Accept": "application/json", "User-Agent": headers.get("User-Agent") or "AiTrends-NewsAPI/1.0"}
    urls_to_try: list[str] = [_merge_query(raw_url, {"pageSize": str(max(n, 20))})]
    low = raw_url.lower()
    if "top-headlines" in low and NEWSAPI_TOP_HEADLINES_DEFAULT not in urls_to_try:
        urls_to_try.append(_merge_query(NEWSAPI_TOP_HEADLINES_DEFAULT, {"pageSize": str(max(n, 20))}))
    last_code, last_text = 0, ""
    last_note = ""
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            for api_url in urls_to_try:
                r = client.get(api_url, headers=h)
                last_code = int(r.status_code or 0)
                last_text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
                if last_code < 200 or last_code >= 300:
                    continue
                try:
                    body = json.loads(last_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(body, dict):
                    continue
                normed, last_note = _newsapi_pack_from_body(body, n=n)
                if normed:
                    pack = {
                        "connector_sync_items_v1": [
                            {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in normed
                        ],
                        "note": "newsapi_everything" if "everything" in api_url else "newsapi_v2",
                    }
                    return 200, _trim_pack_json(pack)
            if last_code and 200 <= last_code < 300:
                return 200, json.dumps(
                    {"connector_sync_items_v1": [], "note": last_note or "no_articles"},
                    ensure_ascii=False,
                )
            return last_code or 0, last_text
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def sync_thenewsapi_top_news(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """TheNewsAPI v1/news/top（或 all）→ AI/tech Top N。"""
    n = CONNECTOR_HEAT_TOP_N
    raw_url = (url or "").strip() or THENEWSAPI_TOP_DEFAULT
    api_url = _merge_query(raw_url, {"limit": str(max(n, 10))})
    h = {**headers, "Accept": "application/json", "User-Agent": headers.get("User-Agent") or "AiTrends-TheNewsAPI/1.0"}
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            r = client.get(api_url, headers=h)
            text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
            if r.status_code < 200 or r.status_code >= 300:
                return r.status_code, text
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                return r.status_code, text
            if not isinstance(body, dict):
                return r.status_code, json.dumps({"connector_sync_items_v1": [], "note": "not_object"}, ensure_ascii=False)
            data = body.get("data")
            flat: list[dict[str, Any]] = []
            if isinstance(data, list):
                flat = [x for x in data if isinstance(x, dict)]
            elif isinstance(data, dict):
                for _cat, rows in data.items():
                    if isinstance(rows, list):
                        flat.extend([x for x in rows if isinstance(x, dict)])
            if not flat:
                return 200, json.dumps({"connector_sync_items_v1": [], "note": "no_data"}, ensure_ascii=False)
            normed: list[dict[str, Any]] = []
            for art in flat:
                row = _normalize_thenewsapi_article(art)
                if not row["title"] or not row["url"]:
                    continue
                if not _news_text_ai_relevant(row["title"], row["description"]):
                    continue
                normed.append(row)
            try:
                normed.sort(
                    key=lambda x: float(x.get("relevance_score") or 0),
                    reverse=True,
                )
            except (TypeError, ValueError):
                pass
            normed = normed[:n]
            if not normed:
                return 200, json.dumps({"connector_sync_items_v1": [], "note": "no_ai_articles"}, ensure_ascii=False)
            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in normed
                ],
                "note": "thenewsapi_top",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def _hn_normalize_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """单条 story → 入库 snippet 形状（含 objectID、points、链接与正文节选）。"""
    link = (hit.get("url") or hit.get("story_url") or "").strip()
    if not link and hit.get("objectID"):
        link = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
    text = (hit.get("story_text") or hit.get("comment_text") or "").strip()
    return {
        "objectID": hit.get("objectID"),
        "title": hit.get("title") or hit.get("story_title") or "",
        "url": link,
        "points": hit.get("points"),
        "num_comments": hit.get("num_comments"),
        "author": hit.get("author"),
        "created_at": hit.get("created_at"),
        "story_text": text[:8000] if text else "",
    }


def sync_hacker_news_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """Algolia HN API：首页热门（``tags=front_page``），按 points 取 Top N 逐条入库。"""
    n = CONNECTOR_HEAT_TOP_N
    raw_url = (url or "").strip() or HN_ALGOLIA_SEARCH_DEFAULT
    parts = urlsplit(raw_url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q.setdefault("tags", "front_page")
    try:
        lim = int(str(q.get("hitsPerPage") or "0").strip() or "0")
    except ValueError:
        lim = 0
    q["hitsPerPage"] = str(max(n, lim, 30))
    api_url = urlunsplit(
        (
            parts.scheme or "https",
            parts.netloc or "hn.algolia.com",
            parts.path or "/api/v1/search",
            urlencode(q),
            "",
        )
    )
    h = {**headers, "Accept": "application/json", "User-Agent": headers.get("User-Agent") or "AiTrends-HN/1.0"}
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            r = client.get(api_url, headers=h)
            text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
            if r.status_code < 200 or r.status_code >= 300:
                return r.status_code, text
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                return r.status_code, text
            if not isinstance(body, dict):
                return r.status_code, json.dumps({"connector_sync_items_v1": [], "note": "not_object"}, ensure_ascii=False)
            hits = body.get("hits")
            if not isinstance(hits, list) or not hits:
                return 200, json.dumps({"connector_sync_items_v1": [], "note": "no_hits"}, ensure_ascii=False)

            def _score(item: dict[str, Any]) -> int:
                try:
                    return int(item.get("points") or 0)
                except (TypeError, ValueError):
                    return 0

            ranked = sorted([x for x in hits if isinstance(x, dict)], key=_score, reverse=True)[:n]
            payloads = [_hn_normalize_hit(x) for x in ranked if (x.get("title") or "").strip()]
            if not payloads:
                return 200, json.dumps({"connector_sync_items_v1": [], "note": "no_titled_hits"}, ensure_ascii=False)
            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in payloads
                ],
                "note": "hn_algolia_front_page",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def sync_huggingface_spaces_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """GET 列表 JSON，按 trendingScore（次按 likes）取前 N，再 GET 每条 ``/api/spaces/{id}`` 详情。

    与 HF 邮件/官网「本周热门」一致：优先近期热度，而非历史累计点赞榜。
    """
    n = CONNECTOR_HEAT_TOP_N
    list_url, _ = _hf_list_pool_limit(url)
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(list_url, headers=headers)
            text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
            if r.status_code < 200 or r.status_code >= 300:
                return r.status_code, text
            try:
                arr = json.loads(text)
            except Exception:
                return r.status_code, text
            if not isinstance(arr, list) or not arr:
                return r.status_code, json.dumps({"connector_sync_items_v1": [], "note": "not_a_list"}, ensure_ascii=False)

            def score(it: dict[str, Any]) -> tuple[int, int]:
                try:
                    ts = int(it.get("trendingScore") or 0)
                except (TypeError, ValueError):
                    ts = 0
                try:
                    likes = int(it.get("likes") or 0)
                except (TypeError, ValueError):
                    likes = 0
                return (ts, likes)

            ranked = sorted([x for x in arr if isinstance(x, dict)], key=score, reverse=True)[:n]
            base = f"{urlsplit(list_url).scheme}://{urlsplit(list_url).netloc}".rstrip("/")
            payloads: list[dict[str, Any]] = []
            for it in ranked:
                sid = str(it.get("id") or "").strip()
                if not sid:
                    continue
                detail_url = f"{base}/api/spaces/{sid}"
                r2 = client.get(detail_url, headers=headers)
                if r2.status_code < 200 or r2.status_code >= 300:
                    continue
                try:
                    one = json.loads(r2.text or "{}")
                except Exception:
                    continue
                if isinstance(one, dict):
                    payloads.append(one)

            if not payloads:
                return r.status_code, json.dumps({"connector_sync_items_v1": [], "note": "detail_fetch_empty"}, ensure_ascii=False)

            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in payloads
                ],
                "note": "hf_trending_score_top",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


ARXIV_API_QUERY_DEFAULT = (
    "https://export.arxiv.org/api/query?"
    "search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL&"
    "sortBy=lastUpdatedDate&sortOrder=descending&max_results=80"
)
_ARXIV_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def arxiv_api_is_query_url(url: str) -> bool:
    """arXiv Atom API（``export.arxiv.org/api/query``）。"""
    p = urlsplit((url or "").strip().lower())
    return "export.arxiv.org" in (p.netloc or "") and "/api/query" in (p.path or "")


def _arxiv_collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _arxiv_id_from_atom_id(id_text: str) -> str:
    s = (id_text or "").strip()
    if "/abs/" in s:
        return s.split("/abs/", 1)[-1].strip("/").split("?")[0][:64]
    return s[-64:] if s else ""


def parse_arxiv_atom_entries(xml_text: str, *, limit: int = CONNECTOR_HEAT_TOP_N) -> list[dict[str, Any]]:
    """解析 arXiv Atom feed → 逐条入库 JSON（含 arxiv_id、摘要、作者与链接）。"""
    if not (xml_text or "").strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", _ARXIV_ATOM_NS):
        id_el = entry.find("a:id", _ARXIV_ATOM_NS)
        arxiv_id = _arxiv_id_from_atom_id(id_el.text if id_el is not None else "")
        title_el = entry.find("a:title", _ARXIV_ATOM_NS)
        title = _arxiv_collapse_ws(title_el.text if title_el is not None else "")
        if not title or not arxiv_id:
            continue
        summary_el = entry.find("a:summary", _ARXIV_ATOM_NS)
        summary = _arxiv_collapse_ws(summary_el.text if summary_el is not None else "")[:12_000]
        published_el = entry.find("a:published", _ARXIV_ATOM_NS)
        updated_el = entry.find("a:updated", _ARXIV_ATOM_NS)
        authors: list[str] = []
        for author in entry.findall("a:author", _ARXIV_ATOM_NS):
            name_el = author.find("a:name", _ARXIV_ATOM_NS)
            if name_el is not None and (name_el.text or "").strip():
                authors.append(_arxiv_collapse_ws(name_el.text or ""))
        abs_url = ""
        pdf_url = ""
        for link in entry.findall("a:link", _ARXIV_ATOM_NS):
            href = (link.get("href") or "").strip()
            if not href:
                continue
            rel = (link.get("rel") or "").strip().lower()
            typ = (link.get("type") or "").strip().lower()
            if rel == "alternate" or (not pdf_url and "abs" in href):
                abs_url = abs_url or href
            if typ == "application/pdf" or href.endswith(".pdf"):
                pdf_url = pdf_url or href
        if not abs_url:
            abs_url = f"https://arxiv.org/abs/{arxiv_id}"
        cats: list[str] = []
        for cat in entry.findall("a:category", _ARXIV_ATOM_NS):
            term = (cat.get("term") or "").strip()
            if term:
                cats.append(term)
        out.append(
            {
                "arxiv_id": arxiv_id,
                "id": arxiv_id,
                "title": title,
                "summary": summary,
                "authors": authors[:24],
                "published": (published_el.text or "").strip() if published_el is not None else "",
                "updated": (updated_el.text or "").strip() if updated_el is not None else "",
                "abs_url": abs_url,
                "pdf_url": pdf_url,
                "categories": cats[:12],
            }
        )
        if len(out) >= limit:
            break
    return out


def sync_arxiv_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """arXiv Atom API：cs.AI/LG/CL 最近更新，取前 N 篇打包入库。"""
    n = CONNECTOR_HEAT_TOP_N
    raw_url = (url or "").strip() or ARXIV_API_QUERY_DEFAULT
    parts = urlsplit(raw_url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    try:
        lim = int(str(q.get("max_results") or "0").strip() or "0")
    except ValueError:
        lim = 0
    q["max_results"] = str(max(n, lim, 30))
    api_url = urlunsplit(
        (
            parts.scheme or "http",
            parts.netloc or "export.arxiv.org",
            parts.path or "/api/query",
            urlencode(q),
            "",
        )
    )
    h = {
        **headers,
        "Accept": "application/atom+xml,application/xml,text/xml",
        "User-Agent": headers.get("User-Agent") or "AiTrends-Arxiv/1.0",
    }
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            r = client.get(api_url, headers=h)
            if r.status_code == 429:
                time.sleep(3.0)
                r = client.get(api_url, headers=h)
            text = (r.text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
            if r.status_code < 200 or r.status_code >= 300:
                return r.status_code, text
            payloads = parse_arxiv_atom_entries(text, limit=n)
            if not payloads:
                return 200, json.dumps({"connector_sync_items_v1": [], "note": "no_entries"}, ensure_ascii=False)
            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(p, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for p in payloads
                ],
                "note": "arxiv_atom_cs_ai_lg_cl",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def _taaft_title_for_slug(html: str, slug: str) -> str:
    base = f"https://theresanaiforthat.com/ai/{slug}"
    for pat in (
        rf'href="{re.escape(base)}/?"[^>]*title="([^"]{{2,160}})"',
        rf'title="([^"]{{2,160}})"[^>]*href="{re.escape(base)}/?"',
        rf'href="{re.escape(base)}/?"[^>]*>([^<]{{2,120}})</a>',
    ):
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            t = re.sub(r"\s+", " ", m.group(1)).strip()
            if len(t) >= 2 and t.lower() not in ("ai", "new"):
                return t
    return slug.replace("-", " ").strip().title()


def _parse_taaft_listing_html(html: str, *, limit: int) -> list[dict[str, Any]]:
    """从 TAAFT /new/ HTML 解析工具卡片（需 curl_cffi 拉取）。"""
    if not (html or "").strip():
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"https://theresanaiforthat\.com/ai/([a-z0-9-]+)/?", html, flags=re.IGNORECASE):
        slug = (m.group(1) or "").strip().lower()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        page_url = f"https://theresanaiforthat.com/ai/{slug}/"
        title = _taaft_title_for_slug(html, slug)
        desc = (
            f"{title} — new on There's An AI For That (/new/). "
            f"Listing: {page_url}. For indie devs tracking AI tools to clone or monetize."
        )
        out.append(
            {
                "source": "taaft",
                "name": title[:200],
                "slug": slug[:120],
                "url": page_url,
                "listing_url": page_url,
                "description": desc[:1200],
            }
        )
        if len(out) >= limit:
            break
    return out


def sync_taaft_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """TAAFT 新工具列表页 → Top N 工具卡片 JSON。"""
    n = CONNECTOR_HEAT_TOP_N
    list_url = (url or "").strip() or TAAFT_NEW_DEFAULT
    try:
        code, text = _http_get_text(list_url, headers, timeout=60.0)
        if code < 200 or code >= 300:
            return code, (text or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
        items = _parse_taaft_listing_html(text or "", limit=n)
        if not items:
            return 200, json.dumps(
                {"connector_sync_items_v1": [], "note": "taaft_parse_empty"},
                ensure_ascii=False,
            )
        pack = {
            "connector_sync_items_v1": [
                {"snippet": json.dumps(it, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for it in items
            ],
            "note": "taaft_new_list",
        }
        return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def _parse_money_usd(text: str) -> float | None:
    s = (text or "").lower().replace(",", "")
    m = re.search(r"\$?\s*([\d.]+)\s*([km])?", s)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    suf = (m.group(2) or "").lower()
    if suf == "k":
        val *= 1000
    elif suf == "m":
        val *= 1_000_000
    return val


def _acquire_v1_search(
    client: httpx.Client,
    *,
    operation: str,
    params: dict[str, Any],
    headers: dict[str, str],
) -> list[dict[str, Any]]:
    api_url = ACQUIRE_SEARCH_API_DEFAULT
    body = {
        "data": {
            operation: params,
            "__meta": {
                "referrer": "https://acquire.com/",
                "cookie": _ACQUIRE_SEARCH_META_COOKIE,
            },
        }
    }
    h = {
        **headers,
        "Content-Type": "application/json",
        "Origin": "https://acquire.com",
        "Referer": "https://acquire.com/",
        "User-Agent": headers.get("User-Agent") or _BROWSER_UA,
    }
    r = client.post(api_url, headers=h, json=body)
    if r.status_code < 200 or r.status_code >= 300:
        return []
    try:
        payload = r.json()
    except Exception:
        return []
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        return []
    rows = result.get(operation)
    return [x for x in rows if isinstance(x, dict)] if isinstance(rows, list) else []


def _acquire_row_is_ai(row: dict[str, Any]) -> bool:
    blob = f"{row.get('type') or ''} {row.get('listingHeadline') or ''}".lower()
    return "ai" in blob or "artificial intelligence" in blob or "machine learning" in blob


def _parse_acquire_api_rows(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """MicroAcquire v1-search 匿名列表 → 连接器 snippet。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if len(out) >= limit:
            break
        if not _acquire_row_is_ai(row):
            continue
        link = str(row.get("link") or "").strip()
        if not link or link in seen:
            continue
        seen.add(link)
        headline = re.sub(r"\s+", " ", str(row.get("listingHeadline") or "")).strip()
        if len(headline) < 4:
            continue
        asking = row.get("askingPrice")
        try:
            ask_usd = float(asking) if asking is not None else None
        except (TypeError, ValueError):
            ask_usd = None
        out.append(
            {
                "source": "acquire",
                "name": headline[:200],
                "url": link[:2048],
                "asking_price_usd": ask_usd,
                "arr_usd": ask_usd,
                "type": str(row.get("type") or "AI")[:64],
                "location": str(row.get("location") or "")[:120],
                "category": "AI",
            }
        )
    return out


def sync_acquire_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """Acquire：MicroAcquire 公开 v1-search（anonTopPicks + anonStartupsByCategory）。"""
    n = CONNECTOR_HEAT_TOP_N
    try:
        with httpx.Client(timeout=45.0, follow_redirects=True) as client:
            merged: list[dict[str, Any]] = []
            for op, params in (
                ("anonTopPicks", {"type": "saas", "advisory": False}),
                ("anonStartupsByCategory", {"category": "ai"}),
            ):
                merged.extend(_acquire_v1_search(client, operation=op, params=params, headers=headers))
            items = _parse_acquire_api_rows(merged, limit=n)
            if not items:
                return 200, json.dumps(
                    {"connector_sync_items_v1": [], "note": "acquire_parse_empty"},
                    ensure_ascii=False,
                )
            pack = {
                "connector_sync_items_v1": [
                    {"snippet": json.dumps(it, ensure_ascii=False)[:_PER_ITEM_SNIPPET_MAX]} for it in items
                ],
                "note": "acquire_v1_search_ai",
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]
