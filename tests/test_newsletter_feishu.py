"""飞书 Webhook 推送（mock HTTP）。"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.newsletter_feishu import send_daily_digest_feishu, send_feishu_text


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


@patch("backend.app.newsletter_feishu.time.sleep")
@patch("backend.app.newsletter_feishu.urllib.request.urlopen")
def test_send_feishu_text_retries_on_rate_limit(mock_urlopen: MagicMock, _sleep: MagicMock) -> None:
    limited = MagicMock()
    limited.read.return_value = b'{"code":9499,"msg":"frequency limited psm test"}'
    limited.__enter__ = lambda s: limited
    limited.__exit__ = MagicMock(return_value=False)
    ok = MagicMock()
    ok.read.return_value = b'{"code":0,"msg":"success"}'
    ok.__enter__ = lambda s: ok
    ok.__exit__ = MagicMock(return_value=False)
    mock_urlopen.side_effect = [limited, ok]
    send_feishu_text(
        "https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        "hello",
        retry_delays_s=(0,),
    )
    assert mock_urlopen.call_count == 2


@patch("backend.app.newsletter_feishu.urllib.request.urlopen")
def test_send_daily_digest_feishu(mock_urlopen: MagicMock) -> None:
    resp = MagicMock()
    resp.read.return_value = b'{"code":0}'
    resp.__enter__ = lambda s: resp
    resp.__exit__ = MagicMock(return_value=False)
    mock_urlopen.return_value = resp
    send_daily_digest_feishu(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
        text="📬 结构化正文",
    )
    mock_urlopen.assert_called_once()
