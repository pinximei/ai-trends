"""连接器同步等场景下写入「资源」文章（product_articles），供公开站使用。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .domain.articles import (
    VALUE_SCORE_MIN,
    display_fingerprint,
    feed_lane,
    ingest_duplicate_exists,
    ingest_fingerprint,
    primary_canonical_from_raw_labels,
    rule_value_score,
    validate_llm_polish_for_publish,
    FACET_ALL_LABELS,
)
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
    每个连接器成功响应最多入库 **一篇** 已发布文章（多板块 targets 共用同一响应正文时去重）。
    流程：规则指纹去重 → 规则价值分（低于阈值整批丢弃）→ **必须** LLM 全文重写、分类与分 tab 结构；
    未配置模型、调用失败或 JSON 不合规则 **不入库**；展示指纹与近期已发布冲突则丢弃。
    """
    if not targets:
        return 0
    t0 = targets[0]
    industry_id = int(t0["industry_id"])
    segment_id = int(t0["segment_id"])
    label = (t0.get("label") or t0.get("segment_slug") or "板块")[:200]

    safe = (snippet or "")[:12000]
    ing_fp = ingest_fingerprint(safe)
    if ingest_duplicate_exists(db, industry_id=industry_id, ingest_fp=ing_fp):
        return 0

    summary_base, readable_body = _render_readable_snapshot(safe)
    summary_base = (summary_base or f"HTTP {http_status}")[:512]

    vs = rule_value_score(snippet=safe, summary=summary_base, http_status=http_status or 0)
    if vs < VALUE_SCORE_MIN:
        return 0

    src_tag = (admin_source_key or "").strip() or "未绑定数据源"
    fk = feed_lane(src_tag)
    slug = f"sync-c{connector_id}-s{segment_id}-{uuid.uuid4().hex[:16]}"[:128]
    rule_title = f"同步资源 · {label} · {connector_name}"[:500]
    rule_body = (
        "## 连接器同步快照\n\n"
        f"- **数据源标识**: `{src_tag}`\n"
        f"- **领域标签**: {label}\n"
        f"- **HTTP 状态**: {http_status}\n"
        f"- **规则价值分**: {vs:.0f}\n\n"
        "### 内容摘要\n\n"
        f"{readable_body}\n\n"
        "<details>\n"
        "<summary>原始返回片段</summary>\n\n"
        f"```json\n{safe[:8000]}\n```\n"
        "\n</details>\n"
    )

    from .llm_service import polish_connector_article

    polished = polish_connector_article(
        db,
        snippet=safe,
        connector_name=connector_name,
        admin_source_key=src_tag,
        segment_label=label,
        rule_title=rule_title,
        rule_summary=summary_base,
        value_score=vs,
        ref_id=f"c{connector_id}:{ing_fp[:12]}",
        feed_kind=fk,
    )
    if not polished or not validate_llm_polish_for_publish(polished):
        return 0

    title = (polished.get("title") or "")[:500]
    summary = (polished.get("summary") or "")[:512]
    tabs = polished.get("tabs") or []
    body_main = (polished.get("body_md") or "").strip()
    if not body_main:
        body_main = "\n\n".join(f"## {t['label']}\n\n{t['body_md']}" for t in tabs)
    body = body_main[:50000]
    cats = polished.get("categories")
    raw_list = [str(x).strip() for x in cats if str(x).strip()] if isinstance(cats, list) else []
    if len(raw_list) == 1 and raw_list[0] in FACET_ALL_LABELS:
        one = raw_list[0]
    else:
        one = primary_canonical_from_raw_labels(raw_list)
    clean = [one]
    ai_categories_json = json.dumps(clean, ensure_ascii=False)
    ai_tabs_json = json.dumps(
        [{"label": t["label"], "summary": t["summary"], "body_md": t["body_md"]} for t in tabs],
        ensure_ascii=False,
    )
    fk_out = str(polished.get("feed_kind") or fk).strip().lower()
    stored_feed_kind = fk_out if fk_out in ("news", "apps") else fk

    disp_fp = display_fingerprint(title, summary)

    # 展示层去重：与近期已发布条目的标题+摘要指纹冲突则跳过
    recent = db.scalars(
        select(Article)
        .where(Article.industry_id == industry_id, Article.status == "published")
        .order_by(desc(Article.published_at))
        .limit(80)
    ).all()
    for a in recent:
        if display_fingerprint(a.title, a.summary or "") == disp_fp:
            return 0

    db.add(
        Article(
            title=title,
            slug=slug,
            summary=summary,
            body=body,
            segment_id=segment_id,
            industry_id=industry_id,
            content_type="third_party_derived",
            third_party_source=f"{src_tag} / {connector_name}"[:512],
            status="published",
            published_at=now,
            ingest_fingerprint=ing_fp,
            ai_categories_json=ai_categories_json,
            ai_tabs_json=ai_tabs_json,
            feed_kind=stored_feed_kind,
        )
    )
    return 1
