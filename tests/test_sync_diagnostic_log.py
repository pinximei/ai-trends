"""同步诊断日志：仅保留 error。"""
from backend.app.sync_diagnostic_log import should_persist_diagnostic


def test_should_persist_diagnostic_errors_only():
    assert should_persist_diagnostic(level="error", step="http_fail")
    assert not should_persist_diagnostic(level="warn", step="skip_score")
    assert not should_persist_diagnostic(level="info", step="batch_start")
    assert not should_persist_diagnostic(level="info", step="connector_done")
