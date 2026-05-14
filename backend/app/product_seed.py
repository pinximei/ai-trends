"""Seed demo data for product_* tables."""
from __future__ import annotations

import json
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
    SoftwareDownload,
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

    def _tabs_json(pairs: list[tuple[str, str, str]]) -> str:
        return json.dumps(
            [{"label": a, "summary": b, "body_md": c} for a, b, c in pairs],
            ensure_ascii=False,
        )

    articles = [
        Article(
            slug="weekly-models",
            title="大模型赛道：本周指标速览",
            summary="基于公开 API 聚合的演示数据。",
            body="## 总览\n\n演示稿结构与线上 LLM 入库一致：多分 tab 展示。",
            segment_id=segs[0].id,
            industry_id=ind.id,
            content_type="third_party_derived",
            third_party_source="hacker_news / 演示数据源",
            source_external_id="demo-hn-object-1",
            status="published",
            published_at=datetime.utcnow(),
            feed_kind="news",
            ai_categories_json='["大模型"]',
            ai_tabs_json=_tabs_json(
                [
                    ("要点速览", "本周大模型指标与趋势提要。", "## 本周要点\n\n- 演示指标曲线\n- 可替换为连接器同步结果"),
                    ("口径说明", "数据来源与免责声明。", "## 口径\n\n基于公开 API 演示聚合，非投资建议。"),
                ]
            ),
        ),
        Article(
            slug="app-landscape",
            title="AI 应用观察（演示）",
            summary="应用板块资源示例。",
            body="## 总览\n\n应用类演示：双 tab 结构与正式稿一致。",
            segment_id=segs[1].id,
            industry_id=ind.id,
            content_type="application",
            third_party_source="huggingface_spaces / 演示数据源",
            source_external_id="demo-hf-app-landscape",
            status="published",
            published_at=datetime.utcnow(),
            feed_kind="apps",
            ai_categories_json='["应用产品"]',
            ai_tabs_json=_tabs_json(
                [
                    ("产品动态", "应用与上新线索。", "## 动态\n\n**应用**类文章需标注第三方来源（演示）。"),
                    ("生态观察", "开源与托管演示相关提示。", "## 生态\n\n演示数据，线上由 LLM 按连接器片段重写。"),
                ]
            ),
        ),
        Article(
            slug="tool-picks",
            title="Spaces 应用演示（自营示例）",
            summary="Hugging Face Spaces 类可运行应用演示条目。",
            body="## 总览\n\n工具类演示条目。",
            segment_id=segs[2].id,
            industry_id=ind.id,
            content_type="self_tool",
            third_party_source="huggingface_spaces / 演示数据源",
            source_external_id="demo-hf-space",
            status="published",
            published_at=datetime.utcnow(),
            feed_kind="apps",
            ai_categories_json='["应用产品"]',
            ai_tabs_json=_tabs_json(
                [
                    ("应用形态", "Spaces / 低代码托管类应用提示。", "## 形态\n\n演示为 **应用发现** 泳道占位。"),
                    ("使用建议", "集成与版本注意点。", "## 建议\n\n演示环境，生产请接真实流水线。"),
                ]
            ),
        ),
    ]
    for a in articles:
        db.add(a)

    db.add(
        CmsPage(
            slug="about",
            title="关于本站与免责声明",
            body_md=(
                "## 网站介绍\n\nAiTrends 演示站：AI 行业趋势与资源聚合（学习项目）。\n\n"
                "## 数据与来源\n\n数据来自配置的第三方 API 与演示种子；热门推荐由系统按周期生成快照。\n\n"
                "## 免责声明\n\n信息仅供参考，不构成任何专业建议；使用需自担风险。"
            ),
            status="published",
            published_at=datetime.utcnow(),
        )
    )
    db.add(
        CmsPage(
            slug="about_en",
            title="About & disclaimer",
            body_md=(
                "## About\n\nAiTrends demo: AI industry trends and resource aggregation (learning project).\n\n"
                "## Data\n\nData comes from configured third-party APIs and demo seed; featured lists are rebuilt on a schedule.\n\n"
                "## Disclaimer\n\nFor information only; not professional advice. Use at your own risk."
            ),
            status="published",
            published_at=datetime.utcnow(),
        )
    )

    db.commit()


