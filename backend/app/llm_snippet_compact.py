"""连接器片段：入库指纹用完整 JSON，送 LLM 前压成「编辑用摘要」以省 token。"""
from __future__ import annotations

import json
import re
from typing import Any

from .domain.articles import CONNECTOR_LLM_SNIPPET_MAX_CHARS

# 单字段与 README 在摘要中的上限（不影响 CONNECTOR_SNIPPET_MAX_CHARS 存储）
_LLM_FIELD_STR_MAX = 1_200
# 送 LLM 的 readme 上限（须 ≤ connector _README_MD_MAX；过短会导致描述空洞）
_LLM_README_MAX = 12_000
_LLM_LIST_ITEMS_MAX = 12
_DROP_KEY_SUBSTR = (
    "gravatar",
    "avatar_url",
    "followers_url",
    "node_id",
    "organizations_url",
    "subscriptions_url",
    "received_events_url",
    "gists_url",
    "starred_url",
    "events_url",
    "badge_svg",
    "raw_url",
    "archive_url",
    "compare_url",
    "commits_url",
    "git_refs_url",
    "hooks_url",
    "issue_events_url",
    "keys_url",
    "merges_url",
    "milestones_url",
    "notifications_url",
    "pulls_url",
    "releases_url",
    "tags_url",
    "trees_url",
    "contributors_url",
    "languages_url",
    "stargazers_url",
    "subscribers_url",
    "subscription_url",
    "teams_url",
    "issue_comment_url",
    "comments_url",
)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _trim_str(val: Any, *, limit: int = _LLM_FIELD_STR_MAX) -> str:
    s = _collapse_ws(str(val)) if val is not None else ""
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _should_drop_key(key: str) -> bool:
    k = (key or "").lower()
    if k.startswith("_"):
        return True
    return any(sub in k for sub in _DROP_KEY_SUBSTR)


def _pick_dict(
    src: dict[str, Any],
    *,
    admin_source_key: str,
    depth: int = 0,
) -> dict[str, Any]:
    sk = (admin_source_key or "").strip().lower()
    out: dict[str, Any] = {}

    if sk == "github":
        allow = (
            "name",
            "full_name",
            "description",
            "html_url",
            "homepage",
            "language",
            "license",
            "topics",
            "stargazers_count",
            "forks_count",
            "open_issues_count",
            "default_branch",
            "created_at",
            "updated_at",
            "trending_stars_today",
            "readme_md",
            "_aisoul_trending",
        )
        for key in allow:
            if key not in src:
                continue
            v = src[key]
            if key == "readme_md":
                out[key] = _trim_str(v, limit=_LLM_README_MAX)
            elif key == "topics" and isinstance(v, list):
                out[key] = [str(x)[:40] for x in v[:20]]
            elif isinstance(v, (str, int, float, bool)) or v is None:
                out[key] = v if not isinstance(v, str) else _trim_str(v)
            elif isinstance(v, dict) and depth < 2:
                out[key] = _pick_dict(v, admin_source_key=sk, depth=depth + 1)
        return out

    if sk == "product_hunt":
        allow = (
            "name",
            "tagline",
            "description",
            "url",
            "website",
            "votesCount",
            "commentsCount",
            "createdAt",
            "featuredAt",
            "topics",
            "slug",
        )
        for key in allow:
            if key in src:
                out[key] = _trim_str(src[key]) if isinstance(src[key], str) else src[key]
        return out

    if sk in ("newsapi", "thenewsapi", "finnhub", "hacker_news", "arxiv", "youtube_data"):
        allow = (
            "title",
            "name",
            "description",
            "content",
            "url",
            "link",
            "publishedAt",
            "published_at",
            "source",
            "source_name",
            "author",
            "points",
            "num_comments",
            "objectID",
            "arxiv_id",
            "id",
        )
        for key in allow:
            if key in src:
                v = src[key]
                out[key] = _trim_str(v) if isinstance(v, str) else v
        return out

    # 通用：浅层保留标量与小对象，丢弃噪声键
    for key, val in list(src.items())[:80]:
        if _should_drop_key(key):
            continue
        if isinstance(val, str):
            out[key] = _trim_str(val)
        elif isinstance(val, (int, float, bool)) or val is None:
            out[key] = val
        elif isinstance(val, list) and depth < 2:
            slim: list[Any] = []
            for item in val[:_LLM_LIST_ITEMS_MAX]:
                if isinstance(item, dict):
                    slim.append(_pick_dict(item, admin_source_key=sk, depth=depth + 1))
                elif isinstance(item, str):
                    slim.append(_trim_str(item, limit=400))
                else:
                    slim.append(item)
            if slim:
                out[key] = slim
        elif isinstance(val, dict) and depth < 2:
            nested = _pick_dict(val, admin_source_key=sk, depth=depth + 1)
            if nested:
                out[key] = nested
    return out


def compact_snippet_for_llm(snippet: str, *, admin_source_key: str = "") -> str:
    """
    将连接器单条 JSON 压成 LLM 用摘要（无对话历史、无多轮上下文）。
    完整 ``snippet`` 仍用于指纹与 ``source_external_id`` 解析（见 article_ingest）。
    """
    s = (snippet or "").strip()
    if not s:
        return ""
    if not s.startswith("{") and not s.startswith("["):
        return s[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return s[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]

    if isinstance(data, dict):
        compact = _pick_dict(data, admin_source_key=admin_source_key)
        out = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        return out[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]

    if isinstance(data, list):
        items = []
        for row in data[:_LLM_LIST_ITEMS_MAX]:
            if isinstance(row, dict):
                items.append(_pick_dict(row, admin_source_key=admin_source_key))
            else:
                items.append(row)
        out = json.dumps(items, ensure_ascii=False, separators=(",", ":"))
        return out[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]

    return _trim_str(data)[:CONNECTOR_LLM_SNIPPET_MAX_CHARS]
