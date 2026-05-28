"""文本展示：乱码修复与 Markdown 卡片摘要。"""
from backend.app.text_display import (
    format_connector_snippet_plain,
    is_degraded_data_tab_body,
    markdown_to_plain_preview,
    normalize_article_tabs_for_display,
    prepare_data_tab_body,
    prepare_description_tab_body,
    prepare_detail_data_tab_body,
    repair_utf8_mojibake,
    tab_text_role_from_label,
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


def test_tab_text_role_maps_wire_display_to_data() -> None:
    assert tab_text_role_from_label("数据支撑") == "data"
    assert tab_text_role_from_label("要点") == "data"
    assert tab_text_role_from_label("描述") == "description"


def test_normalize_article_tabs_news_wire_junk() -> None:
    tabs = [
        {
            "label": "描述",
            "summary": "事件概述与影响分析。" * 3,
            "body_md": "## 描述\n\ntitle: Breaking news\n\n一段中文说明。",
        },
        {
            "label": "数据支撑",
            "summary": "| 字段 | 内容 |",
            "body_md": (
                "url: https://example.com/a\n"
                "title: Headline\n"
                "| 字段 | 内容 |\n| --- | --- |\n"
                "| 指标 | 数值 |\n"
            ),
        },
    ]
    out = normalize_article_tabs_for_display(
        tabs,
        admin_source_key="newsapi",
        source_original_url="https://example.com/a",
    )
    assert len(out) == 2
    data = next(t for t in out if t["label"] == "数据支撑")
    assert "url:" not in data["body_md"]
    assert "| 指标 | 内容 |" in data["body_md"]
    assert "Headline" in data["body_md"] or "example.com" in data["body_md"]
    desc = next(t for t in out if t["label"] == "描述")
    assert "title:" not in desc["body_md"]
    assert "一段中文说明" in desc["body_md"]


def test_prepare_description_strips_connector_snapshot() -> None:
    raw = "## 连接器同步快照\n\nfoo: bar\n\n## 描述\n\n正常段落。"
    md = prepare_description_tab_body(raw)
    assert "连接器同步快照" not in md
    assert "foo:" not in md
    assert "正常段落" in md


def test_strip_inline_github_api_json_from_description() -> None:
    snippet = (
        '{"id": 1, "node_id": "R_kg", "name": "MoneyPrinterTurbo", '
        '"full_name": "harry0703/MoneyPrinterTurbo", "private": false, '
        '"html_url": "https://github.com/harry0703/MoneyPrinterTurbo", '
        '"stargazers_count": 61700, "language": "Python", '
        '"owner": {"login": "harry0703", "html_url": "https://github.com/harry0703"}}'
    )
    raw = (
        "MoneyPrinterTurbo 是开源 AI 短视频生成工具，支持多模型与 Web 界面。\n\n"
        f"{snippet}\n"
    )
    md = prepare_description_tab_body(raw, admin_source_key="github")
    assert "node_id" not in md
    assert "followers_url" not in md
    assert "MoneyPrinterTurbo" in md
    assert "开源" in md or "短视频" in md


def test_prepare_data_tab_rebuilds_from_inline_github_json() -> None:
    snippet = (
        '{"full_name":"harry0703/MoneyPrinterTurbo","stargazers_count":61700,'
        '"language":"Python","html_url":"https://github.com/harry0703/MoneyPrinterTurbo",'
        '"description":"Auto video generator"}'
    )
    body = f"| 指标 | 内容 |\n| --- | --- |\n| 原始 | {snippet} |\n"
    md = prepare_data_tab_body(body, admin_source_key="github")
    assert "| 指标 | 内容 |" in md
    assert "harry0703/MoneyPrinterTurbo" in md
    assert "61700" in md
    assert "node_id" not in md