def ensure_demo_software_downloads(db: Session) -> None:
    """演示环境写入若干 iOS/Android 下载占位，便于联调分类筛选。"""
    if db.scalar(select(SoftwareDownload.id).limit(1)):
        return
    rows = [
        SoftwareDownload(
            title="AiTrends 雷达（演示 iOS）",
            summary="占位：替换为实际 App Store 链接后可上架。",
            platform="ios",
            category_slug="ai_radar",
            category_label="行业雷达",
            store_url="https://apps.apple.com/",
            sort_order=20,
            status="published",
        ),
        SoftwareDownload(
            title="AiTrends 雷达（演示 Android）",
            summary="占位：替换为 Google Play 或 APK 分发地址。",
            platform="android",
            category_slug="ai_radar",
            category_label="行业雷达",
            store_url="https://play.google.com/store",
            sort_order=19,
            status="published",
        ),
        SoftwareDownload(
            title="AI 助手壳（演示 iOS）",
            summary="应用类型示例：对话 / Agent。",
            platform="ios",
            category_slug="ai_assistant",
            category_label="AI 助手",
            store_url="https://apps.apple.com/",
            sort_order=12,
            status="published",
        ),
        SoftwareDownload(
            title="AI 助手壳（演示 Android）",
            summary="与 iOS 同类型，便于批量生成时按类型归类。",
            platform="android",
            category_slug="ai_assistant",
            category_label="AI 助手",
            store_url="https://play.google.com/store",
            sort_order=11,
            status="published",
        ),
        SoftwareDownload(
            title="端侧推理工具（演示 Android）",
            summary="应用类型示例：工具链。",
            platform="android",
            category_slug="devtools",
            category_label="开发工具",
            store_url="https://play.google.com/store",
            sort_order=8,
            status="published",
        ),
    ]
    for r in rows:
        db.add(r)
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
    if not db.get(ProductSetting, "llm"):
        db.add(
            ProductSetting(
                key="llm",
                value_json={
                    "provider": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                    "api_key": "",
                },
            )
        )
    if not db.scalar(select(ProductConnector.id).where(ProductConnector.provider_name == "demo").limit(1)):
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
    from .runtime_settings_service import ensure_runtime_settings_row
    from .scheduler_settings_service import ensure_scheduler_settings_row

    ensure_runtime_settings_row(db)
    ensure_scheduler_settings_row(db)
    from .newsletter_settings_service import ensure_newsletter_settings_row

    ensure_newsletter_settings_row(db)


def ensure_public_about_page(db: Session) -> None:
    """生产环境若未跑演示种子，仍保证「关于」页有默认 CMS，避免 /pages/about 404。"""
    if not db.get(CmsPage, "about"):
        db.add(
            CmsPage(
                slug="about",
                title="关于本站与免责声明",
                body_md=(
                    "## 网站介绍\n\nAiTrends：AI 行业趋势与资源聚合（学习项目）。\n\n"
                    "## 数据与来源\n\n数据来自配置的第三方 API 与运营录入；热门推荐由系统按周期生成快照。\n\n"
                    "## 免责声明\n\n信息仅供参考，不构成任何专业建议；使用需自担风险。"
                ),
                status="published",
                published_at=datetime.utcnow(),
            )
        )
    if not db.get(CmsPage, "about_en"):
        db.add(
            CmsPage(
                slug="about_en",
                title="About & disclaimer",
                body_md=(
                    "## About\n\nAiTrends: AI industry trends and resource aggregation (learning project).\n\n"
                    "## Data\n\nData from configured third-party APIs and editorial input; featured lists are rebuilt on a schedule.\n\n"
                    "## Disclaimer\n\nFor information only; not professional advice. Use at your own risk."
                ),
                status="published",
                published_at=datetime.utcnow(),
            )
        )
    db.commit()
