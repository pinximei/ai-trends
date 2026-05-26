"""文本展示：乱码修复与 Markdown 卡片摘要。"""
from backend.app.text_display import (
    format_connector_snippet_plain,
    is_degraded_data_tab_body,
    markdown_to_plain_preview,
    prepare_detail_data_tab_body,
    repair_utf8_mojibake,
)
from backend.app.domain.articles import build_connector_data_tab_markdown


def test_markdown_table_to_plain_preview() -> None:
    raw = "| 指标 | 数值 |\n| --- | --- |\n| Star | 1200 |\n| 主语言 | Python |"
    out = markdown_to_plain_preview(raw, max_len=200)
    assert "|" not in out
    assert "Star" in out
    assert "1200" in out


def test_format_github_snippet_plain() -> None:
    snippet = '{"full_name":"org/repo","stargazers_count":99,"language":"Go","description":"A tool"}'
    out = format_connector_snippet_plain(snippet, admin_source_key="github")
    assert "org/repo" in out
    assert "99" in out
    assert "{" not in out


def test_build_connector_data_tab_markdown() -> None:
    snippet = '{"full_name":"o/r","stargazers_count":10,"language":"Rust"}'
    md = build_connector_data_tab_markdown("github", snippet)
    assert "| 指标 | 内容 |" in md
    assert "o/r" in md
    assert "10" in md


def test_repair_utf8_mojibake_roundtrip() -> None:
    good = "中文摘要"
    broken = good.encode("utf-8").decode("latin-1")
    assert repair_utf8_mojibake(good) == good
    assert repair_utf8_mojibake(broken) == good


def test_prepare_detail_data_tab_from_mixed_junk() -> None:
    junk = (
        "full_name: org/repo\n"
        "stargazers_count: 99\n"
        "language: Go\n"
        "| 字段 | 内容 |\n"
        "| --- | --- |\n"
        "| 指标 | 数值 |\n"
    )
    assert is_degraded_data_tab_body(junk)
    md = prepare_detail_data_tab_body(junk, admin_source_key="github")
    assert "| 指标 | 内容 |" in md
    assert "org/repo" in md
    assert "99" in md
    assert "full_name:" not in md


def test_prepare_detail_data_tab_from_json_block() -> None:
    body = '```json\n{"full_name":"a/b","stargazers_count":5}\n```'
    md = prepare_detail_data_tab_body(body, admin_source_key="github")
    assert "a/b" in md
    assert "```" not in md
