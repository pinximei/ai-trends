"""Product Hunt OAuth 解析（mock HTTP，无真实密钥）。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.product_hunt_oauth import (
    fetch_product_hunt_client_credentials_token,
    resolve_product_hunt_bearer,
)


def test_resolve_direct_bearer_when_no_secret() -> None:
    token, mode = resolve_product_hunt_bearer(api_key="already-a-token", oauth_client_secret="")
    assert token == "already-a-token"
    assert mode == "direct_bearer"


def test_resolve_oauth_exchange_when_secret_present() -> None:
    def fake_post(url, **kwargs):
        assert kwargs["json"]["grant_type"] == "client_credentials"
        assert kwargs["json"]["client_id"] == "cid"
        assert kwargs["json"]["client_secret"] == "sec"
        r = MagicMock()
        r.status_code = 200
        r.text = json.dumps({"access_token": "new-bearer", "token_type": "bearer"})
        return r

    with patch("backend.app.product_hunt_oauth.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post = fake_post
        token, mode = resolve_product_hunt_bearer(api_key="cid", oauth_client_secret="sec")
    assert token == "new-bearer"
    assert mode == "oauth_exchange"


def test_fetch_token_http_error() -> None:
    def fake_post(url, **kwargs):
        r = MagicMock()
        r.status_code = 401
        r.text = '{"error":"invalid_client"}'
        return r

    with patch("backend.app.product_hunt_oauth.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post = fake_post
        with pytest.raises(RuntimeError, match="401"):
            fetch_product_hunt_client_credentials_token(client_id="x", client_secret="y")
