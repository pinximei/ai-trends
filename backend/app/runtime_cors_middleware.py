"""按库内 / 环境 CORS 白名单动态回显 Origin（替代启动时固定的 CORSMiddleware）。"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .runtime_settings_service import cors_allow_origins_list


class RuntimeCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origins = cors_allow_origins_list()
        origin = request.headers.get("origin")

        if request.method == "OPTIONS":
            resp = Response(status_code=204)
            if origin and origin in origins:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Credentials"] = "true"
                resp.headers["Access-Control-Allow-Methods"] = "*"
                req_headers = request.headers.get("access-control-request-headers")
                if req_headers:
                    resp.headers["Access-Control-Allow-Headers"] = req_headers
            return resp

        response = await call_next(request)
        if origin and origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
