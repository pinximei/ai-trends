from __future__ import annotations

from typing import Any


def success(data: Any) -> dict[str, Any]:
    """对外 JSON 统一信封（code / message / data）。"""
    return {"code": 0, "message": "ok", "data": data}


def failure(message: str, *, code: int = 1, data: Any | None = None) -> dict[str, Any]:
    """业务失败：HTTP 仍 200，code≠0，与前台 `publicPost`/`publicGet` 解析一致。"""
    return {"code": code, "message": message, "data": data if data is not None else {}}
