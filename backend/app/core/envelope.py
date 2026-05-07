from __future__ import annotations

from typing import Any


def success(data: Any) -> dict[str, Any]:
    """对外 JSON 统一信封（code / message / data）。"""
    return {"code": 0, "message": "ok", "data": data}
