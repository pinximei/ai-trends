"""每日摘要：LLM 提示与邮件/飞书推送排版（条理清晰）。"""
from __future__ import annotations

import re
from typing import Any

DIGEST_SUBJECT_LLM_SYSTEM = (
    "为 AiTrends「AI 产品雷达 · 每日精选」推送写标题。严格输出单个 JSON 对象，禁止 Markdown 围栏与 JSON 外文字。"
    '仅一个键 subject（中文标题，≤50 字）。'
    "只能根据用户给出的标题列表概括，禁止编造未列出的产品或事件；不要输出正文。"
)

_SUMMARY_SNIP = 96
_HIGHLIGHT_SNIP = 220
_COMPACT_SNIP = 72


def _snippet(text: str, *, max_len: int = _SUMMARY_SNIP) -> str:
    s = (text or "").strip().replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def build_digest_subject_default(
    digest_date: str,
    apps: list[Any],
    news: list[Any],
    *,
    period_label: str | None = None,
    period_kind: str | None = None,
) -> str:
    """无 LLM 时的默认标题。"""
    d = (period_label or digest_date or "").strip()
    kind = (period_kind or "每日精选").strip()
    na, nn = len(apps), len(news)
    if na and nn:
        return f"AI 产品雷达 · {kind} · {na} 应用 {nn} 资讯 · {d}"
    if na:
        return f"AI 产品雷达 · {kind} · {na} 款应用 · {d}"
    if nn:
        return f"AI 产品雷达 · {kind} · {nn} 条资讯 · {d}"
    return f"AI 产品雷达 · {kind} · {d}"


_TIER_LABEL: dict[str, str] = {
    "S": "高变现价值",
    "A": "较高变现价值",
    "B": "变现价值中",
    "C": "低变现价值",
}


def _tier_display(tier: str) -> str:
    t = (tier or "").strip().upper()
    if not t:
        return ""
    return _TIER_LABEL.get(t, f"{t} 档")


def _tier_suffix_for_article(a: Any, *, feed_kind: str) -> str:
    if feed_kind != "apps":
        return ""
    from .newsletter_replication import article_high_value_for_digest

    tier = (getattr(a, "replication_tier", None) or "").strip().upper()
    if not tier or not article_high_value_for_digest(a):
        return ""
    label = _tier_display(tier)
    return f" · {label}" if label else ""


def _why_follow(a: Any, *, feed_kind: str) -> str:
    from .newsletter_replication import article_high_value_for_digest, article_replication_public

    tier = (getattr(a, "replication_tier", None) or "").strip().upper()
    if feed_kind == "apps":
        repl = article_replication_public(a)
        if repl and article_high_value_for_digest(a):
            worth = int(repl.get("worth_score") or 0)
            verdict = (repl.get("verdict") or "").strip()
            vs = (repl.get("value_summary") or "").strip()
            head = f"深度评估 {worth}/10"
            if verdict:
                head = f"{head} · {verdict}"
            if vs:
                return f"{head}；{_snippet(vs, max_len=120)}"
            return head
        if tier in ("S", "A"):
            return "仅有档位标签，暂无完整变现评估，建议以热度与介绍为准，详见站内详情"
        if tier == "B":
            return "变现价值中等，站内评估未达标，建议结合详情判断"
        if tier == "C":
            return "低变现价值向，更适合跟踪趋势而非投入开发"
        return "当日热度靠前，可作为产品动态样本跟踪"
    return "当日高热度资讯，建议了解对行业与产品方向的影响"


def _highlight_item_lines(articles: list[Any], *, feed_kind: str) -> list[str]:
    lines: list[str] = []
    for i, a in enumerate(articles, 1):
        title = _snippet((getattr(a, "title", None) or "无标题"), max_len=64)
        intro = _snippet(getattr(a, "summary", None) or "", max_len=_HIGHLIGHT_SNIP)
        tier_s = _tier_suffix_for_article(a, feed_kind=feed_kind)
        aid = int(getattr(a, "id", 0) or 0)
        lines.append(f"### {i}. {title}{tier_s}")
        lines.append(f"- **介绍**：{intro or '见站内详情'}")
        lines.append(f"- **为何关注**：{_why_follow(a, feed_kind=feed_kind)}")
        lines.append(f"- **站内阅读**：文章 #{aid}")
        lines.append("")
    return lines


def _compact_list_lines(articles: list[Any]) -> list[str]:
    lines: list[str] = []
    for a in articles:
        title = _snippet((getattr(a, "title", None) or "无标题"), max_len=52)
        note = _snippet(getattr(a, "summary", None) or "", max_len=_COMPACT_SNIP)
        aid = int(getattr(a, "id", 0) or 0)
        tail = f" — {note}" if note else ""
        lines.append(f"- **{title}**{tail} · 文章 #{aid}")
    if not lines:
        lines.append("> 无")
    lines.append("")
    return lines


