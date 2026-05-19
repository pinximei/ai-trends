"""从 GitHub Trending 页面解析「升星最快」仓库列表（今日/本周/本月 star 增速）。

用法（仓库根目录）:
  py -3.12 scripts/github_trending_discover.py
  py -3.12 scripts/github_trending_discover.py --since weekly --limit 25
  py -3.12 scripts/github_trending_discover.py -o trending_repos.json

环境变量（均可不配置）:
  GITHUB_TOKEN / GITHUB_API_KEY — 可选；Trending 页与公开仓库 REST API 无需 Token 即可访问。

下一步用详情脚本:
  py -3.12 scripts/github_trending_fetch_details.py -i trending_repos.json -o repos_detail.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.connector_heat_fetch import (  # noqa: E402
    GITHUB_TRENDING_DEFAULT,
    _github_trending_since,
    parse_github_trending_repos,
)


def _build_url(since: str) -> str:
    since = (since or "daily").strip().lower()
    if since not in {"daily", "weekly", "monthly"}:
        since = "daily"
    return f"https://github.com/trending?since={since}"


def discover(*, since: str, limit: int, token: str | None) -> dict:
    url = _build_url(since)
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "AiTrends-GitHubTrendingDiscover/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        rows = parse_github_trending_repos(r.text or "", limit=limit)

    repos = []
    for row in rows:
        slug = str(row.get("full_name") or "").strip()
        if not slug:
            continue
        repos.append(
            {
                "full_name": slug,
                "rank": row.get("rank"),
                "stars_today": row.get("stars_today"),
                "html_url": f"https://github.com/{slug}",
            }
        )

    return {
        "since": _github_trending_since(url),
        "discovery_url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": len(repos),
        "repos": repos,
    }


def main() -> int:
    import os

    p = argparse.ArgumentParser(description="解析 GitHub Trending 页面，输出升星榜单仓库列表 JSON")
    p.add_argument("--since", choices=["daily", "weekly", "monthly"], default="daily", help="日/周/月榜")
    p.add_argument("--limit", type=int, default=10, help="最多解析条数（默认 10）")
    p.add_argument("-o", "--output", help="写入 JSON 文件；省略则打印到 stdout")
    p.add_argument("--url", default="", help=f"完整 Trending URL（默认按 since 生成，同 {GITHUB_TRENDING_DEFAULT}）")
    args = p.parse_args()

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_API_KEY") or "").strip() or None
    limit = max(1, min(int(args.limit), 50))

    try:
        if args.url.strip():
            import httpx as _hx

            headers = {
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "AiTrends-GitHubTrendingDiscover/1.0",
            }
            if token:
                headers["Authorization"] = f"Bearer {token}"
            with _hx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.get(args.url.strip(), headers=headers)
                r.raise_for_status()
                rows = parse_github_trending_repos(r.text or "", limit=limit)
            payload = {
                "since": _github_trending_since(args.url.strip()),
                "discovery_url": args.url.strip(),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "count": len(rows),
                "repos": [
                    {
                        "full_name": row["full_name"],
                        "rank": row.get("rank"),
                        "stars_today": row.get("stars_today"),
                        "html_url": f"https://github.com/{row['full_name']}",
                    }
                    for row in rows
                ],
            }
        else:
            payload = discover(since=args.since, limit=limit, token=token)
    except httpx.HTTPStatusError as e:
        print(f"FAIL: HTTP {e.response.status_code} {e.request.url}", file=sys.stderr)
        print((e.response.text or "")[:500], file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"OK: 已写入 {args.output}（{payload['count']} 个仓库）")
    else:
        print(text)
    return 0 if payload["count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
