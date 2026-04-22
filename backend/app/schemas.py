from typing import Literal

from pydantic import BaseModel, Field


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
    frequency: str = "daily_07:00"
    api_base: str = ""
    api_key: str = ""
    notes: str = ""
    scope_label: str = ""
    # 多条领域/板块；提交时优先于单字段 scope_label。
    scope_labels: list[str] = Field(default_factory=list)


class AdminSourceTestRequest(BaseModel):
    """测试数据源 HTTP 可达性：已入库用 source；未入库用 api_base。api_key 仅本次请求使用，不落库。"""

    source: str | None = None
    api_base: str | None = None
    api_key: str = ""
    # GitLab REST 使用 PRIVATE-TOKEN；多数 OAuth 使用 Bearer；
    # 部分开放平台需要把 key 放在 query 参数里（如 ?token=xxx / ?apiKey=xxx / ?key=xxx）。
    auth_mode: Literal["bearer", "private_token", "query_key"] = "bearer"
    key_param: str = "key"


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
