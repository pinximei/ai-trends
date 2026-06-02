"""连接器入库诊断文案（无递归）。"""
from __future__ import annotations

from backend.app.connector_ingest_diagnostics import (
    _diagnose_polish_err_only,
    diagnose_polish_failure,
    explain_polish_reject,
)


def test_diagnose_polish_failure_no_recursion_when_only_polish_err() -> None:
    msg = diagnose_polish_failure(
        None,
        "",
        admin_source_key="product_hunt",
        polish_err="validate_failed: empty_title_or_summary title=False",
    )
    assert "递归" not in msg
    assert "润色校验" in msg or "empty_title" in msg


def test_explain_polish_reject_validate_failed() -> None:
    msg = explain_polish_reject("validate_failed: tab_描述_body_short len=10")
    assert msg
    assert "递归" not in msg


def test_diagnose_polish_err_only_no_recursion() -> None:
    msg = _diagnose_polish_err_only("validate_failed: foo", admin_source_key="github")
    assert "foo" in msg
    assert "递归" not in msg
