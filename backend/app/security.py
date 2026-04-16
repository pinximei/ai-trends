from __future__ import annotations

import hashlib
import hmac
import os
import time
import json
import base64
from typing import Any

from fastapi import HTTPException, Request


JWT_SECRET = os.getenv("AISOU_JWT_SECRET", "change-this-jwt-secret")
JWT_TTL_SECONDS = int(os.getenv("AISOU_JWT_TTL_SECONDS", "1800"))
SIGNING_KEY = os.getenv("AISOU_SIGNING_KEY", "change-this-signing-key")
AUTH_BOOTSTRAP_KEY = os.getenv("AISOU_AUTH_BOOTSTRAP_KEY", "dev-bootstrap-key")
ALLOWED_SKEW_SECONDS = int(os.getenv("AISOU_ALLOWED_SKEW_SECONDS", "300"))
REQUIRE_HTTPS = os.getenv("AISOU_REQUIRE_HTTPS", "true").lower() in {"1", "true", "yes", "on"}
ALLOW_INSECURE_LOCALHOST = os.getenv("AISOU_ALLOW_INSECURE_LOCALHOST", "true").lower() in {"1", "true", "yes", "on"}
APP_ENV = os.getenv("AISOU_ENV", "dev").lower()

if APP_ENV not in {"dev", "local"}:
    weak_defaults = {
        "change-this-jwt-secret",
        "change-this-signing-key",
        "dev-bootstrap-key",
    }
    if JWT_SECRET in weak_defaults or SIGNING_KEY in weak_defaults or AUTH_BOOTSTRAP_KEY in weak_defaults:
        raise RuntimeError("weak security defaults are not allowed outside dev/local")


def issue_access_token(client_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": client_id,
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
        "scope": "api:read api:write",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def verify_access_token(token: str) -> dict[str, Any]:
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    expected = hmac.new(JWT_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(payload_raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="token expired")
    return payload


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(method: str, path: str, query: str, ts: str, body: bytes) -> str:
    return "\n".join([method.upper(), path, query, ts, _sha256_hex(body)])


def verify_hmac_signature(request: Request, body: bytes) -> None:
    ts = request.headers.get("x-ts", "")
    sig = request.headers.get("x-signature", "")
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="missing signature headers")
    try:
        ts_value = int(ts)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid timestamp") from exc

    now = int(time.time())
    if abs(now - ts_value) > ALLOWED_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="timestamp out of range")

    canonical = _canonical(
        request.method,
        request.url.path,
        request.url.query,
        ts,
        body,
    )
    expected = hmac.new(SIGNING_KEY.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="bad request signature")


def verify_bearer_from_request(request: Request) -> dict[str, Any]:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    return verify_access_token(token)


def enforce_https(request: Request) -> None:
    if not REQUIRE_HTTPS:
        return

    host = (request.url.hostname or "").lower()
    if ALLOW_INSECURE_LOCALHOST and host in {"127.0.0.1", "localhost", "::1"}:
        return

    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    request_proto = (request.url.scheme or "").lower()
    if forwarded_proto == "https" or request_proto == "https":
        return

    raise HTTPException(status_code=400, detail="https required")
