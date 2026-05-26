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


_EN_KV_LINE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*[:：]\s*(.+)$")
_ZH_KV_LINE = re.compile(r"^(.{1,32}?)\s*[：:]\s*(.+)$")

_EN_FIELD_LABELS: dict[str, str] = {
    "full_name": "仓库",
    "name": "名称",
    "stargazers_count": "Star 总数",
    "stars": "Star 总数",
    "trending_stars_today": "今日 Star",
    "language": "主语言",
    "description": "简介",
    "homepage": "主页",
    "title": "标题",
    "tagline": "标语",
    "votesCount": "投票",
    "votes_count": "投票",
    "points": "票数",
    "num_comments": "评论",
    "author": "作者",
    "url": "链接",
    "website": "官网",
}


def _rows_to_data_tab_markdown(rows: list[tuple[str, str]], *, extra_links: list[tuple[str, str]] | None = None) -> str:
    if not rows and not extra_links:
        return ""
    md = ["## 数据支撑", "", "| 指标 | 内容 |", "| --- | --- |"]
    for lab, val in rows[:14]:
        val_esc = str(val).replace("|", "\\|").replace("\n", " ")
        md.append(f"| {lab} | {val_esc} |")
    if extra_links:
        md.append("")
        md.append("**相关链接**")
        md.append("")
        for lab, url in extra_links[:6]:
            u = str(url).strip()
            if u:
                md.append(f"- [{lab}]({u})")
    return "\n".join(md)


def _extract_json_snippet_from_body(body: str) -> str:
    m = re.search(r"```json\s*([\s\S]*?)\s*```", body, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    s = body.strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    for m2 in re.finditer(r"\{[\s\S]{20,8000}\}", s):
        chunk = m2.group(0)
        try:
            json.loads(chunk)
            return chunk
        except json.JSONDecodeError:
            continue
    return ""


def _extract_rows_from_degraded_body(body: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(label: str, val: str) -> None:
        lab = label.strip()
        v = val.strip()
        if not lab or not v or lab in seen:
            return
        if lab in ("字段", "指标", "内容", "数值") and v in ("内容", "数值", "---"):
            return
        seen.add(lab)
        rows.append((lab, v[:500]))

    for line in body.splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        m_en = _EN_KV_LINE.match(t)
        if m_en:
            key = t.split(":", 1)[0].split("：", 1)[0].strip()
            val = m_en.group(1).strip()
            add(_EN_FIELD_LABELS.get(key, key), val)
            continue
        if "|" in t and t.count("|") >= 2:
            cells = [c.strip() for c in t.strip("|").split("|") if c.strip()]
            if len(cells) >= 2 and not all(re.match(r"^:?-{3,}:?$", c) for c in cells):
                if cells[0] not in ("字段", "指标") or cells[1] not in ("内容", "数值"):
                    add(cells[0], cells[1])
            continue
        m_zh = _ZH_KV_LINE.match(t)
        if m_zh and not t.startswith("|"):
            add(m_zh.group(1), m_zh.group(2))
    return rows


def is_degraded_data_tab_body(body: str) -> bool:
    s = (body or "").strip()
    if not s:
        return True
    if '{"' in s or re.search(r'"\w+"\s*:\s*', s):
        return True
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    en_kv = sum(1 for ln in lines if _EN_KV_LINE.match(ln))
    if en_kv >= 2:
        return True
    if re.search(r"\|\s*字段\s*\|\s*内容\s*\|", s) and en_kv >= 1:
        return True
    data_rows = 0
    for ln in lines:
        if "|" not in ln or re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", ln):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|") if c.strip()]
        if len(cells) >= 2 and cells[0] not in ("字段", "指标", "内容"):
            if not all(re.match(r"^:?-{3,}:?$", c) for c in cells):
                data_rows += 1
    if data_rows == 0 and (en_kv >= 1 or "```" in s):
        return True
    return False


def _strip_junk_from_data_tab_body(body: str) -> str:
    s = sanitize_stored_text_field(body)
    s = re.sub(r"```json\s*[\s\S]*?```", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<details>[\s\S]*?</details>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"##\s*连接器同步快照[\s\S]*?(?=\n##\s|$)", "", s)
    kept: list[str] = []
    for line in s.splitlines():
        t = line.strip()
        if _EN_KV_LINE.match(t):
            continue
        if t.startswith(">") and "原始摘录" in t:
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{4,}", "\n\n\n", out).strip()
    return out


def _normalize_markdown_tables(md: str) -> str:
    if not md or "|" not in md:
        return md

    def is_table_row(line: str) -> bool:
        t = line.strip()
        return bool(t) and "|" in t and re.match(r"^\|?.+\|", t)

    def parse_cells(line: str) -> list[str]:
        t = line.strip()
        if t.startswith("|"):
            t = t[1:]
        if t.endswith("|"):
            t = t[:-1]
        return [c.strip() for c in t.split("|")]

    def is_sep(cells: list[str]) -> bool:
        return bool(cells) and all(re.match(r"^:?-{3,}:?$", c) for c in cells)

    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if not is_table_row(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        block: list[str] = []
        while i < len(lines) and is_table_row(lines[i]):
            block.append(lines[i])
            i += 1
        parsed = [parse_cells(r) for r in block]
        if not parsed:
            continue
        if len(parsed) == 1 or not is_sep(parsed[1]):
            cols = max(len(r) for r in parsed)
            parsed.insert(1, ["---"] * cols)
        max_cols = max(len(r) for r in parsed)
        for idx, cells in enumerate(parsed):
            if idx == 1 and is_sep(cells):
                out.append("| " + " | ".join(["---"] * max_cols) + " |")
            else:
                padded = cells + [""] * (max_cols - len(cells))
                out.append("| " + " | ".join(padded[:max_cols]) + " |")
    return "\n".join(out)


def prepare_detail_data_tab_body(
    body_md: str,
    *,
    admin_source_key: str = "",
    source_original_url: str = "",
    snippet: str = "",
) -> str:
    """
    详情页「数据支撑」：修复乱码、去掉英文 key 行与 JSON 残渣，必要时重建 GFM 表格。
    """
    from .domain.articles import build_connector_data_tab_markdown

    raw = sanitize_stored_text_field(body_md)
    if not raw.strip():
        url = (source_original_url or "").strip()
        return _rows_to_data_tab_markdown([("原文链接", url)]) if url else ""

    snippet = _extract_json_snippet_from_body(raw) or (snippet or "").strip()
    if snippet:
        rebuilt = build_connector_data_tab_markdown(admin_source_key, snippet)
        if rebuilt.strip():
            return rebuilt

    if is_degraded_data_tab_body(raw):
        rows = _extract_rows_from_degraded_body(raw)
        url = (source_original_url or "").strip()
        if url and not any(r[0] == "原文链接" for r in rows):
            rows.append(("原文链接", url))
        if rows:
            return _rows_to_data_tab_markdown(rows)
        if url:
            return _rows_to_data_tab_markdown([("原文链接", url)])

    cleaned = _strip_junk_from_data_tab_body(raw)
    cleaned = _normalize_markdown_tables(cleaned)
    cleaned = re.sub(r"(?m)^##\s*数据支撑\s*\n+", "", cleaned).strip()
    if cleaned and not cleaned.lstrip().startswith("##"):
        cleaned = f"## 数据支撑\n\n{cleaned}"
    return cleaned or raw
