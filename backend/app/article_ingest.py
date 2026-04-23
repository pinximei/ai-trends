"""连接器同步等场景下写入「资源」文章（product_articles），供公开站 /resources 使用。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from .product_models import Article


def _render_readable_snapshot(snippet: str) -> tuple[str, str]:
    """将接口返回片段转为可读摘要与正文（优先 JSON）。"""
    text = (snippet or "").strip()
    if not text:
        return ("暂无返回内容", "暂无返回内容。")
    try:
        payload = json.loads(text)
    except Exception:
        plain = text[:3000]
        return (plain[:500], plain)

    if isinstance(payload, dict):
        lines: list[str] = []
        for k, v in list(payload.items())[:10]:
            if isinstance(v, (dict, list)):
                vv = json.dumps(v, ensure_ascii=False)[:220]
            else:
                vv = str(v)[:220]
            lines.append(f"- **{k}**: {vv}")
        if not lines:
            lines.append("- 返回对象为空")
        summary = "；".join(line.replace("- **", "").replace("**: ", "=") for line in lines[:3])[:500]
        return (summary, "\n".join(lines))

    if isinstance(payload, list):
        top = payload[:5]
        lines = [f"- 条目 {i + 1}: {json.dumps(item, ensure_ascii=False)[:220]}" for i, item in enumerate(top)]
        summary = f"返回列表，共 {len(payload)} 条，展示前 {len(top)} 条。"
        return (summary[:500], "\n".join(lines))

    val = str(payload)
    return (val[:500], val[:3000])


def create_published_articles_for_connector_targets(
    db: Session,
    *,
    connector_id: int,
    connector_name: str,
    admin_source_key: str,
    targets: list[dict],
    http_status: int,
    snippet: str,
    now: datetime,
) -> int:
    """
    为每个解析出的 (industry_id, segment_id) 新增一篇 **已发布** 文章。
    targets 项须含: industry_id, segment_id, segment_slug, label（展示用）。
    返回新建篇数。
    """
    if not targets:
        return 0
    safe = (snippet or "")[:12000]
    summary_base, readable_body = _render_readable_snapshot(safe)
    summary_base = (summary_base or f"HTTP {http_status}")[:512]
    src_tag = admin_source_key.strip() if admin_source_key.strip() else "未绑定数据源"
    n = 0
    for t in targets:
        slug = f"sync-c{connector_id}-s{t['segment_id']}-{uuid.uuid4().hex[:16]}"[:128]
        label = (t.get("label") or t.get("segment_slug") or "板块")[:200]
        title = f"同步资源 · {label} · {connector_name}"[:500]
        body = (
            "## 连接器同步快照\n\n"
            f"- **数据源标识**: `{src_tag}`\n"
            f"- **领域标签**: {label}\n"
            f"- **HTTP 状态**: {http_status}\n\n"
            "### 内容摘要\n\n"
            f"{readable_body}\n\n"
            "<details>\n"
            "<summary>原始返回片段</summary>\n\n"
            f"```json\n{safe[:8000]}\n```\n"
            "\n</details>\n"
        )
        db.add(
            Article(
                title=title,
                slug=slug,
                summary=summary_base,
                body=body,
                segment_id=int(t["segment_id"]),
                industry_id=int(t["industry_id"]),
                content_type="third_party_derived",
                third_party_source=f"{src_tag} / {connector_name}"[:512],
                status="published",
                published_at=now,
            )
        )
        n += 1
    return n
