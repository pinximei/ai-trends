"""根据 Trending 发现结果，调用 GitHub REST API 拉取各仓库详情。

用法（仓库根目录）:
  py -3.12 scripts/github_trending_discover.py -o trending_repos.json
  py -3.12 scripts/github_trending_fetch_details.py -i trending_repos.json -o repos_detail.json

或直接指定仓库（逗号分隔）:
  py -3.12 scripts/github_trending_fetch_details.py --repos microsoft/vscode,facebook/react

环境变量（可选，公开仓库不配 Token 即可；大批量时建议设置以免 API 限流）:
  GITHUB_TOKEN 或 GITHUB_API_KEY — Personal Access Token
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


def _api_headers(token: str | None) -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AiTrends-GitHubTrendingDetails/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        h["Authorization"] = f"Bearer {token.strip()}"
    return h


def _load_repos_from_input(path: str | None, repos_csv: str | None) -> list[dict]:
    if repos_csv:
        out = []
        for i, slug in enumerate(repos_csv.split(","), start=1):
            s = slug.strip().strip("/")
            if s and "/" in s:
                out.append({"full_name": s, "rank": i, "stars_today": None})
        return out

    if not path:
        raise ValueError("请提供 -i trending_repos.json 或 --repos owner/repo,...")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("repos"), list):
        return [x for x in data["repos"] if isinstance(x, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    raise ValueError("输入 JSON 需为 { repos: [...] } 或仓库对象数组")


def fetch_details(
    repo_rows: list[dict],
    *,
    token: str | None,
    include_readme: bool,
) -> dict:
    headers = _api_headers(token)
    results: list[dict] = []
    errors: list[dict] = []

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for row in repo_rows:
            slug = str(row.get("full_name") or "").strip().strip("/")
            if not slug or "/" not in slug:
                continue
            api_url = f"https://api.github.com/repos/{slug}"
            try:
                r = client.get(api_url, headers=headers)
                if r.status_code < 200 or r.status_code >= 300:
                    errors.append({"full_name": slug, "http_status": r.status_code, "body": (r.text or "")[:300]})
                    continue
                repo = r.json()
                if not isinstance(repo, dict):
                    continue
                if row.get("stars_today") is not None:
                    repo["trending_stars_today"] = row["stars_today"]
                repo["_aisoul_trending"] = {
                    "rank": row.get("rank"),
                    "stars_today": row.get("stars_today"),
                    "discovery_html_url": row.get("html_url"),
                }
                if include_readme:
                    rr = client.get(f"{api_url}/readme", headers={**headers, "Accept": "application/json"})
                    if 200 <= rr.status_code < 300:
                        try:
                            readme = rr.json()
                            if isinstance(readme, dict) and readme.get("content"):
                                repo["_readme_meta"] = {
                                    "name": readme.get("name"),
                                    "path": readme.get("path"),
                                    "size": readme.get("size"),
                                    "encoding": readme.get("encoding"),
                                }
                        except json.JSONDecodeError:
                            pass
                results.append(repo)
            except Exception as e:
                errors.append({"full_name": slug, "error": str(e)[:200]})

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count_ok": len(results),
        "count_error": len(errors),
        "repos": results,
        "errors": errors,
    }


def main() -> int:
    import os

    p = argparse.ArgumentParser(description="GitHub REST API 拉取 Trending 仓库详情")
    p.add_argument("-i", "--input", help="github_trending_discover.py 输出的 JSON")
    p.add_argument("--repos", help="逗号分隔 owner/repo，跳过发现步骤")
    p.add_argument("-o", "--output", help="详情 JSON 输出路径")
    p.add_argument("--readme", action="store_true", help="额外请求 /readme 元数据（不解码正文）")
    args = p.parse_args()

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_API_KEY") or "").strip() or None

    try:
        rows = _load_repos_from_input(args.input, args.repos)
        if not rows:
            print("FAIL: 无有效仓库条目", file=sys.stderr)
            return 1
        payload = fetch_details(rows, token=token, include_readme=args.readme)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"OK: 详情 {payload['count_ok']} 条，失败 {payload['count_error']} 条 → {args.output}")
    else:
        print(text)

    return 0 if payload["count_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
