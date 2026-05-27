"""连接器入库 / LLM 润色失败根因诊断。"""
from backend.app.connector_ingest_diagnostics import (
    diagnose_polish_failure,
    explain_polish_error,
    format_fetch_empty_message,
)
from backend.app.polish_publish_compat import coerce_polish_output
from backend.app.sync_diagnostic_log import should_persist_diagnostic
from tests.replication_fixtures import sample_replication_analysis


def test_should_persist_diagnostic_errors_only():
    assert should_persist_diagnostic(level="error", step="http_fail")
    assert not should_persist_diagnostic(level="info", step="connector_done")


def test_diagnose_tab_summary_short_with_data():
    data = {
        "feed_kind": "apps",
        "title": "t",
        "summary": "x" * 40,
        "tabs": [
            {"label": "描述", "summary": "a" * 80, "body_md": "b" * 200},
            {"label": "复刻评估", "summary": "c" * 37, "body_md": "d" * 200},
            {"label": "数据支撑", "summary": "e" * 20, "body_md": "f" * 80},
        ],
    }
    msg = diagnose_polish_failure(
        data,
        "tab_复刻评估_summary_short len=37 need>=52",
        admin_source_key="product_hunt",
        phase="first_pass",
    )
    assert "根因=" in msg
    assert "37" in msg and "52" in msg
    assert "实测 Tab" in msg
    assert "差 15 字" in msg


def test_diagnose_replication_analysis_invalid():
    msg = diagnose_polish_failure(
        {"feed_kind": "apps", "replication_analysis": {"verdict": "观望"}},
        "replication_analysis_invalid:tier_rationale=0字(需≥20)",
        admin_source_key="github",
    )
    assert "replication_analysis" in msg
    assert "tier_rationale" in msg


def test_coerce_maps_legacy_highlight_tab():
    raw = {
        "feed_kind": "apps",
        "categories": ["高价值复刻"],
        "tabs": [
            {"label": "描述", "summary": "s" * 80, "body_md": "b" * 130},
            {"label": "复刻评估", "summary": "r" * 60, "body_md": "x" * 200},
            {"label": "功能亮点", "summary": "h" * 20, "body_md": "y" * 80},
        ],
        "replication_analysis": sample_replication_analysis(worth=8, verdict="高价值"),
    }
    out = coerce_polish_output(raw)
    labels = [t["label"] for t in out["tabs"]]
    assert "数据支撑" in labels
    assert "功能亮点" not in labels


def test_explain_polish_error_json_parse():
    msg = explain_polish_error("json_parse_failed raw_preview='not json'")
    assert "JSON 解析失败" in msg


def test_format_fetch_empty_product_hunt():
    msg = format_fetch_empty_message("pack_items=0 note=no_posts", source_key="product_hunt")
    assert "no_posts" in msg or "无上榜" in msg
