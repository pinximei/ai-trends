export type TocItem = { id: string; text: string; level: 2 | 3 };

function slugifySegment(raw: string): string {
  const s = raw
    .trim()
    .replace(/[#*`]+/g, "")
    .replace(/[^a-zA-Z0-9\u4e00-\u9fff_]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/-+/g, "-")
    .slice(0, 72);
  return s || "section";
}

/** 从 Markdown 正文提取 ## / ### 作为目录（顺序与正文一致） */
export function parseMarkdownToc(md: string): TocItem[] {
  if (!md.trim()) return [];
  const lines = md.split(/\r?\n/);
  const out: TocItem[] = [];
  const counts = new Map<string, number>();
  for (const line of lines) {
    const m = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (!m) continue;
    const level = m[1].length === 2 ? (2 as const) : (3 as const);
    const text = m[2].trim().replace(/\s+#+\s*$/, "").trim();
    if (!text) continue;
    const base = slugifySegment(text);
    const n = (counts.get(base) ?? 0) + 1;
    counts.set(base, n);
    const id = n === 1 ? base : `${base}-${n}`;
    out.push({ id, text, level });
  }
  return out;
}
