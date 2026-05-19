"""连接器两阶段取数：先按热度取前 N 条，再逐条拉详情，打包为 ``connector_sync_items_v1`` 供入库。"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .domain.articles import CONNECTOR_HEAT_TOP_N, CONNECTOR_SNIPPET_MAX_CHARS

PH_GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"
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
        out.append({"full_name": slug, "stars_today": stars_today, "rank": len(out) + 1})
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
            ranked = parse_github_trending_repos(r.text or "", limit=n)
            if not ranked:
                return r.status_code, json.dumps(
                    {"connector_sync_items_v1": [], "note": "trending_parse_empty", "since": since},
                    ensure_ascii=False,
                )
            payloads: list[dict[str, Any]] = []
            for row in ranked:
                slug = str(row.get("full_name") or "").strip()
                if not slug:
                    continue
                api_url = f"https://api.github.com/repos/{slug}"
                r2 = client.get(api_url, headers=api_headers)
                if r2.status_code < 200 or r2.status_code >= 300:
                    continue
                try:
                    repo = json.loads(r2.text or "{}")
                except json.JSONDecodeError:
                    continue
                if not isinstance(repo, dict):
                    continue
                extra: dict[str, Any] = {"since": since, "rank": row.get("rank"), "discovery_url": url}
                if row.get("stars_today") is not None:
                    extra["stars_today"] = row["stars_today"]
                repo["_aisoul_trending"] = extra
                if row.get("stars_today") is not None:
                    repo["trending_stars_today"] = row["stars_today"]
                payloads.append(repo)
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


def sync_product_hunt_top_details(headers: dict[str, str]) -> tuple[int, str]:
    """posts(order: RANKING) 取热度前 N，再对每个 slug 请求 ``post(slug:)`` 详情。"""
    n = CONNECTOR_HEAT_TOP_N
    list_q = (
        f"{{ posts(first: {n}, order: RANKING) {{ edges {{ node {{ id slug name tagline votesCount }} }} }} }}"
    )
    try:
        with httpx.Client(timeout=45.0) as client:
            code, body = _post_ph_graphql(client, headers, list_q)
            if not body or "errors" in body:
                err = json.dumps(body or {"errors": "empty"}, ensure_ascii=False)[:2000]
                return (code or 502, err)
            data = body.get("data") or {}
            posts = data.get("posts") or {}
            nodes: list[dict[str, Any]] = []
            for e in posts.get("edges") or []:
                if isinstance(e, dict) and isinstance(e.get("node"), dict):
                    nodes.append(e["node"])
            if not nodes:
                return code, json.dumps({"connector_sync_items_v1": [], "note": "no_posts"}, ensure_ascii=False)

            slugs: list[str] = []
            for node in nodes[:n]:
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
                ]
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]


def _hf_list_pool_limit(url: str) -> tuple[str, int]:
    """返回用于发现排序的列表 URL，并保证 limit 足够大以便客户端按 likes 截前 N。"""
    parts = urlsplit(url.strip() or "https://huggingface.co/api/spaces")
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
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


def sync_huggingface_spaces_top_details(url: str, headers: dict[str, str]) -> tuple[int, str]:
    """GET 列表 JSON，按 likes（次按 trendingScore）取前 N，再 GET 每条 ``/api/spaces/{id}`` 详情。"""
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
                    likes = int(it.get("likes") or 0)
                except (TypeError, ValueError):
                    likes = 0
                try:
                    ts = int(it.get("trendingScore") or 0)
                except (TypeError, ValueError):
                    ts = 0
                return (likes, ts)

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
                ]
            }
            return 200, _trim_pack_json(pack)
    except Exception as e:
        return 0, str(e)[:CONNECTOR_SNIPPET_MAX_CHARS]
