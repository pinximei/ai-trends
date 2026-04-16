from typing import Literal

from pydantic import BaseModel


class RemovalRequestCreate(BaseModel):
    requester_contact: str
    target_signal_id: str
    reason: str
    request_type: str = "correction"


class InternalRunRequest(BaseModel):
    idempotency_key: str
    job_type: str


class AdminSourceConfigUpsert(BaseModel):
    source: str
    enabled: bool = True
    frequency: str = "daily"
    api_base: str = ""
    api_key: str = ""
    notes: str = ""


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminResolveRequest(BaseModel):
    note: str = ""


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: Literal["viewer", "operator", "admin"] = "viewer"
    enabled: bool = True


class AdminUserUpdate(BaseModel):
    role: Literal["viewer", "operator", "admin"] | None = None
    enabled: bool | None = None
    password: str | None = None


class AdminSettingsUpdate(BaseModel):
    password_min_length: int = 10
    lock_minutes: int = 15
    max_failed_attempts: int = 5


class AdminChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class TrendOpsUpdate(BaseModel):
    lifecycle_stage: str | None = None
    trend_score: float | None = None


class SignalOpsUpdate(BaseModel):
    status: str | None = None
