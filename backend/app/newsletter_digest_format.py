"""每日摘要：LLM 提示与邮件/飞书推送排版（条理清晰）。"""
from __future__ import annotations

import re
from typing import Any

DIGEST_SUBJECT_LLM_SYSTEM = (
    "为 AiTrends「今日精选」推送写标题。严格输出单个 JSON 对象，禁止 Markdown 围栏与 JSON 外文字。"
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


def build_digest_subject_default(digest_date: str, apps: list[Any], news: list[Any]) -> str:
    """无 LLM 时的默认标题。"""
    d = (digest_date or "").strip()
    na, nn = len(apps), len(news)
    if na and nn:
        return f"今日精选 · {na} 应用 {nn} 资讯 · {d}"
    if na:
        return f"今日 {na} 款 AI 应用 · {d}"
    if nn:
        return f"今日 {nn} 条 AI 资讯 · {d}"
    return f"AiTrends 每日精选 · {d}"


_TIER_LABEL: dict[str, str] = {
    "S": "高可复刻",
    "A": "较高可复刻",
    "B": "可复刻性中",
    "C": "低可复刻",
}


def _tier_display(tier: str) -> str:
    t = (tier or "").strip().upper()
    if not t:
        return ""
    return _TIER_LABEL.get(t, f"{t} 档")


def _why_follow(a: Any, *, feed_kind: str) -> str:
    tier = (getattr(a, "replication_tier", None) or "").strip().upper()
    if feed_kind == "apps":
        if tier == "S":
            return "高可复刻：产品边界清晰，适合独立开发者快速验证 MVP 与变现假设"
        if tier == "A":
            return "较高可复刻：形态明确，可参考其技术栈与用户路径做 1 月内验证"
        if tier == "B":
            return "可复刻性中等，需更多工程投入，建议结合站内详情评估范围"
        if tier == "C":
            return "低可复刻：偏基础设施或强依赖闭源能力，更适合跟踪趋势而非直接抄"
        if tier:
            return f"可复刻性 {_tier_display(tier)}，建议结合站内详情评估"
        return "热度靠前，适合作为今日可跟进的应用样本"
    return "当日高热度资讯，建议了解对行业与产品方向的影响"


def _highlight_item_lines(articles: list[Any], *, feed_kind: str) -> list[str]:
    lines: list[str] = []
    for i, a in enumerate(articles, 1):
        title = _snippet((getattr(a, "title", None) or "无标题"), max_len=64)
        intro = _snippet(getattr(a, "summary", None) or "", max_len=_HIGHLIGHT_SNIP)
        tier = (getattr(a, "replication_tier", None) or "").strip()
        tier_s = f" · {_tier_display(tier)}" if tier and feed_kind == "apps" else ""
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
) -> list[str]:
    """单栏：亮点详细介绍 + 其余简明列表。"""
    if not articles:
        return [
            f"## {highlight_title}",
            "",
            "> 今日暂无新稿。",
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
) -> str:
    """正文：亮点条目单独介绍，其余简明列表（均用站内已发布摘要，不二次 LLM）。"""
    parts: list[str] = []
    parts.extend(
        _lane_body(
            apps,
            feed_kind="apps",
            highlight_title="亮点应用",
            more_title="更多应用",
            kind_note="（可安装 / 可复刻产品向）",
            highlight_n=highlight_apps,
        )
    )
    parts.extend(
        _lane_body(
            news,
            feed_kind="news",
            highlight_title="亮点资讯",
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


def digest_md_to_plain_email(body_md: str, *, subject: str, digest_date: str) -> str:
    """邮件纯文本：保留分栏与条目层级。"""
    t = normalize_digest_body_md(body_md, apps_count=0, news_count=0)
    # 保留统计引用块，转为普通行
    t = re.sub(r"^>\s*", "▸ ", t, flags=re.MULTILINE)
    t = re.sub(r"^##\s+(.+)$", r"\n━━━━━━━━━━━━━━━━\n【\1】\n━━━━━━━━━━━━━━━━", t, flags=re.MULTILINE)
    t = re.sub(r"^###\s+(\d+\.\s*.+)$", r"\n\1", t, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    head = f"AiTrends 每日精选 · {digest_date}\n主题：{subject.strip()}\n"
    return _collapse_blank_lines(head + "\n" + t)


def digest_md_to_feishu_text(
    body_md: str,
    *,
    subject: str,
    digest_date: str,
    apps_count: int,
    news_count: int,
    public_site_base_url: str,
) -> str:
    """飞书文本：分栏符号 + 层级缩进。"""
    plain = digest_md_to_plain_email(
        normalize_digest_body_md(body_md, apps_count=apps_count, news_count=news_count),
        subject=subject,
        digest_date=digest_date,
    )
    base = (public_site_base_url or "").strip().rstrip("/")
    tail = f"\n\n🔗 完整站点：{base}" if base else ""
    meta = f"（应用 {apps_count} 条 · 资讯 {news_count} 条）\n" if (apps_count or news_count) else "\n"
    return f"📬 AiTrends 每日精选 · {digest_date}{meta}\n{plain}{tail}"[:4000]


def digest_delivery_texts(
    body_md: str,
    subject: str,
    *,
    digest_date: str,
    public_site_base_url: str,
    apps_count: int,
    news_count: int,
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
    )
    return md, email_plain, feishu_text
