import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { ArticleFeedCard } from "@/api/public";
import { ArticleCoverVisual } from "@/components/ArticleCoverVisual";
import { useI18n } from "@/i18n";
import { HomeHeatBadge } from "./HomeHeatBadge";
import { itemBlurb, itemEngagementLine, platformAccent, replicationTierLabel, showReplicationTierOnCard } from "./homeUtils";

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
};

function hasCoverUrl(item: ArticleFeedCard): boolean {
  return Boolean((item.cover_image_url || "").trim());
}

function CoverFrame({
  item,
  seed,
  className,
  aspectClass,
  fallbackMode = "pattern",
  initialClassName,
}: {
  item: ArticleFeedCard;
  seed: string;
  className: string;
  aspectClass: string;
  fallbackMode?: "initial" | "pattern";
  initialClassName?: string;
}) {
  return (
    <div className={`relative overflow-hidden ${aspectClass} ${className}`}>
      <ArticleCoverVisual
        coverUrl={item.cover_image_url}
        title={item.title || ""}
        seed={seed}
        fallbackMode={fallbackMode}
        fallbackClassName="absolute inset-0 h-full w-full"
        imgClassName="absolute inset-0 h-full w-full object-cover"
        initialClassName={initialClassName}
      />
    </div>
  );
}

function MetaRow({ item }: { item: ArticleFeedCard }) {
  const { t } = useI18n();
  const accent = platformAccent(item.admin_source_key || "");
  const engagement = itemEngagementLine(item);
  const showTier = showReplicationTierOnCard(item.feed_kind);
  const tierLabel = showTier ? replicationTierLabel(item.replication_tier) : null;
  const tier = (item.replication_tier || "").trim().toUpperCase();
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${accent.badge}`}>
        {item.platform_label || t("source")}
      </span>
      {showTier && tierLabel ? (
        <span className="rounded-md bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-800" title={`可复刻性 ${tier} 档`}>
          {tierLabel}
        </span>
      ) : null}
      <HomeHeatBadge heat={item.heat_score} />
      {engagement ? <span className="font-semibold tabular-nums text-amber-700">{engagement}</span> : null}
      <span className="tabular-nums text-slate-400">{timeAgo(item.display_at ?? item.published_at)}</span>
    </div>
  );
}

export function HomeArticleTile({ item, variant, rank }: Props) {
  const { t } = useI18n();
  const highlights = (item.card_highlights || "").trim();
  const categories = item.categories?.slice(0, 2) ?? [];

  let inner: ReactNode;

  if (variant === "spotlight") {
    const showCover = hasCoverUrl(item);
    inner = (
      <div
        className={
          showCover ? "grid overflow-hidden lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]" : ""
        }
      >
        {showCover ? (
          <CoverFrame
            item={item}
            seed={`spot-${item.id}`}
            className="ring-0"
            aspectClass="aspect-[16/9] w-full sm:aspect-[2/1] lg:aspect-[4/3] lg:max-h-[280px]"
            fallbackMode="initial"
            initialClassName="select-none text-5xl font-black text-white drop-shadow-lg sm:text-6xl"
          />
        ) : null}
        <div
          className={`flex flex-col justify-center gap-3 p-4 sm:p-5 ${showCover ? "lg:border-l lg:border-slate-100" : ""}`}
        >
          <MetaRow item={item} />
          <h3 className="line-clamp-3 text-xl font-bold leading-snug text-slate-900 sm:text-2xl">{item.title}</h3>
          <p className="line-clamp-4 text-sm leading-relaxed text-slate-600">{itemBlurb(item, 220)}</p>
          {highlights ? (
            <p className="line-clamp-2 rounded-lg bg-violet-50/80 px-3 py-2 text-xs leading-relaxed text-violet-900/90">
              <span className="font-semibold text-violet-700">{t("homeHighlightsLabel")}: </span>
              {highlights}
            </p>
          ) : null}
        </div>
      </div>
    );
  } else if (variant === "tile") {
    inner = (
      <div className="flex min-h-[6.75rem] flex-col overflow-hidden sm:flex-row sm:items-stretch">
        <CoverFrame
          item={item}
          seed={`tile-${item.id}`}
          className="relative h-36 w-full shrink-0 ring-0 sm:h-auto sm:min-h-[6.75rem] sm:w-36 sm:self-stretch md:w-40"
          aspectClass="h-full w-full sm:aspect-auto"
          fallbackMode="initial"
          initialClassName="select-none text-3xl font-black text-white drop-shadow-md sm:text-4xl"
        />
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-2 p-3.5 sm:p-4">
          <MetaRow item={item} />
          <h3 className="line-clamp-2 text-sm font-bold leading-snug text-slate-900">{item.title}</h3>
          <p className="line-clamp-2 flex-1 text-xs leading-relaxed text-slate-600">{itemBlurb(item, 120)}</p>
          {categories.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {categories.map((c) => (
                <span key={c} className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-600">
                  {c}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  } else {
    inner = (
      <div className="flex items-center gap-3 p-3 sm:gap-4 sm:p-3.5">
        {rank != null ? (
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-50 text-sm font-bold text-violet-700 ring-1 ring-violet-100">
            {rank}
          </span>
        ) : null}
        <CoverFrame
          item={item}
          seed={`rank-${item.id}`}
          className="h-14 w-14 shrink-0 rounded-xl ring-1 ring-slate-200/80"
          aspectClass="h-14 w-14"
          fallbackMode="initial"
          initialClassName="select-none text-lg font-black text-white drop-shadow-md"
        />
        <div className="min-w-0 flex-1">
          <MetaRow item={item} />
          <h3 className="mt-1 line-clamp-1 text-sm font-semibold text-slate-900">{item.title}</h3>
          <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-slate-500">{itemBlurb(item, 80)}</p>
        </div>
      </div>
    );
  }

  const className =
    variant === "spotlight"
      ? "ui-card group block overflow-hidden transition hover:shadow-md"
      : variant === "tile"
        ? "ui-card group block h-full overflow-hidden transition hover:border-violet-200/80 hover:shadow-sm"
        : "group block transition hover:bg-slate-50/80";

  return (
    <Link to={`/resources/${item.id}`} className={className}>
      {inner}
    </Link>
  );
}
