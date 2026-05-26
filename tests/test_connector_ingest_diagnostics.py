"""连接器入库失败原因中文说明。"""
from backend.app.connector_ingest_diagnostics import (
    explain_polish_error,
    explain_polish_reject,
    format_fetch_empty_message,
)
from backend.app.sync_diagnostic_log import should_persist_diagnostic


def test_should_persist_diagnostic_errors_only():
    assert should_persist_diagnostic(level="error", step="http_fail")
    assert not should_persist_diagnostic(level="warn", step="skip_score")
    assert not should_persist_diagnostic(level="info", step="connector_done")
    assert not should_persist_diagnostic(level="info", step="batch_start")


def test_explain_polish_reject_tab_summary_short():
    msg = explain_polish_reject(
        "tab_复刻评估_summary_short len=37 need>=52",
        admin_source_key="product_hunt",
    )
    assert "37" in msg
    assert "52" in msg
    assert "复刻评估" in msg


def test_explain_polish_error_no_key():
    assert "LLM API Key" in explain_polish_error("no_llm_key")


def test_format_fetch_empty_product_hunt():
    msg = format_fetch_empty_message("pack_items=0 note=no_posts", source_key="product_hunt")
    assert "no_posts" in msg or "无上榜" in msg
