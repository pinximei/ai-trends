"""GitHub 详情链接：入库与读时补全。"""
from __future__ import annotations

import json

from backend.app.domain import articles as art


def test_github_repo_url_prefers_full_name_over_issues_html_url() -> None:
    payload = json.dumps(
        {
            "full_name": "foo/bar",
            "html_url": "https://github.com/foo/bar/issues/99",
            "homepage": "https://bar.dev",
        },
        ensure_ascii=False,
    )
    rows = art.extract_connector_detail_link_rows("github", payload)
    labels = [r[0] for r in rows]
    urls = [r[1] for r in rows]
    assert "GitHub 仓库" in labels
    assert "https://github.com/foo/bar" in urls
    assert "https://bar.dev" in urls
    assert art.extract_connector_primary_url("github", payload) == "https://github.com/foo/bar"


def test_ensure_connector_links_in_polish_tabs_appends_markdown() -> None:
    tabs = [
        {"label": "描述", "summary": "x" * 80, "body_md": "正文"},
        {"label": "数据支撑", "summary": "短", "body_md": "| 指标 | 值 |\n| Star | 100 |"},
    ]
    snippet = json.dumps({"full_name": "org/demo", "homepage": "https://demo.app"}, ensure_ascii=False)
    art.ensure_connector_links_in_polish_tabs("github", snippet, tabs)
    body = tabs[1]["body_md"]
    assert "[GitHub 仓库](https://github.com/org/demo)" in body
    assert "[项目主页](https://demo.app)" in body


def test_enrich_published_tabs_with_source_url() -> None:
    tabs = [{"label": "数据支撑", "summary": "s", "body_md": "仅表格无链接"}]
    out = art.enrich_published_tabs_with_source_url(
        tabs,
        source_original_url="https://github.com/a/b",
        admin_source_key="github",
    )
    assert "[GitHub 仓库](https://github.com/a/b)" in out[0]["body_md"]