def _split_highlight(articles: list[Any], highlight_n: int) -> tuple[list[Any], list[Any]]:
    n = max(0, min(8, int(highlight_n)))
    if n <= 0:
        n = min(3, len(articles))
    if not articles:
        return [], []
    if len(articles) <= n:
        return list(articles), []
    return list(articles[:n]), list(articles[n:])


def _lane_body(
    articles: list[Any],
    *,
    feed_kind: str,
    highlight_title: str,
    more_title: str,
    kind_note: str,
    highlight_n: int,
    empty_message: str | None = None,
) -> list[str]:
    """单栏：亮点详细介绍 + 其余简明列表。"""
    if not articles:
        return [
            f"## {highlight_title}",
            "",
            f"> {empty_message or '今日暂无新稿。'}",
            "",
        ]
    featured, rest = _split_highlight(articles, highlight_n)
    lines: list[str] = [
        f"## {highlight_title}",
        "",
        f"> 编辑推荐 Top {len(featured)} 条{kind_note}",
        "",
    ]
    lines.extend(_highlight_item_lines(featured, feed_kind=feed_kind))
    if rest:
        lines.extend(
            [
                f"## {more_title}",
                "",
                f"> 另有 {len(rest)} 条{kind_note}",
                "",
            ]
        )
        lines.extend(_compact_list_lines(rest))
    return lines


def build_digest_body_from_articles(
    apps: list[Any],
    news: list[Any],
    *,
    highlight_apps: int = 3,
    highlight_news: int = 3,
    monetization_apps: list[Any] | None = None,
    regular_apps: list[Any] | None = None,
) -> str:
    """正文：亮点条目单独介绍，其余简明列表（均用站内已发布摘要，不二次 LLM）。"""
    from .newsletter_replication import split_deep_replicable_apps

    if monetization_apps is not None and regular_apps is not None:
        mon_lane, app_lane = monetization_apps, regular_apps
    else:
        mon_lane, app_lane = [], list(apps)
    replicable_apps, regular_rest = split_deep_replicable_apps(app_lane)
    parts: list[str] = [
        "> AI 产品雷达 · 每日精选（美东摘要日当天已发布）。"
        "「高价值应用」仅含价值分≥8 且结论为「高价值」的条目；其余按热度收录。",
        "",
    ]
    if mon_lane:
        parts.extend(
            _lane_body(
                mon_lane,
                feed_kind="apps",
                highlight_title="变现线索",
                more_title="更多变现向",
                kind_note="（并购 / 订阅收入 / Acquire·TAAFT）",
                highlight_n=min(highlight_apps, len(mon_lane)),
            )
        )
    parts.extend(
        _lane_body(
            replicable_apps,
            feed_kind="apps",
            highlight_title="高价值应用",
            more_title="更多高价值应用",
            kind_note="（价值分≥8 · 结论高价值）",
            highlight_n=highlight_apps,
            empty_message="今日无达标的高价值应用（价值分≥8 且结论为「高价值」）。",
        )
    )
    parts.extend(
        _lane_body(
            regular_rest,
            feed_kind="apps",
            highlight_title="今日应用",
            more_title="更多应用",
            kind_note="（热度向）",
            highlight_n=highlight_apps,
        )
    )
    parts.extend(
        _lane_body(
            news,
            feed_kind="news",
            highlight_title="本周必读",
            more_title="更多资讯",
            kind_note="（行业动态向）",
            highlight_n=highlight_news,
        )
    )
    return _collapse_blank_lines("\n".join(parts))

def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip())


def normalize_digest_body_md(
    body_md: str,
    *,
    apps_count: int = 0,
    news_count: int = 0,
) -> str:
    """规整空行（正文由模板生成，已含亮点/更多分栏）。"""
    _ = apps_count, news_count
    text = _collapse_blank_lines(body_md)
    return re.sub(r"([^\n])\n(## )", r"\1\n\n\2", text)


def enrich_digest_read_links(
    body_md: str,
    *,
    public_site_base_url: str,
    article_by_id: dict[int, Any],
) -> str:
    """在「站内阅读」行后补充可点击路径（邮件纯文本 / 飞书可见）。"""
    base = (public_site_base_url or "").strip().rstrip("/")
    if not base or not article_by_id:
        return body_md

    def _line_repl(line: str) -> str:
        m = re.search(r"文章\s*[#＃]?\s*(\d+)", line, re.IGNORECASE)
        if not m:
            m = re.search(r"\bid\s*=\s*(\d+)", line, re.IGNORECASE)
        if not m:
            return line
        aid = int(m.group(1))
        if aid not in article_by_id:
            return line
        url = f"{base}/resources/{aid}"
        if url in line:
            return line
        return f"{line.rstrip()} — {url}"

    lines = []
    for line in body_md.splitlines():
        if "站内阅读" in line or "文章" in line:
            lines.append(_line_repl(line))
        else:
            lines.append(line)
    return "\n".join(lines)


