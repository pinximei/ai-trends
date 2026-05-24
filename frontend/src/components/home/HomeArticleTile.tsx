import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ArticleFeedCard } from "@/api/public";
import { ArticleCoverVisual } from "@/components/ArticleCoverVisual";
import { useI18n } from "@/i18n";
import { HomeHeatBadge } from "./HomeHeatBadge";
import { itemBlurb, itemEngagementLine, platformAccent } from "./homeUtils";

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diff = Date.now() - d.getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "刚刚";
  if (m < 60) return `${m} 分钟前`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} 小时前`;
  return `${Math.floor(h / 24)} 天前`;
}

type Props = {
  item: ArticleFeedCard;
  variant: "feature" | "list" | "grid-mini" | "rank";
  rank?: number;
  detailLink?: boolean;
};

function CoverFrame({
  item,
  seed,
  className,
  aspectClass,
}: {
  item: ArticleFeedCard;
  seed: string;
  className: string;
  aspectClass: string;
}) {
  return (
    <div className={`relative overflow-hidden ${aspectClass} ${className}`}>
      <ArticleCoverVisual
        coverUrl={item.cover_image_url}
        title={item.title || ""}
        seed={seed}
        fallbackMode="pattern"
        fallbackClassName="absolute inset-0"
        imgClassName="absolute inset-0 h-full w-full object-cover"
      />
    </div>
  );
}

function MetaRow({ item, compact = false }: { item: ArticleFeedCard; compact?: boolean }) {
  const { t } = useI18n();
  const accent = platformAccent(item.admin_source_key || "");
  const engagement = itemEngagementLine(item);
  return (
    <div className={`flex flex-wrap items-center gap-x-1.5 gap-y-0.5 ${compact ? "text-[10px]" : "text-xs"} text-slate-500`}>
      <span className={`rounded px-1.5 py-0.5 font-semibold uppercase tracking-wide ${accent.badge} ${compact ? "text-[9px]" : "text-[10px]"}`}>
        {item.platform_label || t("source")}
      </span>
      <HomeHeatBadge heat={item.heat_score} />
      {engagement ? <span className="font-semibold tabular-nums text-amber-700">{engagement}</span> : null}
      <span className="tabular-nums text-slate-400">{timeAgo(item.published_at)}</span>
    </div>
  );
}

export function HomeArticleTile({ item, variant, rank, detailLink = false }: Props) {
  const { t } = useI18n();
  const highlights = (item.card_highlights || "").trim();

  let inner: ReactNode;

  if (variant === "feature") {
    inner = (
      <div className="flex min-h-0 flex-col gap-3 sm:flex-row sm:gap-4">
        <CoverFrame
          item={item}
          seed={`feat-${item.id}`}
          className="shrink-0 rounded-lg ring-1 ring-slate-200/80 sm:w-[42%]"
          aspectClass="aspect-[16/10] w-full sm:aspect-[4/3] sm:min-h-[11rem]"
        />
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 py-0.5 sm:py-2">
          <MetaRow item={item} />
          <h3 className="line-clamp-3 text-lg font-bold leading-snug text-slate-900 sm:text-xl">{item.title}</h3>
          <p className="line-clamp-3 text-sm leading-relaxed text-slate-600">{itemBlurb(item, 160)}</p>
          {highlights ? (
            <p className="line-clamp-2 text-xs leading-snug text-violet-800/90">
              <span className="font-semibold text-violet-600">{t("homeHighlightsLabel")}: </span>
              {highlights}
            </p>
          ) : null}
        </div>
      </div>
    );
  } else if (variant === "list") {
    inner = (
      <div className="flex gap-2.5 py-2">
        <CoverFrame
          item={item}
          seed={`list-${item.id}`}
          className="h-[4.25rem] w-[4.25rem] shrink-0 rounded-md ring-1 ring-slate-200/80"
          aspectClass="h-full w-full"
        />
        <div className="min-w-0 flex-1">
          <MetaRow item={item} compact />
          <h3 className="mt-1 line-clamp-2 text-sm font-semibold leading-snug text-slate-900">{item.title}</h3>
        </div>
      </div>
    );
  } else if (variant === "grid-mini") {
    inner = (
      <div className="flex h-full flex-col overflow-hidden">
        <CoverFrame
          item={item}
          seed={`mini-${item.id}`}
          className="ring-0"
          aspectClass="aspect-[16/10] w-full"
        />
        <div className="flex flex-1 flex-col gap-1.5 p-2.5">
          <MetaRow item={item} compact />
          <h3 className="line-clamp-2 text-xs font-bold leading-snug text-slate-900">{item.title}</h3>
        </div>
      </div>
    );
  } else {
    inner = (
      <div className="flex items-center gap-2.5 px-2 py-2 sm:px-3">
        {rank != null ? (
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-violet-50 text-xs font-bold text-violet-700">
            {rank}
          </span>
        ) : null}
        <CoverFrame
          item={item}
          seed={`rank-${item.id}`}
          className="h-11 w-11 shrink-0 rounded-lg ring-1 ring-slate-200/80"
          aspectClass="h-full w-full"
        />
        <div className="min-w-0 flex-1">
          <h3 className="line-clamp-1 text-sm font-semibold text-slate-900">{item.title}</h3>
          <p className="mt-0.5 line-clamp-1 text-[11px] text-slate-500">{itemBlurb(item, 56)}</p>
          <div className="mt-1">
            <MetaRow item={item} compact />
          </div>
        </div>
      </div>
    );
  }

  const className =
    variant === "feature"
      ? "block transition hover:opacity-95"
      : variant === "list"
        ? "block border-b border-slate-100 last:border-0 transition hover:bg-slate-50/80"
        : variant === "grid-mini"
          ? "ui-card h-full overflow-hidden transition hover:border-violet-200/70 hover:shadow-sm"
          : "transition hover:bg-slate-50/80";

  if (detailLink) {
    return (
      <Link to={`/resources/${item.id}`} className={`group ${className}`}>
        {inner}
      </Link>
    );
  }

  return <article className={className}>{inner}</article>;
}
