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
  variant: "spotlight" | "tile" | "rank";
  rank?: number;
  detailLink?: boolean;
};

export function HomeArticleTile({ item, variant, rank, detailLink = false }: Props) {
  const { t } = useI18n();
  const accent = platformAccent(item.admin_source_key || "");
  const engagement = itemEngagementLine(item);
  const highlights = (item.card_highlights || "").trim();
  const categories = item.categories?.slice(0, 2) ?? [];

  const metaRow = (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${accent.badge}`}>
        {item.platform_label || t("source")}
      </span>
      <HomeHeatBadge heat={item.heat_score} />
      {engagement ? <span className="font-semibold tabular-nums text-amber-700">{engagement}</span> : null}
      <span className="tabular-nums">{timeAgo(item.published_at)}</span>
    </div>
  );

  const body = (
    <>
      {variant === "spotlight" ? (
        <div className={`relative overflow-hidden rounded-xl ring-1 ${accent.ring}`}>
          <ArticleCoverVisual
            coverUrl={item.cover_image_url}
            title={item.title || ""}
            seed={`spot-${item.id}`}
            fallbackClassName="flex h-44 w-full items-center justify-center sm:h-52"
            imgClassName="h-44 w-full object-cover sm:h-52"
            initialClassName="text-5xl font-black text-white/90"
          />
        </div>
      ) : null}

      {variant === "tile" ? (
        <div className={`relative h-28 overflow-hidden rounded-lg ring-1 ${accent.ring}`}>
          <ArticleCoverVisual
            coverUrl={item.cover_image_url}
            title={item.title || ""}
            seed={`tile-${item.id}`}
            fallbackClassName="flex h-full w-full items-center justify-center"
            imgClassName="h-full w-full object-cover"
            initialClassName="text-3xl font-black text-white/90"
          />
        </div>
      ) : null}

      {variant === "rank" && rank != null ? (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-sm font-bold text-violet-700 ring-1 ring-violet-100">
          {rank}
        </span>
      ) : null}

      {variant === "rank" ? (
        <div className={`relative h-14 w-14 shrink-0 overflow-hidden rounded-xl ring-1 ${accent.ring}`}>
          <ArticleCoverVisual
            coverUrl={item.cover_image_url}
            title={item.title || ""}
            seed={`rank-${item.id}`}
            fallbackClassName="flex h-full w-full items-center justify-center"
            imgClassName="h-full w-full object-cover"
            initialClassName="text-lg font-bold text-white/90"
          />
        </div>
      ) : null}

      <div className={variant === "rank" ? "min-w-0 flex-1" : ""}>
        {metaRow}
        <h3
          className={
            variant === "spotlight"
              ? "mt-3 line-clamp-2 text-xl font-bold leading-snug text-slate-900 sm:text-2xl"
              : variant === "tile"
                ? "mt-3 line-clamp-2 text-sm font-bold leading-snug text-slate-900"
                : "mt-1 line-clamp-1 text-sm font-semibold text-slate-900 sm:text-[15px]"
          }
        >
          {item.title}
        </h3>
        <p
          className={
            variant === "spotlight"
              ? "mt-2 line-clamp-3 text-sm leading-relaxed text-slate-600 sm:text-[15px]"
              : variant === "tile"
                ? "mt-2 line-clamp-2 text-xs leading-relaxed text-slate-600"
                : "mt-1 line-clamp-2 text-xs leading-snug text-slate-500"
          }
        >
          {itemBlurb(item, variant === "spotlight" ? 200 : variant === "tile" ? 100 : 72)}
        </p>
        {highlights && variant !== "rank" ? (
          <p className="mt-2 line-clamp-2 text-xs font-medium leading-snug text-violet-800/90">
            <span className="text-violet-600">{t("homeHighlightsLabel")}: </span>
            {highlights}
          </p>
        ) : null}
        {categories.length > 0 && variant === "tile" ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {categories.map((c) => (
              <span key={c} className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600">
                {c}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </>
  );

  const className =
    variant === "spotlight"
      ? "ui-card overflow-hidden p-4 sm:p-5"
      : variant === "tile"
        ? "ui-card flex h-full flex-col p-3 sm:p-4"
        : "flex gap-3 rounded-xl border border-transparent p-2 sm:p-3";

  if (detailLink) {
    return (
      <Link to={`/resources/${item.id}`} className={`group block transition hover:shadow-lg ${className}`}>
        {body}
      </Link>
    );
  }

  return <article className={className}>{body}</article>;
}