def _strip_md_inline(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return t.strip()


def digest_md_to_plain_email(body_md: str, *, subject: str, digest_date: str) -> str:
    """邮件纯文本：保留分栏与条目层级。"""
    t = normalize_digest_body_md(body_md, apps_count=0, news_count=0)
    # 保留统计引用块，转为普通行
    t = re.sub(r"^>\s*", "▸ ", t, flags=re.MULTILINE)
    t = re.sub(r"^##\s+(.+)$", r"\n——— 【\1】 ———", t, flags=re.MULTILINE)
    t = re.sub(r"^###\s+(\d+\.\s*.+)$", r"\n\1", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    head = f"AiTrends 每日精选 · {digest_date}\n主题：{subject.strip()}\n"
    return _collapse_blank_lines(head + "\n" + t)


def _digest_md_lines_to_feishu_body(body_md: str) -> str:
    """飞书纯文本：不用宽字符「图表线」，用【分栏】+ 缩进列表（Webhook 仅支持 text）。"""
    lines_out: list[str] = []
    for raw in normalize_digest_body_md(body_md, apps_count=0, news_count=0).splitlines():
        ln = raw.rstrip()
        if not ln:
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            continue
        if ln.startswith("## "):
            title = _strip_md_inline(ln[3:].strip())
            if lines_out:
                lines_out.append("")
            lines_out.append(f"【{title}】")
            continue
        if ln.startswith("### "):
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            lines_out.append(_strip_md_inline(ln[4:].strip()))
            continue
        if ln.startswith("> "):
            lines_out.append(f"▸ {_strip_md_inline(ln[2:])}")
            continue
        if ln.startswith("- "):
            item = _strip_md_inline(ln[2:])
            if item.startswith("介绍：") or item.startswith("为何关注：") or item.startswith("站内阅读："):
                lines_out.append(f"  {item}")
            else:
                lines_out.append(f"• {item}")
            continue
        lines_out.append(_strip_md_inline(ln))
    return _collapse_blank_lines("\n".join(lines_out))


def digest_md_to_feishu_text(
    body_md: str,
    *,
    subject: str,
    digest_date: str,
    apps_count: int,
    news_count: int,
    public_site_base_url: str,
    period_kind: str = "daily",
) -> str:
    """飞书文本：独立排版，避免邮件用的宽分隔线在手机端错位成「乱表」。"""
    body = _digest_md_lines_to_feishu_body(body_md)
    base = (public_site_base_url or "").strip().rstrip("/")
    tail = f"\n\n🔗 完整站点：{base}" if base else ""
    meta = f"（应用 {apps_count} 条 · 资讯 {news_count} 条）" if (apps_count or news_count) else ""
    kind_labels = {"daily": "每日精选", "weekly": "周报", "monthly": "月报"}
    kind_label = kind_labels.get((period_kind or "daily").strip().lower(), "精选")
    head = f"📬 AI 产品雷达 · {kind_label} · {digest_date}\n主题：{_strip_md_inline(subject)}"
    if meta:
        head = f"{head}\n{meta}"
    return _collapse_blank_lines(f"{head}\n\n{body}{tail}")[:4000]


def digest_delivery_texts(
    body_md: str,
    subject: str,
    *,
    digest_date: str,
    public_site_base_url: str,
    apps_count: int,
    news_count: int,
    period_kind: str = "daily",
) -> tuple[str, str]:
    """从已落库的 body_md 生成邮件纯文本与飞书正文（发送阶段）。"""
    md = normalize_digest_body_md(body_md, apps_count=apps_count, news_count=news_count)
    email_plain = digest_md_to_plain_email(md, subject=subject, digest_date=digest_date)
    feishu_text = digest_md_to_feishu_text(
        md,
        subject=subject,
        digest_date=digest_date,
        apps_count=apps_count,
        news_count=news_count,
        public_site_base_url=public_site_base_url,
        period_kind=period_kind,
    )
    return email_plain, feishu_text


def format_digest_for_delivery(
    body_md: str,
    subject: str,
    *,
    digest_date: str,
    public_site_base_url: str,
    apps: list[Any],
    news: list[Any],
) -> tuple[str, str, str]:
    """
    返回 (normalized_md, email_plain, feishu_text)。
    """
    by_id = {int(a.id): a for a in apps + news if getattr(a, "id", None) is not None}
    md = normalize_digest_body_md(body_md, apps_count=len(apps), news_count=len(news))
    md = enrich_digest_read_links(md, public_site_base_url=public_site_base_url, article_by_id=by_id)
    email_plain = digest_md_to_plain_email(md, subject=subject, digest_date=digest_date)
    feishu_text = digest_md_to_feishu_text(
        md,
        subject=subject,
        digest_date=digest_date,
        apps_count=len(apps),
        news_count=len(news),
        public_site_base_url=public_site_base_url,
        period_kind="daily",
    )
    return md, email_plain, feishu_text
