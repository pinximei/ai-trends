"""飞书群机器人 Webhook：推送每日精选摘要。"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def send_feishu_text(webhook_url: str, text: str) -> None:
    url = (webhook_url or "").strip()
    if not url or not url.startswith("https://"):
        raise RuntimeError("飞书 Webhook URL 无效")
    payload = {"msg_type": "text", "content": {"text": (text or "").strip()[:4000]}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"飞书 HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"飞书请求失败: {e}") from e
    try:
        data: dict[str, Any] = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        raise RuntimeError(f"飞书响应非 JSON: {raw[:200]}") from e
    code = data.get("code", data.get("StatusCode"))
    if code not in (0, "0", None) and int(code or 0) != 0:
        raise RuntimeError(f"飞书返回错误: {data.get('msg') or data.get('StatusMessage') or raw[:200]}")


def send_daily_digest_feishu(*, webhook_url: str, text: str) -> None:
    """发送已排版好的飞书正文（由 newsletter_digest_format 生成）。"""
    send_feishu_text(webhook_url, text)
