"""应用复刻评估 JSON 解析与发布校验。"""
from __future__ import annotations

from backend.app.domain.replication_analysis import (
    FEED_CARD_TAB_REPLICATION,
    normalize_replication_analysis,
    validate_replication_analysis_for_publish,
)
from backend.app.domain.articles import required_feed_card_tab_labels, validate_llm_polish_for_publish
from tests.replication_fixtures import sample_ai_usage_steps, sample_market_position


def test_required_tabs_apps_includes_replication() -> None:
    assert required_feed_card_tab_labels("apps") == ("描述", FEED_CARD_TAB_REPLICATION, "数据支撑")
    assert required_feed_card_tab_labels("news") == ("描述", "数据支撑")


def test_normalize_and_validate_replication_analysis() -> None:
    raw = {
        "verdict": "值得复刻",
        "worth_score": 8,
        "difficulty": "中",
        "estimated_hours": {"mvp_min": 40, "mvp_max": 80, "prod_min": 200, "prod_max": 400},
        "tier_rationale": "产品边界清晰，可用 React + FastAPI 快速搭 MVP。",
        "value_summary": "面向独立开发者的订阅工具，有明确付费场景。",
        "tech_stack": ["React", "FastAPI", "PostgreSQL"],
        "implementation_plan": ["搭建鉴权", "实现核心列表 API", "接入支付"],
        "implementation_details": ["复用开源 admin 模板"],
        "open_source": {
            "has_support": True,
            "projects": [{"name": "refine", "url": "https://github.com/refinedev/refine", "role": "后台脚手架"}],
            "gaps": "支付与邮件需自研",
        },
        "risks": ["竞品多"],
        "market_position": sample_market_position(),
        "ai_usage_steps": sample_ai_usage_steps(),
    }
    norm = normalize_replication_analysis(raw)
    assert norm is not None
    assert validate_replication_analysis_for_publish(norm)


def test_validate_llm_polish_apps_three_tabs() -> None:
    repl = normalize_replication_analysis(
        {
            "verdict": "观望",
            "worth_score": 6,
            "difficulty": "高",
            "estimated_hours": {"mvp_min": 120, "mvp_max": 200, "prod_min": 500, "prod_max": 800},
            "tier_rationale": "依赖闭源大模型 API，复刻成本高但可做垂直细分。",
            "value_summary": "企业向工作流，客单价高但销售周期长。",
            "tech_stack": ["Next.js", "Python"],
            "implementation_plan": ["调研 API 配额"],
            "implementation_details": ["先做只读演示"],
            "open_source": {"has_support": False, "projects": [], "gaps": "核心推理无开源替代"},
            "risks": ["合规"],
            "market_position": sample_market_position(),
            "ai_usage_steps": sample_ai_usage_steps(),
        }
    )
    data = {
        "title": "示例 AI 写作助手",
        "summary": "面向创作者的写作助手，提供模板与多模型切换，适合独立开发者参考其产品形态、订阅设计与增长路径。",
        "body_md": "## 总览\n\n" + ("产品聚焦内容创作场景。" * 20),
        "categories": ["应用产品"],
        "feed_kind": "apps",
        "replication_tier": "B",
        "replication_analysis": repl,
        "tabs": [
            {
                "label": "描述",
                "summary": "写作助手面向自媒体与营销文案场景，解决从零起草慢的问题，提供模板库与风格预设。" * 2,
                "body_md": "## 产品\n\n" + ("支持多模型 API 路由。" * 30),
            },
            {
                "label": FEED_CARD_TAB_REPLICATION,
                "summary": "观望：可做垂直细分 MVP，但强依赖第三方模型 API 成本与合规；建议先验证付费意愿与获客渠道，再投入完整工程开发。（评估）",
                "body_md": "## 评估\n\n" + ("建议 120–200 小时做只读 MVP。" * 25),
            },
            {
                "label": "数据支撑",
                "summary": "定价与热度指标汇总，便于核对是否值得投入复刻。",
                "body_md": "| 指标 | 值 |\n| --- | --- |\n| 定价 | $19/月 |\n" + ("x" * 80),
            },
        ],
    }
    assert validate_llm_polish_for_publish(data, admin_source_key="product_hunt")


def test_validate_rejects_incomplete_market_position() -> None:
    raw = {
        "verdict": "值得复刻",
        "worth_score": 8,
        "difficulty": "中",
        "estimated_hours": {"mvp_min": 40, "mvp_max": 80, "prod_min": 200, "prod_max": 400},
        "tier_rationale": "产品边界清晰，可用 React + FastAPI 快速搭 MVP。",
        "value_summary": "面向独立开发者的订阅工具，有明确付费场景。",
        "tech_stack": ["React"],
        "implementation_plan": ["搭建鉴权"],
        "ai_usage_steps": sample_ai_usage_steps(),
    }
    norm = normalize_replication_analysis(raw)
    assert norm is not None
    assert not validate_replication_analysis_for_publish(norm)
