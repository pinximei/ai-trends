"""拉取 GitHub Trending 详情并经 LLM 整理，输出 Markdown 样例供人工核对。

用法:
  py -3.12 scripts/export_github_ai_sample.py
  py -3.12 scripts/export_github_ai_sample.py --input trending_detail_sample.json --max 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import SessionLocal  # noqa: E402
from backend.app.domain.articles import rule_value_score  # noqa: E402
from backend.app.llm_service import polish_connector_article  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default="trending_detail_sample.json")
    p.add_argument("--output", default="github_ai_sample.md")
    p.add_argument("--max", type=int, default=3, help="最多整理几条")
    args = p.parse_args()

    path = Path(args.input)
    if not path.is_file():
        print(f"FAIL: 缺少 {path}，请先运行 discover + fetch_details", file=sys.stderr)
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    repos = [r for r in (data.get("repos") or []) if isinstance(r, dict)][: max(1, args.max)]

    lines: list[str] = [
        "# GitHub Trending → AI 整理样例",
        "",
        f"来源文件: `{path.name}`，共展示 **{len(repos)}** 条（经 DeepSeek 润色）。",
        "",
        "---",
        "",
    ]

    db = SessionLocal()
    try:
        for i, repo in enumerate(repos, 1):
            slug = repo.get("full_name") or "?"
            snippet = json.dumps(repo, ensure_ascii=False)
            tr = repo.get("_aisoul_trending") or {}
            stars_today = repo.get("trending_stars_today") or tr.get("stars_today")
            desc = (repo.get("description") or "")[:500]
            stars = repo.get("stargazers_count")
            url = repo.get("html_url") or f"https://github.com/{slug}"

            vs = rule_value_score(
                snippet=snippet,
                summary=desc,
                http_status=200,
            )

            lines.append(f"## {i}. {slug}")
            lines.append("")
            lines.append("| 字段 | 值 |")
            lines.append("|------|-----|")
            lines.append(f"| 仓库链接 | {url} |")
            lines.append(f"| 今日 star 增速 | {stars_today or '—'} |")
            lines.append(f"| 总 star | {stars} |")
            lines.append(f"| 规则价值分 | {vs:.0f} |")
            lines.append(f"| 简介（API） | {desc or '—'} |")
            lines.append("")

            polished, polish_err = polish_connector_article(
                db,
                snippet=snippet[:32000],
                connector_name="GitHub Trending 拉取",
                admin_source_key="github",
                segment_label="AI｜通用·开源协作",
                rule_title=f"GitHub Trending · {slug}",
                rule_summary=desc[:512],
                value_score=vs,
                ref_id=f"sample-{i}",
                feed_kind="news",
            )

            if not polished:
                lines.append(f"> **LLM 润色失败**（{polish_err or 'unknown'}；线上同步时该条也不会入库）")
                lines.append("")
                continue

            title = (polished.get("title") or "").strip()
            summary = (polished.get("summary") or "").strip()
            body = (polished.get("body_md") or "").strip()
            tabs = polished.get("tabs") or []

            lines.append("### AI 标题")
            lines.append("")
            lines.append(title)
            lines.append("")
            lines.append("### AI 摘要")
            lines.append("")
            lines.append(summary)
            lines.append("")
            lines.append("### AI 正文（Markdown）")
            lines.append("")
            lines.append(body[:4000] if body else "（空）")
            if tabs:
                lines.append("")
                lines.append("### 附加 Tab")
                for t in tabs[:2]:
                    if isinstance(t, dict) and t.get("label"):
                        lines.append(f"\n#### {t.get('label')}\n")
                        lines.append((t.get("body_md") or "")[:1500])
            lines.append("")
            lines.append("---")
            lines.append("")
    finally:
        db.close()

    out = Path(args.output)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: 已写入 {out.resolve()} ({len(repos)} 条)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
