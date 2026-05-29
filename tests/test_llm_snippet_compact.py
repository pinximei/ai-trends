"""LLM 片段压缩：送模型前去掉 API 噪声、保留编辑字段。"""
from __future__ import annotations

import json

from backend.app.llm_snippet_compact import compact_snippet_for_llm


def test_github_compact_drops_noise_and_caps_readme() -> None:
    raw = {
        "name": "demo",
        "full_name": "org/demo",
        "description": "A tool",
        "html_url": "https://github.com/org/demo",
        "stargazers_count": 1200,
        "node_id": "MDEwOlJlcG9zaXRvcnk=",
        "followers_url": "https://api.github.com/users/x/followers",
        "readme_md": "x" * 10_000,
        "license": {"spdx_id": "MIT"},
    }
    out = compact_snippet_for_llm(json.dumps(raw), admin_source_key="github")
    data = json.loads(out)
    assert data["full_name"] == "org/demo"
    assert "node_id" not in out
    assert "followers_url" not in out
    assert len(data["readme_md"]) <= 4_001


def test_product_hunt_compact_keeps_core_fields() -> None:
    raw = {
        "name": "Acme",
        "tagline": "Ship faster",
        "votesCount": 99,
        "gravatar_id": "deadbeef",
        "internal_meta": {"x": 1},
    }
    out = compact_snippet_for_llm(json.dumps(raw), admin_source_key="product_hunt")
    data = json.loads(out)
    assert data["name"] == "Acme"
    assert data["votesCount"] == 99
    assert "gravatar" not in out.lower()


def test_non_json_snippet_passes_through_truncated() -> None:
    plain = "plain text " * 500
    out = compact_snippet_for_llm(plain, admin_source_key="github")
    assert out.startswith("plain text")
    assert len(out) <= 10_240
