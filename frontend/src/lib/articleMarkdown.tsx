import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { prefixTocItemIds, parseMarkdownToc, type TocItem } from "@/lib/markdownToc";

/** 详情页不展示连接器原始 JSON / 摘录块 */
export function sanitizeArticleMarkdown(md: string): string {
  let s = (md || "").trim();
  if (!s) return "";
  s = s.replace(/```json\s*[\s\S]*?```/gi, "");
  s = s.replace(/<details>[\s\S]*?<\/details>/gi, "");
  s = s.replace(/>\s*\*\*原始摘录\*\*[\s\S]*?(?=\n##\s|\n#\s|$)/gi, "");
  s = s.replace(/##\s*连接器同步快照[\s\S]*?(?=\n##\s|$)/gi, "");
  s = s.replace(/\n{4,}/g, "\n\n\n");
  return s.trim();
}

function isMarkdownTableRow(line: string): boolean {
  const t = line.trim();
  return t.length > 0 && t.includes("|") && /^\|?.+\|/.test(t);
}

function isMarkdownTableSeparatorRow(line: string): boolean {
  const cells = parseMarkdownTableCells(line);
  if (!cells.length) return false;
  return cells.every((c) => /^:?-{3,}:?$/.test(c));
}

function parseMarkdownTableCells(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

function formatMarkdownTableRow(cells: string[]): string {
  return `| ${cells.join(" | ")} |`;
}

/** 修复 LLM 常出的表格：补分隔行、统一列数，供 remark-gfm 正确解析 */
export function normalizeMarkdownTables(md: string): string {
  if (!md || !/^\s*\|/m.test(md)) return md;
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    if (!isMarkdownTableRow(lines[i])) {
      out.push(lines[i]);
      i += 1;
      continue;
    }
    const block: string[] = [];
    while (i < lines.length && isMarkdownTableRow(lines[i])) {
      block.push(lines[i]);
      i += 1;
    }
    out.push(...repairMarkdownTableBlock(block));
  }
  return out.join("\n");
}

function repairMarkdownTableBlock(rows: string[]): string[] {
  if (!rows.length) return rows;
  const parsed = rows.map(parseMarkdownTableCells);
  const fixed: string[][] = parsed.map((r) => [...r]);
  if (fixed.length === 1 || !isMarkdownTableSeparatorRow(rows[1] ?? "")) {
    const cols = Math.max(...fixed.map((r) => r.length), 1);
    fixed.splice(1, 0, Array.from({ length: cols }, () => "---"));
  }
  const maxCols = Math.max(...fixed.map((r) => r.length), 1);
  return fixed.map((cells, idx) => {
    if (idx === 1 && cells.every((c) => /^:?-{3,}:?$/.test(c) || c === "---")) {
      return formatMarkdownTableRow(Array.from({ length: maxCols }, () => "---"));
    }
    const padded = cells.slice(0, maxCols);
    while (padded.length < maxCols) padded.push("");
    return formatMarkdownTableRow(padded);
  });
}

/** 长段纯叙述无空行时，按句号拆成段落（跳过含 Markdown 表格的正文） */
export function ensureParagraphBreaks(md: string): string {
  const s = md;
  if (!s || /\n\n/.test(s)) return s;
  if (/^\s*\|[^\n]+\|/m.test(s)) return s;
  const first = s.split("\n")[0] ?? "";
  if (/^\s*[-*#|>]/.test(first)) return s;
  const parts = s.split(/(?<=[。！？])\s+/).map((p) => p.trim()).filter(Boolean);
  if (parts.length <= 2) return s;
  return parts.join("\n\n");
}

/** 列表卡片「数据支撑」预览：去掉表格竖线、代码块等，避免像乱码 */
export function markdownToPlainPreview(md: string, maxLen = 500): string {
  let s = (md || "").trim();
  if (!s) return "";
  s = s.replace(/```[\s\S]*?```/g, " ");
  s = s.replace(/`([^`]+)`/g, "$1");
  const linesOut: string[] = [];
  for (const line of s.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    if (/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(t)) continue;
    if (t.includes("|") && (t.match(/\|/g)?.length ?? 0) >= 2) {
      const cells = t
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((c) => c.trim())
        .filter(Boolean);
      if (cells.length >= 2 && !cells.every((c) => /^:?-{3,}:?$/.test(c))) {
        linesOut.push(`${cells[0]}：${cells[1]}`);
        continue;
      }
    }
    const plain = t
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/^#+\s*/, "")
      .replace(/^[-*+]\s+/, "")
      .replace(/\s+/g, " ")
      .trim();
    if (plain) linesOut.push(plain);
  }
  let out = linesOut.length ? linesOut.join("；") : s.replace(/\s+/g, " ").trim();
  if (maxLen > 0 && out.length > maxLen) out = `${out.slice(0, maxLen - 1)}…`;
  return out;
}

/** 与后端 TabTextRole 对齐：描述 / 复刻评估 / 数据类（含报道依据等 i18n 标题） */
export type ArticleTabRenderRole = "description" | "replication" | "data";

const TAB_SECTION_HEADING_RE = /^##\s*(数据支撑|功能亮点|要点|报道依据|描述|变现评估|复刻评估)\s*$/gm;

function stripEnglishKeyLines(md: string): string {
  return md
    .split("\n")
    .filter((line) => {
      const t = line.trim();
      if (!t) return true;
      return !/^[a-zA-Z_][a-zA-Z0-9_]*\s*[:：]\s*.+/.test(t);
    })
    .join("\n");
}

function stripTabSectionHeadings(md: string): string {
  return md.replace(TAB_SECTION_HEADING_RE, "").replace(/\n{4,}/g, "\n\n\n").trim();
}

/** 详情各区块统一 Markdown 预处理（后端已规范化时作二次兜底） */
export function prepareArticleTabMarkdown(md: string, role: ArticleTabRenderRole): string {
  let cleaned = sanitizeArticleMarkdown(md);
  cleaned = stripEnglishKeyLines(cleaned);
  if (role === "data" || role === "description") {
    cleaned = stripTabSectionHeadings(cleaned);
  }
  const withTables = normalizeMarkdownTables(cleaned);
  return ensureParagraphBreaks(withTables);
}

/** @deprecated 使用 prepareArticleTabMarkdown(md, "data") */
export function prepareDataTabMarkdown(md: string): string {
  return prepareArticleTabMarkdown(md, "data");
}

/** @deprecated 使用 prepareArticleTabMarkdown(md, "description") */
export function prepareDetailMarkdown(md: string): string {
  return prepareArticleTabMarkdown(md, "description");
}

export const ARTICLE_REMARK_PLUGINS = [remarkGfm];

export const ARTICLE_MD_PROSE_CLASS =
  "max-w-none w-full space-y-4 text-slate-600 leading-relaxed " +
  "[&_a]:font-medium [&_a]:text-brand-600 hover:[&_a]:underline " +
  "[&_strong]:text-slate-900 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 " +
  "[&_li]:marker:text-brand-300 [&_p]:mb-4 [&_p:last-child]:mb-0 " +
  "[&_code]:rounded-md [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-slate-800 " +
  "[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-4 " +
  "[&_blockquote]:border-l-4 [&_blockquote]:border-brand-100 [&_blockquote]:pl-4 [&_blockquote]:text-slate-500";

const SCROLL_MARGIN_TOP = "scroll-mt-[5.75rem]";

export function createArticleMarkdownComponents(toc: TocItem[]) {
  const queue = [...toc];
  return {
    h2: ({ children, ...props }: ComponentProps<"h2">) => {
      const t = queue[0]?.level === 2 ? queue.shift() : null;
      const id = t?.id;
      return (
        <h2
          {...props}
          {...(id ? { id, "data-toc-heading": "" } : {})}
          className={`mt-6 text-lg font-bold tracking-tight text-slate-900 ${SCROLL_MARGIN_TOP}`}
        >
          {children}
        </h2>
      );
    },
    h3: ({ children, ...props }: ComponentProps<"h3">) => {
      const t = queue[0]?.level === 3 ? queue.shift() : null;
      const id = t?.id;
      return (
        <h3
          {...props}
          {...(id ? { id, "data-toc-heading": "" } : {})}
          className={`mt-4 text-base font-semibold text-slate-900 ${SCROLL_MARGIN_TOP}`}
        >
          {children}
        </h3>
      );
    },
    p: ({ children, ...props }: ComponentProps<"p">) => (
      <p {...props} className="mb-4 leading-relaxed last:mb-0">
        {children}
      </p>
    ),
    table: ({ children, ...props }: ComponentProps<"table">) => (
      <div
        className="my-4 w-full overflow-x-auto rounded-lg border border-slate-200 bg-white"
        data-testid="article-md-table-wrap"
      >
        <table {...props} className="w-full min-w-full table-auto border-collapse text-left text-sm">
          {children}
        </table>
      </div>
    ),
    thead: ({ children, ...props }: ComponentProps<"thead">) => (
      <thead {...props} className="bg-slate-50">
        {children}
      </thead>
    ),
    th: ({ children, ...props }: ComponentProps<"th">) => (
      <th
        {...props}
        className="whitespace-nowrap border border-slate-200 px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-700"
      >
        {children}
      </th>
    ),
    td: ({ children, ...props }: ComponentProps<"td">) => (
      <td {...props} className="break-words border border-slate-200 px-3 py-2 align-top text-slate-700">
        {children}
      </td>
    ),
    tr: ({ children, ...props }: ComponentProps<"tr">) => (
      <tr {...props} className="even:bg-slate-50/40">
        {children}
      </tr>
    ),
  };
}

export function markdownComponentsForBody(bodyMd: string, prefix: string) {
  const tocItems = prefixTocItemIds(parseMarkdownToc(bodyMd), prefix);
  return createArticleMarkdownComponents(tocItems);
}

type ArticleMarkdownContentProps = {
  bodyMd: string;
  components: ComponentProps<typeof ReactMarkdown>["components"];
};

/** 详情正文：启用 GFM 表格，避免 | 列 | 被当成普通段落 */
export function ArticleMarkdownContent({ bodyMd, components }: ArticleMarkdownContentProps) {
  return (
    <ReactMarkdown remarkPlugins={ARTICLE_REMARK_PLUGINS} components={components}>
      {bodyMd}
    </ReactMarkdown>
  );
}

/** 详情主区：描述 + 复刻评估 + 数据支撑（兼容旧稿「功能亮点」「要点」） */
export const DETAIL_DATA_TAB_LABELS = new Set(["数据支撑", "功能亮点", "要点"]);
export const DETAIL_REPLICATION_TAB_LABEL = "变现评估";

export function pickDetailTabs<T extends { label: string }>(tabs: T[]): T[] {
  if (!tabs.length) return [];
  const desc = tabs.find((t) => t.label === "描述");
  const repl = tabs.find((t) => t.label === DETAIL_REPLICATION_TAB_LABEL);
  const data = tabs.find((t) => DETAIL_DATA_TAB_LABELS.has(t.label));
  if (desc && repl && data) return [desc, repl, data];
  if (desc && data) return [desc, data];
  return tabs.slice(0, 3);
}

export function displayDetailTabLabel(label: string): string {
  if (DETAIL_DATA_TAB_LABELS.has(label) && label !== "数据支撑") return "数据支撑";
  return label;
}
