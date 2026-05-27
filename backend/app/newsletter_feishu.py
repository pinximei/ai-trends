"""飞书群机器人 Webhook：推送每日精选摘要。"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# 飞书群机器人常见限流文案；定时 9:00 与其它系统撞车时需退避重试。
_FEISHU_RATE_LIMIT_MARKERS = ("frequency limited", "rate limit", "too many request", "请求过于频繁")
_DEFAULT_RETRY_DELAYS_S = (45, 120, 300)


def _is_feishu_rate_limited(err: BaseException) -> bool:
    msg = str(err).lower()
    return any(m in msg for m in _FEISHU_RATE_LIMIT_MARKERS)


def send_feishu_text(webhook_url: str, text: str, *, retry_delays_s: tuple[int, ...] = _DEFAULT_RETRY_DELAYS_S) -> None:
    url = (webhook_url or "").strip()
    if not url or not url.startswith("https://"):
        raise RuntimeError("飞书 Webhook URL 无效")
    payload = {"msg_type": "text", "content": {"text": (text or "").strip()[:4000]}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    delays = list(retry_delays_s)
    attempt = 0
    while True:
        attempt += 1
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
            err = RuntimeError(f"飞书 HTTP {e.code}: {detail}")
            if _is_feishu_rate_limited(err) and delays:
                wait = delays.pop(0)
                logger.warning("feishu rate limited (HTTP), retry in %ss (attempt %s)", wait, attempt)
                time.sleep(wait)
                continue
            raise err from e
        except urllib.error.URLError as e:
            err = RuntimeError(f"飞书请求失败: {e}")
            if _is_feishu_rate_limited(err) and delays:
                wait = delays.pop(0)
                logger.warning("feishu rate limited (network), retry in %ss (attempt %s)", wait, attempt)
                time.sleep(wait)
                continue
            raise err from e
        try:
            data: dict[str, Any] = json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            raise RuntimeError(f"飞书响应非 JSON: {raw[:200]}") from e
        code = data.get("code", data.get("StatusCode"))
        if code not in (0, "0", None) and int(code or 0) != 0:
            msg = str(data.get("msg") or data.get("StatusMessage") or raw[:200])
            err = RuntimeError(f"飞书返回错误: {msg}")
            if _is_feishu_rate_limited(err) and delays:
                wait = delays.pop(0)
                logger.warning("feishu rate limited (api), retry in %ss (attempt %s): %s", wait, attempt, msg[:120])
                time.sleep(wait)
                continue
            raise err
        return


def send_daily_digest_feishu(*, webhook_url: str, text: str) -> None:
    """发送已排版好的飞书正文（由 newsletter_digest_format 生成）。"""
    send_feishu_text(webhook_url, text)
