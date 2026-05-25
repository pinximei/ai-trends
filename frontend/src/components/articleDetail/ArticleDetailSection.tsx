import { ARTICLE_MD_PROSE_CLASS, ArticleMarkdownContent } from "@/lib/articleMarkdown";
import type { DetailLayoutConfig, DetailSectionKind } from "@/lib/articleDetailLayout";
import { sectionDomId } from "@/lib/articleDetailLayout";
import type { ComponentProps } from "react";
import type ReactMarkdown from "react-markdown";

type Props = {
  kind: DetailSectionKind;
  layout: DetailLayoutConfig;
  title: string;
  summary: string;
  bodyMd: string;
  components: ComponentProps<typeof ReactMarkdown>["components"];
};

export function ArticleDetailSection({ kind, layout, title, summary, bodyMd, components }: Props) {
  const isData = kind === "data";
  const panelClass = isData ? layout.dataPanelClass : "border-slate-100 bg-white";

  return (
    <section
      id={sectionDomId(kind)}
      className={`ui-card overflow-hidden scroll-mt-[5.75rem] border ${panelClass}`}
      aria-labelledby={`${sectionDomId(kind)}-heading`}
      data-testid={`resource-detail-section-${kind}`}
    >
      <div
        className={
          isData
            ? "border-b border-inherit px-5 py-4 sm:px-6"
            : "border-b border-slate-100 bg-slate-50/90 px-5 py-4 sm:px-6"
        }
      >
        <h2 id={`${sectionDomId(kind)}-heading`} className="text-base font-semibold tracking-tight text-slate-900">
          {title}
        </h2>
        {summary ? <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{summary}</p> : null}
      </div>
      <div className={`p-5 sm:p-8 ${ARTICLE_MD_PROSE_CLASS}`}>
        <ArticleMarkdownContent bodyMd={bodyMd} components={components} />
      </div>
    </section>
  );
}
