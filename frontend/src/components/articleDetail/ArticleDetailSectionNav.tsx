import type { DetailLayoutConfig, DetailSectionKind } from "@/lib/articleDetailLayout";
import { sectionDomId } from "@/lib/articleDetailLayout";

type SectionItem = { kind: DetailSectionKind; label: string; present: boolean };

type Props = {
  layout: DetailLayoutConfig;
  sections: SectionItem[];
  onJump: (id: string) => void;
};

export function ArticleDetailSectionNav({ layout, sections, onJump }: Props) {
  const visible = sections.filter((s) => s.present);
  if (visible.length < 2) return null;

  return (
    <nav
      className="ui-card flex flex-wrap gap-2 p-3 sm:px-4"
      aria-label="详情章节"
      data-testid="resource-detail-section-nav"
    >
      {layout.sectionOrder.map((kind) => {
        const item = visible.find((s) => s.kind === kind);
        if (!item) return null;
        const id = sectionDomId(kind);
        return (
          <button
            key={kind}
            type="button"
            onClick={() => onJump(id)}
            className="rounded-lg border border-slate-200/90 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-700"
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
