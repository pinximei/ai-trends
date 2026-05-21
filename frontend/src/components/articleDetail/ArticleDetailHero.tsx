import type { ReactNode } from "react";
import type { ArticleDetail } from "@/api/public";
import { ArticleCoverVisual } from "@/components/ArticleCoverVisual";
import type { DetailLayoutConfig } from "@/lib/articleDetailLayout";

type Props = {
  article: ArticleDetail;
  layout: DetailLayoutConfig;
  tagline: string;
  profileBadge: string;
  categoryTags: ReactNode;
};

/** 详情页头图：资讯与应用统一为大图/首字母块（与列表卡片比例一致）。 */
function HeroCoverAside({
  cover,
  title,
  seed,
}: {
  cover: string | null | undefined;
  title: string;
  seed: string;
}) {
  return (
    <div className="relative flex min-h-[7rem] w-full shrink-0 overflow-hidden sm:w-36 sm:min-h-[8.5rem] sm:border-r sm:border-slate-200/80">
      <ArticleCoverVisual
        coverUrl={cover}
        title={title}
        seed={seed}
        fallbackClassName="flex min-h-[7rem] w-full items-center justify-center sm:min-h-[8.5rem]"
        imgClassName="h-full w-full min-h-[7rem] object-cover sm:min-h-[8.5rem]"
        initialClassName="select-none text-4xl font-black text-white drop-shadow-md sm:text-5xl"
      />
    </div>
  );
}

export function ArticleDetailHero({ article, layout, tagline, profileBadge, categoryTags }: Props) {
  const dateStr = article.published_at?.slice(0, 10) ?? "";
  const platform = article.platform_label?.trim() || profileBadge;
  const seed = `${article.id}:${article.title || ""}`;
  const cover = article.cover_image_url;
  const title = article.title || "";
  const sourceUrl = (article.source_original_url || "").trim();

  const sourceLinkEl =
    sourceUrl.startsWith("http://") || sourceUrl.startsWith("https://") ? (
      <a
        href={sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-brand-600 shadow-sm hover:border-brand-300 hover:bg-brand-50"
      >
        {layout.heroVariant === "repo" ? "打开 GitHub 仓库" : "查看原文"}
        <span aria-hidden>↗</span>
      </a>
    ) : null;

  if (layout.heroVariant === "repo") {
    return (
      <header className="ui-card overflow-hidden">
        <div className="flex flex-col sm:flex-row">
          <HeroCoverAside cover={cover} title={title} seed={seed} />
          <div className="min-w-0 flex-1 p-6 sm:p-8">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-slate-800 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white">
                {platform}
              </span>
              <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[10px] font-medium text-slate-600">
                {profileBadge}
              </span>
            </div>
            <h1 className="mt-3 font-mono text-xl font-semibold tracking-tight text-slate-900 sm:text-2xl">{title}</h1>
            {tagline ? <p className="mt-3 text-sm leading-relaxed text-slate-600">{tagline}</p> : null}
            {sourceLinkEl}
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              {dateStr ? <span className="tabular-nums">{dateStr}</span> : null}
            </div>
            {categoryTags}
          </div>
        </div>
      </header>
    );
  }

  if (layout.heroVariant === "news") {
    return (
      <header className="ui-card overflow-hidden border-l-4 border-l-brand-500">
        <div className="flex flex-col bg-brand-50/40 sm:flex-row">
          <HeroCoverAside cover={cover} title={title} seed={seed} />
          <div className="min-w-0 flex-1 px-6 py-8 sm:px-8">
            <div className="flex flex-wrap items-center gap-2 text-xs font-medium text-slate-600">
              <span className="rounded-md bg-white/80 px-2 py-0.5 ring-1 ring-slate-200/80">{platform}</span>
              <span className="text-slate-400">·</span>
              <span>{profileBadge}</span>
              {dateStr ? (
                <>
                  <span className="text-slate-400">·</span>
                  <time className="tabular-nums">{dateStr}</time>
                </>
              ) : null}
            </div>
            <h1 className="mt-4 text-2xl font-semibold leading-tight text-slate-900 sm:text-3xl">{title}</h1>
            {tagline ? <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">{tagline}</p> : null}
            {sourceLinkEl}
            {categoryTags}
          </div>
        </div>
      </header>
    );
  }

  if (layout.heroVariant === "wire") {
    return (
      <header className="ui-card overflow-hidden border-l-4 border-l-emerald-500">
        <div className="flex flex-col sm:flex-row">
          <HeroCoverAside cover={cover} title={title} seed={seed} />
          <div className="min-w-0 flex-1 bg-gradient-to-r from-emerald-50/80 to-white px-6 py-7 sm:px-8">
            <p className="text-[11px] font-bold uppercase tracking-wider text-emerald-800">{profileBadge}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
              <span className="font-medium text-slate-800">{platform}</span>
              {dateStr ? <time className="tabular-nums text-slate-500">{dateStr}</time> : null}
            </div>
            <h1 className="mt-3 text-2xl font-semibold leading-snug text-slate-900 sm:text-[1.65rem]">{title}</h1>
            {tagline ? <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600">{tagline}</p> : null}
            {sourceLinkEl}
            {categoryTags}
          </div>
        </div>
      </header>
    );
  }

  if (layout.heroVariant === "platform") {
    return (
      <header className="ui-card overflow-hidden border border-violet-100/90">
        <div className="flex flex-col sm:flex-row">
          <HeroCoverAside cover={cover} title={title} seed={seed} />
          <div className="min-w-0 flex-1">
            <div className="border-b border-violet-100/60 bg-violet-50/50 px-6 py-3 sm:px-8">
              <span className="text-[11px] font-bold uppercase tracking-wider text-violet-800">{profileBadge}</span>
            </div>
            <div className="px-6 py-6 sm:px-8">
              <p className="text-sm font-medium text-slate-500">{platform}</p>
              <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
              {tagline ? <p className="mt-3 text-sm leading-relaxed text-slate-600">{tagline}</p> : null}
              {sourceLinkEl}
              <div className="mt-3 text-xs text-slate-500">{dateStr ? <time className="tabular-nums">{dateStr}</time> : null}</div>
              {categoryTags}
            </div>
          </div>
        </div>
      </header>
    );
  }

  // product (launch / space / generic app)
  return (
    <header className="ui-card overflow-hidden">
      <div className="flex flex-col sm:flex-row">
        <HeroCoverAside cover={cover} title={title} seed={seed} />
        <div className="min-w-0 flex-1 p-6 sm:p-8">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={
                "inline-flex rounded-md bg-gradient-to-r px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-white shadow-sm " +
                layout.heroAccent
              }
            >
              {platform}
            </span>
            <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600">
              {profileBadge}
            </span>
          </div>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">{title}</h1>
          {tagline ? <p className="mt-3 text-sm leading-relaxed text-slate-600 sm:text-base">{tagline}</p> : null}
          {sourceLinkEl}
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            {dateStr ? <time className="tabular-nums">{dateStr}</time> : null}
          </div>
          {categoryTags}
        </div>
      </div>
    </header>
  );
}
