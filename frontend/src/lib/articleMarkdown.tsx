import type { ComponentProps } from "react";
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

/** 长段纯叙述无空行时，按句号拆成段落 */
export function ensureParagraphBreaks(md: string): string {
  const s = sanitizeArticleMarkdown(md);
  if (!s || /\n\n/.test(s)) return s;
  const first = s.split("\n")[0] ?? "";
  if (/^\s*[-*#|>]/.test(first) || /\|/.test(first)) return s;
  const parts = s.split(/(?<=[。！？])\s+/).map((p) => p.trim()).filter(Boolean);
  if (parts.length <= 2) return s;
  return parts.join("\n\n");
}

export function prepareDetailMarkdown(md: string): string {
  return ensureParagraphBreaks(sanitizeArticleMarkdown(md));
}

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
      <div className="my-4 overflow-x-auto rounded-lg border border-slate-200">
        <table {...props} className="w-full min-w-[280px] border-collapse text-left text-sm">
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
      <th {...props} className="border border-slate-200 px-3 py-2 font-semibold text-slate-800">
        {children}
      </th>
    ),
    td: ({ children, ...props }: ComponentProps<"td">) => (
      <td {...props} className="border border-slate-200 px-3 py-2 align-top text-slate-700">
        {children}
      </td>
    ),
    tr: ({ children, ...props }: ComponentProps<"tr">) => (
      <tr {...props} className="even:bg-slate-50/50">
        {children}
      </tr>
    ),
  };
}

export function markdownComponentsForBody(bodyMd: string, prefix: string) {
  const tocItems = prefixTocItemIds(parseMarkdownToc(bodyMd), prefix);
  return createArticleMarkdownComponents(tocItems);
}

/** 详情主区：描述 + 数据支撑（兼容旧稿「功能亮点」「要点」） */
export const DETAIL_DATA_TAB_LABELS = new Set(["数据支撑", "功能亮点", "要点"]);

export function pickDetailTabs<T extends { label: string }>(tabs: T[]): T[] {
  if (!tabs.length) return [];
  const desc = tabs.find((t) => t.label === "描述");
  const data = tabs.find((t) => DETAIL_DATA_TAB_LABELS.has(t.label));
  if (desc && data) return [desc, data];
  return tabs.slice(0, 2);
}

export function displayDetailTabLabel(label: string): string {
  if (DETAIL_DATA_TAB_LABELS.has(label) && label !== "数据支撑") return "数据支撑";
  return label;
}
