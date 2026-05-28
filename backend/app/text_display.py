"""前台卡片摘要、Tab 文案：编码修复与 Markdown 转可读纯文本。"""
from __future__ import annotations

import json
import re
from typing import Literal

TabTextRole = Literal["description", "replication", "data"]


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


def github_connector_snippet_from_article_fields(
    *,
    source_original_url: str = "",
    summary: str = "",
    engagement_stars_total: int | None = None,
    title: str = "",
) -> str:
    """GitHub 稿详情页：用已入库字段拼连接器 snippet，重建「数据支撑」表。"""
    url = (source_original_url or "").strip()
    full_name = ""
    if "github.com/" in url:
        parts = url.split("github.com/", 1)[-1].strip("/").split("/")
        if len(parts) >= 2:
            full_name = f"{parts[0]}/{parts[1]}"
    payload: dict[str, object] = {
        "full_name": full_name or None,
        "html_url": url or None,
        "stargazers_count": engagement_stars_total,
        "description": (summary or title or "").strip()[:500] or None,
    }
    clean = {k: v for k, v in payload.items() if v is not None and str(v).strip()}
    return json.dumps(clean, ensure_ascii=False) if clean else ""


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


def _find_json_object_spans(text: str, *, min_len: int = 40) -> list[tuple[int, int]]:
    """按括号深度定位 JSON 对象片段（用于剥离内联 GitHub/API 响应）。"""
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        for j in range(i, n):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    if j - i + 1 >= min_len:
                        spans.append((i, j + 1))
                    i = j + 1
                    break
        else:
            i += 1
    return spans


