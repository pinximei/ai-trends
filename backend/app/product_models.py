"""Greenfield product schema (requirements Master v1)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import JSON as SAJSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# JSON：默认 PostgreSQL；若显式使用 SQLite 连接串，SQLAlchemy 2 同样支持 SAJSON
JSONType = SAJSON


class Industry(Base):
    __tablename__ = "product_industries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Segment(Base):
    __tablename__ = "product_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry_id: Mapped[int] = mapped_column(ForeignKey("product_industries.id"), index=True)
    slug: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    show_on_public: Mapped[bool] = mapped_column(Boolean, default=True)


class MetricDefinition(Base):
    __tablename__ = "product_metric_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    unit: Mapped[str] = mapped_column(String(32), default="")
    aggregation: Mapped[str] = mapped_column(String(32), default="mean")
    segment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_segments.id"), nullable=True)
    participates_in_anomaly: Mapped[bool] = mapped_column(Boolean, default=True)
    value_kind: Mapped[str] = mapped_column(String(16), default="absolute")


class MetricPoint(Base):
    __tablename__ = "product_metric_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_metric_definitions.id"), index=True)
    segment_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_segments.id"), index=True)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    value: Mapped[float] = mapped_column(Float)
    source_ref: Mapped[str] = mapped_column(String(256), default="")


class Article(Base):
    __tablename__ = "product_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    segment_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_segments.id"), index=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_industries.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(32), default="third_party_derived")
    third_party_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HotSnapshot(Base):
    __tablename__ = "product_hot_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_industries.id"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    payload_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), default="weekly_cron")


class CmsPage(Base):
    __tablename__ = "product_cms_pages"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    body_md: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LlmUsageLog(Base):
    __tablename__ = "product_llm_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ref_type: Mapped[str] = mapped_column(String(32), default="")
    ref_id: Mapped[str] = mapped_column(String(64), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Inspiration(Base):
    __tablename__ = "product_inspirations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_segments.id"), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class InspirationVersion(Base):
    __tablename__ = "product_inspiration_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inspiration_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_inspirations.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text, default="")
    context_snapshot_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_by_username: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductSetting(Base):
    """键值配置：hot / anomaly 等"""

    __tablename__ = "product_settings_kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductConnector(Base):
    __tablename__ = "product_connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    provider_name: Mapped[str] = mapped_column(String(128), default="")
    type: Mapped[str] = mapped_column(String(16), default="api")
    config_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    # 与 admin_source_configs.source 对应，同步时按该数据源的领域标签解析行业/板块。
    admin_source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProductConnectorLog(Base):
    __tablename__ = "product_connector_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_connectors.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    rows_ingested: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnomalyEvent(Base):
    __tablename__ = "product_anomaly_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_segments.id"), nullable=True, index=True)
    metric_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_metric_definitions.id"), nullable=True, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[int] = mapped_column(Integer, default=1, index=True)
    detail_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
