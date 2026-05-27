"""变现/工时评估测试用公共样例。"""
from __future__ import annotations

from typing import Any


def sample_market_position() -> dict[str, Any]:
    return {
        "target_user": "独立开发者与小团队，需要快速验证 AI 小工具变现",
        "vertical_niche": "将代码仓库整理为 LLM 上下文文件的开发者工具",
        "market_saturation": "竞争适中",
        "competitors": [
            {"name": "同类上下文导出工具", "note": "功能重叠，差异化在中文模板与工作流集成"},
        ],
        "differentiation": "聚焦中文注释格式与国内开发者工作流，而非通用文件打包",
        "monetization_hypothesis": "订阅制 8–15 美元/月，按导出次数或私有部署加价",
    }


def sample_phases() -> list[dict[str, Any]]:
    return [
        {
            "name": "核心 MVP",
            "hours_min": 40,
            "hours_max": 60,
            "deliverable": "可演示的主流程与基础 UI",
        },
        {
            "name": "支付与上架",
            "hours_min": 20,
            "hours_max": 30,
            "deliverable": "订阅或买断路径可跑通",
        },
        {
            "name": "打磨发布",
            "hours_min": 16,
            "hours_max": 24,
            "deliverable": "上架素材、文档与首批用户反馈",
        },
    ]


def sample_ai_usage_steps() -> list[str]:
    return [
        "用 LLM 根据 README 生成产品边界与 MVP 功能列表（人工审核）",
        "实现阶段：仅对「选文件规则」调用模型，核心逻辑用确定性代码",
    ]


def sample_replication_analysis(*, worth: int = 8, verdict: str = "高价值") -> dict[str, Any]:
    phases = sample_phases()
    pmin = sum(p["hours_min"] for p in phases)
    pmax = sum(p["hours_max"] for p in phases)
    return {
        "verdict": verdict,
        "worth_score": worth,
        "difficulty": "中",
        "phases": phases,
        "estimated_hours": {
            "mvp_min": pmin,
            "mvp_max": pmax,
            "prod_min": int(pmax * 1.5),
            "prod_max": int(pmax * 2.5),
        },
        "team_shape": "1 人业余，每周约 20 小时",
        "assumptions": "使用现成 UI 组件与托管，不含应用商店审核排队",
        "platform_fit": "cross_platform",
        "tier_rationale": "订阅路径清晰，MVP 可在数周内验证付费意愿。",
        "value_summary": "面向重度 AI 用户的上下文打包工具，订阅 8–15 美元/月具备合理性。",
        "tech_stack": ["TypeScript", "Electron"],
        "implementation_plan": ["搭建导出管线", "接入 Stripe", "发布 beta"],
        "implementation_details": ["本地 IndexedDB 缓存"],
        "open_source": {"has_support": False, "projects": [], "gaps": ""},
        "risks": ["竞品多、差异化需持续运营"],
        "market_position": sample_market_position(),
        "ai_usage_steps": sample_ai_usage_steps(),
    }
