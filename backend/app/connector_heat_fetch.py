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
                _attach_github_readme(client, api_url, api_headers, repo)
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


HN_ALGOLIA_SEARCH_DEFAULT = "https://hn.algolia.com/api/v1/search?tags=front_page"


def hacker_news_algolia_is_search_url(url: str) -> bool:
    """Algolia HN Search API（列表发现）；非 ``firebaseio.com`` 单条 item API。"""
    p = urlsplit((url or "").strip().lower())
    return "hn.algolia.com" in (p.netloc or "") and "/api/" in (p.path or "")


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


ARXIV_API_QUERY_DEFAULT = (
    "http://export.arxiv.org/api/query?"
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
