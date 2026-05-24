"""飞书 Webhook 推送（mock HTTP）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.newsletter_feishu import _md_to_feishu_lines, send_feishu_text


def test_md_to_feishu_lines_strips_markdown() -> None:
    out = _md_to_feishu_lines("## 标题\n\n**加粗**与`代码`")
    assert "标题" in out
    assert "**" not in out


def test_send_feishu_text_rejects_bad_url() -> None:
    with pytest.raises(RuntimeError, match="Webhook"):
        send_feishu_text("http://bad.example/hook", "hi")


@patch("backend.app.newsletter_feishu.urllib.request.urlopen")
def test_send_feishu_text_ok(mock_urlopen: MagicMock) -> None:
    resp = MagicMock()
    resp.read.return_value = b'{"code":0,"msg":"success"}'
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp
    send_feishu_text("https://open.feishu.cn/open-apis/bot/v2/hook/xxx", "hello")
    mock_urlopen.assert_called_once()
