"""Greenfield product schema (requirements Master v1)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
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
    __table_args__ = (
        Index(
            "ix_product_articles_public_feed",
            "industry_id",
            "status",
            "published_at",
            "id",
        ),
        Index(
            "ix_product_articles_public_feed_seg",
            "industry_id",
            "segment_id",
            "status",
            "published_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512))
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    segment_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_segments.id"), index=True)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_industries.id"), index=True)
    content_type: Mapped[str] = mapped_column(String(32), default="third_party_derived")
    third_party_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 连接器解析的主链接（GitHub 仓库页、HN 帖等）；详情 API 返回并在 tab 内补全可点击链接
    source_original_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # 本次 HTTP 同步对应 product_connector_logs.id（一次拉取一条日志，与入库改写稿对应）
    connector_sync_log_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 上游 JSON 中的条目主键（如 objectID、node_id），与 Article.id 并列可查
    source_external_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    # 连接器原始响应指纹，用于入库前去重（与标题无关）
    ingest_fingerprint: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # LLM 重写时给出的短标签类别 JSON 数组，例如 ["大模型","应用发布"]
    ai_categories_json: Mapped[str] = mapped_column(Text, default="[]")
    # LLM 生成的分 tab 结构：[{"label","summary","body_md"}, ...]，概要列在 tab 行，点击展示 body_md
    ai_tabs_json: Mapped[str] = mapped_column(Text, default="[]")
    # 公共站泳道：news=资讯、apps=应用（入库时由数据源决定，供筛选与统计）
    feed_kind: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    # LLM 可复刻性：S/A/B/C（S=高可复刻，C=低可复刻）
    replication_tier: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)
    # 应用泳道：复刻评估结构化 JSON（verdict、难度、工时、技术方案、开源支撑等）
    replication_analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    # 可更新热度（应用泳道按日列表内优先排序）；连接器入库与后台均可改写。
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
    # GitHub 等连接器重复同步时刷新：总 star、今日 star 增速（Trending 页解析）
    engagement_stars_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement_stars_today: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Product Hunt thumbnail / HF Space cardData.thumbnail 等封面图（公开站列表与详情）
    cover_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
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


class SoftwareDownload(Base):
    """客户端安装包 / 应用商店入口，按平台与业务类型分类，供批量上架脚本写入。"""

    __tablename__ = "product_software_downloads"
    __table_args__ = (Index("ix_product_sw_dl_public_list", "status", "platform", "category_slug", "sort_order", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(16), index=True)
    category_slug: Mapped[str] = mapped_column(String(64), index=True)
    category_label: Mapped[str] = mapped_column(String(128), default="")
    store_url: Mapped[str] = mapped_column(String(1024), default="")
    # 相对 backend/data 的包路径，例如 software_uploads/12/app.apk；有值时前台走本地下载而非外链
    artifact_rel_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    artifact_download_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    artifact_mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(16), default="published", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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


class ProductSyncDiagnosticLog(Base):
    """管理后台「同步日志」：记录拉取 / 入库各步骤，便于排查前台无数据。"""

    __tablename__ = "product_sync_diagnostic_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info")
    step: Mapped[str] = mapped_column(String(64), default="log")
    message: Mapped[str] = mapped_column(Text, default="")
    connector_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
