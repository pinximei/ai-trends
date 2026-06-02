"""连接器同步等场景下写入「资源」文章（product_articles），供公开站使用。

无实质正文（仅链接/占位摘要）一律不入库，见 ``domain.articles.polish_payload_has_substantive_content``。
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .domain.articles import (
    CONNECTOR_HEAT_TOP_N,
    CONNECTOR_SNIPPET_MAX_CHARS,
    value_score_min_for_source,
    parse_connector_sync_item_snippets,
    display_fingerprint,
    extract_cover_image_url,
    extract_connector_primary_url,
    ensure_connector_links_in_polish_tabs,
    published_at_for_connector_ingest,
    extract_github_engagement_from_snippet,
    extract_source_external_id_from_connector_snippet,
    feed_lane,
    feed_lane_for_article,
    ingest_duplicate_by_source_external_id_exists,
    ingest_duplicate_exists,
    ingest_fingerprint,
    primary_canonical_from_raw_labels,
    rule_value_score,
    unified_connector_heat,
    FACET_ALL_LABELS,
)
from .product_models import Article


def _snippet_title_preview(snippet: str, *, max_len: int = 100) -> str:
    """从连接器单条 JSON snippet 提取标题，供同步诊断日志展示。"""
    text = (snippet or "").strip()
    if not text:
        return "—"
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            t = (obj.get("title") or obj.get("name") or "").strip()
            if t:
                return t[:max_len]
    except json.JSONDecodeError:
        pass
    return text.replace("\n", " ")[:max_len]


def _strip_raw_json_from_markdown(text: str) -> str:
    from .text_display import _strip_inline_json_blobs

    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"```json\s*[\s\S]*?```", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<details>[\s\S]*?</details>", "", s, flags=re.IGNORECASE)
    s = re.sub(r">\s*\*\*原始摘录\*\*[\s\S]*?(?=\n##\s|\n#\s|$)", "", s, flags=re.IGNORECASE)
    s = _strip_inline_json_blobs(s)
    return re.sub(r"\n{4,}", "\n\n\n", s).strip()


def _ensure_markdown_paragraphs(text: str) -> str:
    s = _strip_raw_json_from_markdown(text)
    if not s or "\n\n" in s:
        return s
    first = (s.split("\n", 1)[0] or "").strip()
    if re.match(r"^[-*#|>]", first) or "|" in first:
        return s
    parts = [p.strip() for p in re.split(r"(?<=[。！？])\s+", s) if p.strip()]
    if len(parts) <= 2:
        return s
    return "\n\n".join(parts)


def _normalize_polish_tabs(
    tabs: list,
    *,
    admin_source_key: str = "",
    source_original_url: str = "",
    snippet: str = "",
) -> None:
    from .text_display import normalize_article_tabs_for_display

    norm = normalize_article_tabs_for_display(
        tabs,
        admin_source_key=admin_source_key,
        source_original_url=source_original_url,
        snippet=snippet,
    )
    tabs.clear()
    tabs.extend(norm)


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


def _apply_github_engagement_to_article(
    row: Article,
    *,
    admin_source_key: str,
    single_snippet: str,
    http_status: int,
    now: datetime,
) -> None:
    """写入/刷新 GitHub star 指标、热度分与 ``updated_at``（供前台按更新时间排序展示）。"""
    safe = (single_snippet or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
    summary_base = ""
    try:
        obj = json.loads(safe)
        if isinstance(obj, dict):
            summary_base = (obj.get("description") or obj.get("readme_md") or "")[:512]
    except json.JSONDecodeError:
        pass
    vs = rule_value_score(snippet=safe, summary=summary_base, http_status=http_status or 0)
    row.heat_score = unified_connector_heat(
        admin_source_key=(admin_source_key or "").strip(),
        snippet=safe,
        value_score=vs,
        sync_unix=float(now.timestamp()),
        connector_rank=0,
        connector_pool_size=CONNECTOR_HEAT_TOP_N,
    )
    ak = (admin_source_key or "").strip().lower()
    if ak == "github":
        metrics = extract_github_engagement_from_snippet(safe)
        if metrics.get("stars_total") is not None:
            row.engagement_stars_total = metrics["stars_total"]
        if metrics.get("stars_today") is not None:
            row.engagement_stars_today = metrics["stars_today"]
    cover = extract_cover_image_url(ak, safe)
    if cover:
        row.cover_image_url = cover
    primary_url = extract_connector_primary_url(admin_source_key, safe)
    if primary_url:
        row.source_original_url = primary_url[:2048]
    row.updated_at = now


def _refresh_article_heat_if_duplicate_external_id(
    db: Session,
    *,
    industry_id: int,
    admin_source_key: str,
    source_external_id: str | None,
    single_snippet: str,
    http_status: int,
    now: datetime | None = None,
) -> int:
    """同一上游条目已入库时：刷新 star 指标、``heat_score`` 与 ``updated_at``，不新建文章。"""
    sid = (source_external_id or "").strip()
    if not sid:
        return 0
    row = db.scalar(
        select(Article)
        .where(
            Article.industry_id == industry_id,
            Article.source_external_id == sid[:512],
            Article.status == "published",
        )
        .order_by(desc(Article.id))
        .limit(1)
    )
    if not row:
        return 0
    ts = now or datetime.utcnow()
    _apply_github_engagement_to_article(
        row,
        admin_source_key=admin_source_key,
        single_snippet=single_snippet,
        http_status=http_status,
        now=ts,
    )
    row.published_at = published_at_for_connector_ingest(single_snippet, now=ts)
    db.flush()
    return 1


def _create_one_published_article_from_connector_targets(
    db: Session,
    *,
    connector_id: int,
    connector_name: str,
    admin_source_key: str,
    targets: list[dict],
    http_status: int,
    single_snippet: str,
    now: datetime,
    connector_sync_log_id: int | None = None,
    connector_rank: int = 0,
    connector_pool_size: int = CONNECTOR_HEAT_TOP_N,
) -> int:
    t0 = targets[0]
    industry_id = int(t0["industry_id"])
    segment_id = int(t0["segment_id"])
    label = (t0.get("label") or t0.get("segment_slug") or "板块")[:200]

    safe = (single_snippet or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
    ing_fp = ingest_fingerprint(safe)
    src_tag = (admin_source_key or "").strip() or "未绑定数据源"

    title_prev = _snippet_title_preview(safe)

    def _diag(level: str, step: str, msg: str) -> None:
        try:
            from .sync_diagnostic_log import commit_diagnostics, write as diag_write

            diag_write(
                db,
                level=level,
                step=step,
                message=msg,
                connector_id=connector_id,
                source_key=src_tag if src_tag != "未绑定数据源" else None,
            )
            commit_diagnostics(db)
        except Exception:
            pass

    def _skip(step: str, msg: str, *, level: str = "error") -> None:
        _diag(level, step, f"「{title_prev}」{msg}")

    source_external_id = extract_source_external_id_from_connector_snippet(safe)
    if ingest_duplicate_by_source_external_id_exists(
        db, industry_id=industry_id, source_external_id=source_external_id
    ):
        n = _refresh_article_heat_if_duplicate_external_id(
            db,
            industry_id=industry_id,
            admin_source_key=admin_source_key,
            source_external_id=source_external_id,
            single_snippet=safe,
            http_status=http_status,
            now=now,
        )
        _skip(
            "skip_dup_ext",
            f"重复上游 id={source_external_id or '—'}：已刷新热度/star 与 published_at，未新建",
            level="info",
        )
        return n

    if ingest_duplicate_exists(db, industry_id=industry_id, ingest_fp=ing_fp):
        sid = (source_external_id or "").strip()
        if sid and not ingest_duplicate_by_source_external_id_exists(
            db, industry_id=industry_id, source_external_id=sid
        ):
            legacy = db.scalar(
                select(Article)
                .where(
                    Article.industry_id == industry_id,
                    Article.status == "published",
                    Article.source_original_url == sid[:2048],
                )
                .order_by(desc(Article.id))
                .limit(1)
            )
            if legacy:
                _apply_github_engagement_to_article(
                    legacy,
                    admin_source_key=admin_source_key,
                    single_snippet=safe,
                    http_status=http_status,
                    now=now,
                )
                legacy.source_external_id = sid[:512]
                legacy.published_at = published_at_for_connector_ingest(safe, now=now)
                db.flush()
                _skip("skip_dup_fp", f"指纹重复但已按 url 刷新旧稿 id={legacy.id}")
                return 1
        _skip("skip_dup_fp", "跳过：内容指纹重复（ingest_fingerprint）")
        return 0

    summary_base, readable_body = _render_readable_snapshot(safe)
    summary_base = (summary_base or f"HTTP {http_status}")[:512]

    from .domain.articles import connector_upstream_has_ingest_material

    upstream_ok, upstream_msg = connector_upstream_has_ingest_material(safe, src_tag)
    if not upstream_ok:
        _skip("skip_thin_upstream", f"跳过：{upstream_msg}")
        return 0

    score_min = value_score_min_for_source(admin_source_key)
    vs = rule_value_score(snippet=safe, summary=summary_base, http_status=http_status or 0)
    if vs < score_min:
        hint = ""
        if len((safe or "").strip()) < 80:
            hint = f" 响应过短（{len((safe or '').strip())} 字符）"
            if (admin_source_key or "").strip().lower() == "github":
                hint += "：请将数据源 api_base 设为 https://github.com/trending?since=daily"
            preview = (safe or "").strip().replace("\n", " ")[:120]
            if preview:
                hint += f" 片段={preview!r}"
        _skip("skip_score", f"跳过：规则价值分 {vs:.0f} < 门槛 {score_min:.0f}{hint}")
        return 0

    fk = feed_lane(src_tag)
    if src_tag.lower() == "github":
        fk = "apps"
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

    from .llm_settings_service import resolve_llm_http_config
    from .llm_service import polish_connector_article

    _base, _llm_key, _llm_model = resolve_llm_http_config(db)
    if not (_llm_key or "").strip():
        _diag(
            "error",
            "skip_llm_no_key",
            f"「{title_prev}」跳过：库内未配置 LLM API Key（所有数据源共用）。"
            "请在管理端「AI 资讯与数据」保存 Key。",
        )
        return 0

    polished, polish_err = polish_connector_article(
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
    from .polish_publish_compat import ensure_publishable_polish

    ready = ensure_publishable_polish(
        polished,
        admin_source_key=admin_source_key,
        snippet=safe,
        rule_title=rule_title,
        rule_summary=summary_base,
    )
    if not ready:
        from .connector_ingest_diagnostics import diagnose_polish_failure
        from .llm_service import _describe_polish_reject

        item_ref = (
            f"pack {connector_rank + 1}/{connector_pool_size}："
            if connector_pool_size > 1
            else ""
        )
        if polished:
            reject = _describe_polish_reject(polished, admin_source_key=admin_source_key)
            explain = diagnose_polish_failure(
                polished,
                reject,
                admin_source_key=admin_source_key,
                phase="compat_exhausted",
            )
            step = "skip_llm_shape"
        else:
            explain = diagnose_polish_failure(
                None,
                "",
                admin_source_key=admin_source_key,
                polish_err=polish_err or "",
                phase="final",
            )
            step = "skip_llm_polish"
        _diag("error", step, f"{item_ref}「{title_prev}」{explain}")
        return 0
    polished = ready

    from .domain.articles import (
        PUBLISH_MIN_SUBSTANTIVE_CHARS,
        collect_polish_text_blob,
        polish_payload_has_substantive_content,
        polish_substantive_char_count,
        substantive_content_reject_message,
    )

    if not polish_payload_has_substantive_content(polished):
        blob = collect_polish_text_blob(polished)
        from .domain.articles import polish_substantive_cjk_count, strip_urls_and_markdown_links

        stripped = strip_urls_and_markdown_links(blob)
        got = polish_substantive_char_count(stripped)
        got_cjk = polish_substantive_cjk_count(stripped)
        _skip(
            "skip_no_content",
            f"跳过：{substantive_content_reject_message(got=got, got_cjk=got_cjk, feed_kind=str(polished.get('feed_kind') or fk), min_chars=PUBLISH_MIN_SUBSTANTIVE_CHARS)}"
            " 请核对 Product Hunt/GitHub 是否走专用打包、LLM Key 与润色日志。",
        )
        return 0

    tabs = polished.get("tabs") or []
    source_original_url = extract_connector_primary_url(src_tag, safe)
    if isinstance(tabs, list):
        _normalize_polish_tabs(
            tabs,
            admin_source_key=src_tag,
            source_original_url=source_original_url or "",
            snippet=safe,
        )
        ensure_connector_links_in_polish_tabs(src_tag, safe, tabs)

    title = (polished.get("title") or "")[:500]
    summary = (polished.get("summary") or "")[:512]
    body_main = _ensure_markdown_paragraphs(str(polished.get("body_md") or ""))
    joined_tabs = "\n\n".join(
        f"## {t['label']}\n\n{t.get('body_md', '')}" for t in tabs if isinstance(t, dict) and t.get("label")
    )[:50000]
    if len(body_main) < 400 and joined_tabs.strip():
        body_main = joined_tabs
    elif not body_main:
        body_main = joined_tabs
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
        [
            {"label": str(t.get("label") or ""), "summary": str(t.get("summary") or ""), "body_md": str(t.get("body_md") or "")}
            for t in tabs
            if isinstance(t, dict)
        ],
        ensure_ascii=False,
    )
    stored_feed_kind = feed_lane_for_article(
        src_tag,
        title=title,
        summary=summary,
        ai_categories_json=ai_categories_json,
        ai_tabs_json=ai_tabs_json,
    )
    from .domain.articles import normalize_replication_tier

    replication_tier = normalize_replication_tier(polished.get("replication_tier"))
    repl_raw = polished.get("replication_analysis")
    if isinstance(repl_raw, dict):
        from .domain.replication_analysis import normalize_replication_analysis

        repl_norm = normalize_replication_analysis(repl_raw, pricing_context=safe[:4000])
        replication_analysis_json = json.dumps(repl_norm or {}, ensure_ascii=False)
    else:
        replication_analysis_json = "{}"

    disp_fp = display_fingerprint(title, summary)

    heat = unified_connector_heat(
        admin_source_key=src_tag,
        snippet=safe,
        value_score=vs,
        sync_unix=float(time.time()),
        connector_rank=connector_rank,
        connector_pool_size=max(1, int(connector_pool_size)),
    )

    recent = db.scalars(
        select(Article)
        .where(Article.industry_id == industry_id, Article.status == "published")
        .order_by(desc(Article.published_at))
        .limit(500)
    ).all()
    for a in recent:
        if display_fingerprint(a.title, a.summary or "") == disp_fp:
            _skip("skip_disp_fp", "跳过：展示指纹与近期文章重复")
            return 0

    cover_image_url = extract_cover_image_url(src_tag, safe)
    published_at = published_at_for_connector_ingest(safe, now=now)
    art = Article(
        title=title,
        slug=slug,
        summary=summary,
        body=body,
        segment_id=segment_id,
        industry_id=industry_id,
        content_type="third_party_derived",
        third_party_source=f"{src_tag} / {connector_name}"[:512],
        connector_sync_log_id=connector_sync_log_id,
        source_external_id=(source_external_id[:512] if source_external_id else None),
        source_original_url=(source_original_url[:2048] if source_original_url else None),
        status="published",
        published_at=published_at,
        ingest_fingerprint=ing_fp,
        ai_categories_json=ai_categories_json,
        ai_tabs_json=ai_tabs_json,
        feed_kind=stored_feed_kind,
        replication_tier=replication_tier,
        replication_analysis_json=replication_analysis_json,
        heat_score=heat,
        cover_image_url=cover_image_url,
    )
    if src_tag.lower() == "github":
        metrics = extract_github_engagement_from_snippet(safe)
        if metrics.get("stars_total") is not None:
            art.engagement_stars_total = metrics["stars_total"]
        if metrics.get("stars_today") is not None:
            art.engagement_stars_today = metrics["stars_today"]
    art.updated_at = now
    db.add(art)
    db.flush()
    return 1


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
    connector_sync_log_id: int | None = None,
) -> int:
    """
    连接器成功响应后入库已发布文章。

    - 若响应为 ``connector_sync_items_v1`` 多段 pack（热度榜 + 逐条详情），则**逐条**最多 15 篇；
    - 否则仍按整段 ``snippet`` 最多入库 **一篇**。
    每条均走：指纹去重 → 价值分 → LLM 润色 → 展示指纹去重。
    """
    if not targets:
        return 0
    safe_full = (snippet or "")[:CONNECTOR_SNIPPET_MAX_CHARS]
    parts = parse_connector_sync_item_snippets(safe_full)
    if parts:
        pool_n = len(parts)
        total = 0
        sk = (admin_source_key or "").strip().lower()
        for rank, piece in enumerate(parts):
            n = _create_one_published_article_from_connector_targets(
                db,
                connector_id=connector_id,
                connector_name=connector_name,
                admin_source_key=admin_source_key,
                targets=targets,
                http_status=http_status,
                single_snippet=piece,
                now=now,
                connector_sync_log_id=connector_sync_log_id,
                connector_rank=rank,
                connector_pool_size=pool_n,
            )
            total += n
        if total == 0:
            try:
                from .sync_diagnostic_log import commit_diagnostics, write as diag_write

                diag_write(
                    db,
                    level="error",
                    step="ingest_pack_empty",
                    message=(
                        f"pack 共 {pool_n} 条，0 篇入库。"
                        "每条失败原因见本 run 内 skip_* / skip_llm_* 行（重复、价值分不足、LLM 校验等）。"
                    ),
                    connector_id=connector_id,
                    source_key=sk or None,
                )
                commit_diagnostics(db)
            except Exception:
                pass
        return total
    return _create_one_published_article_from_connector_targets(
        db,
        connector_id=connector_id,
        connector_name=connector_name,
        admin_source_key=admin_source_key,
        targets=targets,
        http_status=http_status,
        single_snippet=safe_full,
        now=now,
        connector_sync_log_id=connector_sync_log_id,
    )
