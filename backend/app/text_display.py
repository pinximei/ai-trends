"""前台卡片摘要、Tab 文案：编码修复与 Markdown 转可读纯文本。"""
from __future__ import annotations

import json
import re


def repair_utf8_mojibake(text: str) -> str:
    """
    修复常见 UTF-8 被按 Latin-1/CP1252 误解码后的乱码（如 Ã©、â€™）。
    已是正常中文时原样返回。
    """
    s = (text or "").strip()
    if not s:
        return ""
    if re.search(r"[\u4e00-\u9fff]", s):
        return s

    def _try_fix(enc: str) -> str | None:
        try:
            fixed = s.encode(enc).decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            return None
        if not fixed or fixed == s:
            return None
        if re.search(r"[\u4e00-\u9fff]", fixed):
            return fixed
        return None

    for enc in ("latin-1", "cp1252"):
        fixed = _try_fix(enc)
        if fixed:
            return fixed
    return s


def markdown_to_plain_preview(md: str, *, max_len: int = 500) -> str:
    """
    列表卡片用：去掉 Markdown 表格竖线、代码块、链接语法，避免「数据支撑」显示成乱码表头。
    """
    s = repair_utf8_mojibake((md or "").strip())
    if not s:
        return ""
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    lines_out: list[str] = []
    for line in s.splitlines():
        t = line.strip()
        if not t:
            continue
        if re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", t):
            continue
        if "|" in t and t.count("|") >= 2:
            cells = [c.strip() for c in t.strip("|").split("|") if c.strip()]
            if len(cells) >= 2 and not all(re.match(r"^:?-{3,}:?$", c) for c in cells):
                lines_out.append(f"{cells[0]}：{cells[1]}" + (f"（{cells[2]}）" if len(cells) > 2 else ""))
                continue
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        t = re.sub(r"^#+\s*", "", t)
        t = re.sub(r"^[-*+]\s+", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            lines_out.append(t)
    out = "；".join(lines_out) if lines_out else re.sub(r"\s+", " ", s)
    out = re.sub(r"\s+", " ", out).strip()
    if max_len > 0 and len(out) > max_len:
        return out[: max_len - 1].rstrip() + "…"
    return out


def sanitize_stored_text_field(text: str, *, max_len: int = 50000) -> str:
    """入库/读出统一：修编码 + 去控制字符。"""
    s = repair_utf8_mojibake((text or "").replace("\x00", ""))
    if max_len > 0:
        s = s[:max_len]
    return s


def format_connector_snippet_plain(snippet: str, *, admin_source_key: str = "", max_len: int = 4000) -> str:
    """连接器 JSON → 中文可读要点（避免 json.dumps 整段塞进「数据支撑」）。"""
    text = (snippet or "").strip()[: max_len + 2000]
    if not text:
        return ""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return markdown_to_plain_preview(text, max_len=max_len)

    k = (admin_source_key or "").strip().lower()
    rows: list[tuple[str, str]] = []

    def add(label: str, val: object) -> None:
        if val is None:
            return
        if isinstance(val, (dict, list)):
            return
        s = str(val).strip()
        if s:
            rows.append((label, s[:500]))

    if isinstance(obj, dict):
        if k == "github":
            add("仓库", obj.get("full_name") or obj.get("name"))
            add("Star 总数", obj.get("stargazers_count") or obj.get("stars"))
            add("今日 Star", obj.get("trending_stars_today"))
            add("主语言", obj.get("language"))
            lic = obj.get("license")
            if isinstance(lic, dict):
                add("许可证", lic.get("spdx_id") or lic.get("name"))
            elif lic:
                add("许可证", lic)
            add("主页", obj.get("homepage"))
            desc = str(obj.get("description") or "").strip()
            if desc:
                rows.append(("简介", markdown_to_plain_preview(desc, max_len=280)))
        elif k == "hacker_news":
            add("标题", obj.get("title"))
            add("票数", obj.get("points"))
            add("评论", obj.get("num_comments"))
            add("作者", obj.get("author"))
            add("链接", obj.get("url"))
        elif k == "product_hunt":
            add("产品", obj.get("name") or obj.get("title"))
            add("标语", obj.get("tagline"))
            add("投票", obj.get("votesCount") or obj.get("votes_count"))
            add("官网", obj.get("website") or obj.get("url"))
        elif k in ("newsapi", "thenewsapi"):
            add("标题", obj.get("title"))
            add("来源", obj.get("source") or obj.get("source_name"))
            add("时间", obj.get("publishedAt") or obj.get("published_at") or obj.get("date"))
            add("链接", obj.get("url"))
        elif k == "acquire":
            add("标题", obj.get("title") or obj.get("name"))
            add("链接", obj.get("url"))
        else:
            for key in ("title", "name", "tagline", "description", "url", "website"):
                add(key, obj.get(key))

    if rows:
        lines = [f"{lab}：{val}" for lab, val in rows[:12]]
        out = "\n".join(lines)
        return out[:max_len]

    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return format_connector_snippet_plain(
            json.dumps(obj[0], ensure_ascii=False),
            admin_source_key=admin_source_key,
            max_len=max_len,
        )

    return markdown_to_plain_preview(json.dumps(obj, ensure_ascii=False)[:max_len], max_len=max_len)
