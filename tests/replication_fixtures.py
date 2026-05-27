"""复刻评估测试用公共样例。"""
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


def sample_ai_usage_steps() -> list[str]:
    return [
        "用 LLM 根据 README 生成产品边界与 MVP 功能列表（人工审核）",
        "实现阶段：仅对「选文件规则」调用模型，核心逻辑用确定性代码",
    ]
