"""Seed demo data for product_* tables."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .product_models import (
    Article,
    CmsPage,
    Industry,
    MetricDefinition,
    MetricPoint,
    ProductConnector,
    ProductSetting,
    Segment,
)


def seed_product_if_empty(db: Session) -> None:
    if db.scalar(select(Industry.id).limit(1)):
        return

    ind = Industry(slug="ai", name="AI", enabled=True, sort_order=0)
    db.add(ind)
    db.flush()

    segs = [
        Segment(industry_id=ind.id, slug="models", name="大模型", sort_order=0, show_on_public=True),
        Segment(industry_id=ind.id, slug="apps", name="应用", sort_order=1, show_on_public=True),
        Segment(industry_id=ind.id, slug="tools", name="工具", sort_order=2, show_on_public=True),
    ]
    for s in segs:
        db.add(s)
    db.flush()

    metrics = [
        MetricDefinition(
            key="attention_index",
            name="关注度指数",
            unit="index",
            aggregation="mean",
            segment_id=segs[0].id,
            participates_in_anomaly=True,
            value_kind="absolute",
        ),
        MetricDefinition(
            key="app_active_growth",
            name="应用活跃增速",
            unit="%",
            aggregation="mean",
            segment_id=segs[1].id,
            participates_in_anomaly=True,
            value_kind="absolute",
        ),
        MetricDefinition(
            key="tool_mentions",
            name="工具提及量",
            unit="count",
            aggregation="sum",
            segment_id=segs[2].id,
            participates_in_anomaly=True,
            value_kind="absolute",
        ),
    ]
    for m in metrics:
        db.add(m)
    db.flush()

    now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    import math

    for mi, m in enumerate(metrics):
        base = 40.0 + mi * 10
        for d in range(30):
            t = now - timedelta(days=29 - d)
            v = base + 5 * math.sin(d / 5.0) + d * 0.2
            db.add(
                MetricPoint(
                    metric_id=m.id,
                    segment_id=m.segment_id,
                    bucket_start=t,
                    value=round(v, 4),
                    source_ref="demo_seed",
                )
            )

    articles = [
        Article(
            slug="weekly-models",
            title="大模型赛道：本周指标速览",
            summary="基于公开 API 聚合的演示数据。",
            body="## 摘要\n\n正文为演示内容，可替换为连接器同步结果。",
            segment_id=segs[0].id,
            industry_id=ind.id,
            content_type="third_party_derived",
            third_party_source="演示数据源",
            status="published",
            published_at=datetime.utcnow(),
        ),
        Article(
            slug="app-landscape",
            title="AI 应用观察（演示）",
            summary="应用板块资源示例。",
            body="## 说明\n\n**应用**类文章需标注第三方来源（演示）。",
            segment_id=segs[1].id,
            industry_id=ind.id,
            content_type="application",
            third_party_source="示例 API 提供方",
            status="published",
            published_at=datetime.utcnow(),
        ),
        Article(
            slug="tool-picks",
            title="工具链动态（自营示例）",
            summary="自营维护条目可不写第三方来源。",
            body="## 工具\n\n本页为 **自营工具** 类型演示。",
            segment_id=segs[2].id,
            industry_id=ind.id,
            content_type="self_tool",
            third_party_source=None,
            status="published",
            published_at=datetime.utcnow(),
        ),
    ]
    for a in articles:
        db.add(a)

    db.add(
        CmsPage(
            slug="about",
            title="关于本站与免责声明",
            body_md=(
                "## 网站介绍\n\nAISoul 演示站：AI 行业趋势与资源聚合（学习项目）。\n\n"
                "## 数据与来源\n\n数据来自配置的第三方 API 与演示种子；热门推荐由系统按周期生成快照。\n\n"
                "## 免责声明\n\n信息仅供参考，不构成任何专业建议；使用需自担风险。"
            ),
            status="published",
            published_at=datetime.utcnow(),
        )
    )

    db.commit()


def ensure_product_settings_and_demo_connector(db: Session) -> None:
    """已有库时补默认配置与演示连接器。"""
    if not db.get(ProductSetting, "hot"):
        db.add(
            ProductSetting(
                key="hot",
                value_json={
                    "top_n_trends": 5,
                    "top_n_articles": 10,
                    "llm_model": "rule-based",
                },
            )
        )
    if not db.get(ProductSetting, "anomaly"):
        db.add(
            ProductSetting(
                key="anomaly",
                value_json={
                    "short_window_days": 7,
                    "baseline_days": 28,
                    "l1_z": 3.0,
                    "l2_z": 4.0,
                    "cooldown_hours": 48,
                    "board_k": 2,
                },
            )
        )
    if not db.scalar(select(ProductConnector.id).limit(1)):
        db.add(
            ProductConnector(
                name="演示连接器",
                provider_name="demo",
                type="api",
                config_json={"url": "https://httpbin.org/get", "method": "GET", "note": "同步时拉取探测 URL，演示用"},
                enabled=False,
                min_interval_seconds=3600,
            )
        )
    db.commit()
