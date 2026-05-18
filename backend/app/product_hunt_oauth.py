"""Product Hunt API v2：用 Developer OAuth client_id + client_secret 换取 Bearer access_token。"""
from __future__ import annotations

import json

import httpx

PH_OAUTH_TOKEN_URL = "https://api.producthunt.com/v2/oauth/token"


def fetch_product_hunt_client_credentials_token(*, client_id: str, client_secret: str) -> str:
    """``grant_type=client_credentials`` → access_token（公开读榜单等）。"""
    cid = (client_id or "").strip()
    sec = (client_secret or "").strip()
    if not cid or not sec:
        raise ValueError("product_hunt client_id 与 client_secret 均不能为空")
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            PH_OAUTH_TOKEN_URL,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json={
                "client_id": cid,
                "client_secret": sec,
                "grant_type": "client_credentials",
            },
        )
    if r.status_code < 200 or r.status_code >= 300:
        body = (r.text or "")[:800]
        raise RuntimeError(f"Product Hunt OAuth token HTTP {r.status_code}: {body}")
    try:
        data = json.loads(r.text or "{}")
    except json.JSONDecodeError as e:
        raise RuntimeError("Product Hunt OAuth token 响应非 JSON") from e
    if not isinstance(data, dict):
        raise RuntimeError("Product Hunt OAuth token 响应格式异常")
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"Product Hunt OAuth 未返回 access_token: {data!s}"[:400])
    return token


def resolve_product_hunt_bearer(*, api_key: str, oauth_client_secret: str) -> tuple[str, str]:
    """
    解析同步/测试用的 Bearer。

    - 填了 **APP Secret**（oauth_client_secret）：将 API Key 视为 **client_id**，与 Secret 走 OAuth 换 token
      （Product Hunt 开发者后台常见填法）。
    - 仅 API Key：视为已是 **access_token**，直接 Bearer。
    返回 (bearer_token, mode) 其中 mode 为 ``oauth_exchange`` 或 ``direct_bearer``。
    """
    key = (api_key or "").strip()
    secret = (oauth_client_secret or "").strip()
    if secret:
        if not key:
            raise ValueError("product_hunt 已填 APP Secret 时，API Key 须为 Developer 应用的 client_id")
        return fetch_product_hunt_client_credentials_token(client_id=key, client_secret=secret), "oauth_exchange"
    if key:
        return key, "direct_bearer"
    raise ValueError("product_hunt 需要 API Key（access_token 或 client_id）或同时填写 API Key + APP Secret")