def _is_connector_api_json(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    api_keys = frozenset(
        {
            "node_id",
            "html_url",
            "stargazers_count",
            "full_name",
            "avatar_url",
            "gravatar_id",
            "followers_url",
            "private",
            "owner",
            "license",
            "default_branch",
        }
    )
    return len(api_keys & obj.keys()) >= 3


def _strip_github_api_junk_lines(text: str) -> str:
    """剥离无法 json.loads 的 GitHub API 残片（表格单元格、断行 JSON）。"""
    api_markers = (
        '"node_id"',
        '"stargazers_count"',
        '"followers_url"',
        '"gravatar_id"',
        '"avatar_url"',
        '"stargazers_url"',
        '"subscriptions_url"',
    )
    kept: list[str] = []
    for line in (text or "").splitlines():
        t = line.strip()
        if not t:
            kept.append(line)
            continue
        if any(m in t for m in api_markers):
            continue
        if re.search(r"\bnode_id\s*=", t, re.I) or re.search(r"^\s*id\s*=\s*\d", t, re.I):
            continue
        if t.startswith('{"id":') or t.startswith("| {") or t.startswith("|{"):
            continue
        if re.search(r'"\w+"\s*:\s*', t) and re.search(
            r"(node_id|html_url|full_name|private|owner\s*:)",
            t,
        ):
            continue
        kept.append(line)
    out = "\n".join(kept)
    return re.sub(r"\n{4,}", "\n\n\n", out).strip()


def _strip_inline_json_blobs(text: str) -> str:
    """去掉正文里整段连接器/API JSON（常见于 GitHub 润色泄漏）。"""
    s = text or ""
    if not s or "{" not in s:
        return s.strip()
    spans = _find_json_object_spans(s, min_len=80)
    if not spans:
        return _strip_github_api_junk_lines(s)
    remove: list[tuple[int, int]] = []
    for start, end in spans:
        chunk = s[start:end]
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if _is_connector_api_json(obj) or (isinstance(obj, dict) and len(chunk) > 400):
            remove.append((start, end))
    if not remove:
        return _strip_github_api_junk_lines(s)
    out: list[str] = []
    pos = 0
    for start, end in remove:
        out.append(s[pos:start])
        pos = end
    out.append(s[pos:])
    cleaned = "".join(out)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return _strip_github_api_junk_lines(cleaned)


def _extract_json_snippet_from_body(body: str) -> str:
    m = re.search(r"```json\s*([\s\S]*?)\s*```", body, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    s = body.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError:
            pass
    best = ""
    for start, end in _find_json_object_spans(s, min_len=20):
        chunk = s[start:end]
        try:
            json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if len(chunk) > len(best):
            best = chunk
    return best


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


_TAB_SECTION_HEADING_RE = re.compile(
    r"(?m)^##\s*(数据支撑|功能亮点|要点|报道依据|描述|变现评估|复刻评估)\s*\n+"
)


def tab_text_role_from_label(label: str) -> TabTextRole | None:
    """规范 Tab label → 文案处理角色（与详情 i18n 标题无关，如「报道依据」仍走 data）。"""
    from .domain.articles import (
        FEED_CARD_TAB_DESCRIPTION,
        canonical_feed_card_tab_label,
        feed_card_highlights_tab_label,
    )
    from .domain.replication_analysis import FEED_CARD_TAB_REPLICATION

    lab = canonical_feed_card_tab_label((label or "").strip())
    if lab == FEED_CARD_TAB_DESCRIPTION:
        return "description"
    if lab == FEED_CARD_TAB_REPLICATION:
        return "replication"
    if feed_card_highlights_tab_label(lab):
        return "data"
    return None


def _strip_tab_markdown_junk(body: str) -> str:
    """各 Tab 通用：去 JSON 块、连接器快照、英文 key 行等。"""
    s = sanitize_stored_text_field(body)
    s = re.sub(r"```json\s*[\s\S]*?```", "", s, flags=re.IGNORECASE)
    s = re.sub(r"<details>[\s\S]*?</details>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"##\s*连接器同步快照[\s\S]*?(?=\n##\s|$)", "", s)
    s = _strip_inline_json_blobs(s)
    s = _strip_github_api_junk_lines(s)
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


def _strip_tab_section_headings(body: str) -> str:
    return _TAB_SECTION_HEADING_RE.sub("", (body or "").strip()).strip()


def _ensure_paragraph_breaks(md: str) -> str:
    s = (md or "").strip()
    if not s or re.search(r"\n\n", s):
        return s
    if re.search(r"^\s*\|", s, re.MULTILINE):
        return s
    first = (s.split("\n")[0] or "").strip()
    if re.match(r"^[-*#|>]", first):
        return s
    parts = [p.strip() for p in re.split(r"(?<=[。！？])\s+", s) if p.strip()]
    if len(parts) <= 2:
        return s
    return "\n\n".join(parts)


def prepare_description_tab_body(body_md: str, *, admin_source_key: str = "") -> str:
    """描述 Tab：去残渣、修表格与段落，避免混入连接器 JSON。"""
    _ = admin_source_key
    raw = sanitize_stored_text_field(body_md)
    if not raw.strip():
        return ""
    cleaned = _strip_tab_markdown_junk(raw)
    cleaned = _strip_tab_section_headings(cleaned)
    if is_degraded_data_tab_body(cleaned):
        snippet = _extract_json_snippet_from_body(raw)
        if snippet:
            plain = format_connector_snippet_plain(snippet, admin_source_key=admin_source_key or "github")
            if plain and len(re.findall(r"[\u4e00-\u9fff]", cleaned)) >= 24:
                cleaned = f"{cleaned.rstrip()}\n\n---\n\n**仓库要点**\n\n{plain}"
            elif plain:
                cleaned = plain
        cleaned = _strip_inline_json_blobs(cleaned)
    if is_degraded_data_tab_body(cleaned) and len(re.findall(r"[\u4e00-\u9fff]", cleaned)) < 24:
        rows = _extract_rows_from_degraded_body(cleaned)
        if rows:
            return "\n\n".join(f"**{lab}**：{val}" for lab, val in rows[:10])
    cleaned = _normalize_markdown_tables(cleaned)
    cleaned = _ensure_paragraph_breaks(cleaned)
    return cleaned or raw


def prepare_replication_tab_body(body_md: str) -> str:
    """复刻评估 Tab：去 JSON/英文 key，保留列表与段落结构。"""
    raw = sanitize_stored_text_field(body_md)
    if not raw.strip():
        return ""
    cleaned = _strip_tab_markdown_junk(raw)
    cleaned = _strip_tab_section_headings(cleaned)
    cleaned = _normalize_markdown_tables(cleaned)
    cleaned = _ensure_paragraph_breaks(cleaned)
    return cleaned or raw


def _strip_junk_from_data_tab_body(body: str) -> str:
    return _strip_tab_markdown_junk(body)


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


def prepare_data_tab_body(
    body_md: str,
    *,
    admin_source_key: str = "",
    source_original_url: str = "",
    snippet: str = "",
) -> str:
    """
    数据类 Tab（数据支撑 / 报道依据 / 旧「要点」等）：修复乱码、重建 GFM 表格。
    """
    from .domain.articles import build_connector_data_tab_markdown

    raw = sanitize_stored_text_field(body_md)
    if not raw.strip():
        url = (source_original_url or "").strip()
        return _rows_to_data_tab_markdown([("原文链接", url)]) if url else ""

    passed_snippet = (snippet or "").strip()
    if passed_snippet and (admin_source_key or "").strip().lower() == "github":
        rebuilt = build_connector_data_tab_markdown(admin_source_key, passed_snippet)
        if rebuilt.strip():
            return rebuilt

    snippet = _extract_json_snippet_from_body(raw) or passed_snippet
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
    cleaned = _strip_tab_section_headings(cleaned)
    if cleaned and not cleaned.lstrip().startswith("##"):
        cleaned = f"## 数据支撑\n\n{cleaned}"
    return cleaned or raw


prepare_detail_data_tab_body = prepare_data_tab_body


def normalize_tab_for_display(
    tab: dict,
    *,
    admin_source_key: str = "",
    source_original_url: str = "",
    snippet: str = "",
) -> dict[str, str] | None:
    """单 Tab 读出/展示前统一规范化（label 已规范名）。"""
    from .domain.articles import canonical_feed_card_tab_label

    if not isinstance(tab, dict):
        return None
    label = canonical_feed_card_tab_label(str(tab.get("label") or "").strip())
    role = tab_text_role_from_label(label)
    if not role:
        return None
    body_in = str(tab.get("body_md") or "")
    summary_in = str(tab.get("summary") or "")
    if role == "data":
        body_md = prepare_data_tab_body(
            body_in,
            admin_source_key=admin_source_key,
            source_original_url=source_original_url,
            snippet=snippet,
        )
        summary = markdown_to_plain_preview(summary_in or body_md, max_len=400)
    elif role == "description":
        body_md = prepare_description_tab_body(body_in, admin_source_key=admin_source_key)
        summary = markdown_to_plain_preview(summary_in or body_md, max_len=512)
    else:
        body_md = prepare_replication_tab_body(body_in)
        summary = markdown_to_plain_preview(summary_in or body_md, max_len=512)
    if not (summary.strip() and body_md.strip()):
        return None
    return {"label": label, "summary": summary[:2000], "body_md": body_md[:50000]}


def normalize_article_tabs_for_display(
    tabs: list,
    *,
    admin_source_key: str = "",
    source_original_url: str = "",
    snippet: str = "",
) -> list[dict[str, str]]:
    """列表卡片 / 详情页 / 入库前：统一处理全部 Tab 正文与摘要。"""
    out: list[dict[str, str]] = []
    for item in tabs:
        if not isinstance(item, dict):
            continue
        row = normalize_tab_for_display(
            item,
            admin_source_key=admin_source_key,
            source_original_url=source_original_url,
            snippet=snippet,
        )
        if row:
            out.append(row)
    return out
