"""同步诊断日志：仅保留关键 info 与 warn/error。"""
from backend.app.sync_diagnostic_log import should_persist_diagnostic


def test_should_persist_diagnostic_errors_and_warnings():
    assert should_persist_diagnostic(level="error", step="http_fail")
    assert should_persist_diagnostic(level="warn", step="skip_score")


def test_should_persist_diagnostic_key_info_only():
    assert should_persist_diagnostic(level="info", step="batch_start")
    assert should_persist_diagnostic(level="info", step="connector_done")
    assert not should_persist_diagnostic(level="info", step="http_done")
    assert not should_persist_diagnostic(level="info", step="pack_items")
    assert not should_persist_diagnostic(level="info", step="article_ok")
