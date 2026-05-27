import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Flame, GitBranch, LayoutGrid, Newspaper, TrendingUp } from "lucide-react";
import { publicApi, type TrendMomentumItem, type TrendMomentumResponse, type TrendMomentumTopic } from "@/api/public";
import { HomeArticleTile } from "@/components/home/HomeArticleTile";
import { HomeSection } from "@/components/home/HomeSection";
import { useI18n } from "@/i18n";

const INDUSTRY = "ai";

function MomentumBadge({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {tags.map((tag) => (
        <span
          key={tag}
          className="rounded-md bg-orange-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-orange-800 ring-1 ring-orange-200/80"
        >
          {tag}
        </span>
      ))}
    </div>
  );
}

function MomentumMeta({ item }: { item: TrendMomentumItem }) {
  return (
    <p className="mt-1 text-[11px] text-slate-500">
      动量 <span className="font-semibold tabular-nums text-violet-700">{item.momentum_score}</span>
      <span className="mx-1 text-slate-300">·</span>
      热度 {Math.round(item.heat_score ?? 0)}
      {item.days_on_radar > 0 ? (
        <>
          <span className="mx-1 text-slate-300">·</span>
          已跟踪 {item.days_on_radar} 天
        </>
      ) : null}
      {item.engagement_stars_today != null && item.engagement_stars_today > 0 ? (
        <>
          <span className="mx-1 text-slate-300">·</span>
          +{item.engagement_stars_today} 今日 Star
        </>
      ) : null}
    </p>
  );
}

function TrackList({ items }: { items: TrendMomentumItem[] }) {
  const { t } = useI18n();
  if (!items.length) return <p className="text-sm text-slate-500">{t("trendsEmpty")}</p>;
  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.id} className="space-y-2">
          <MomentumBadge tags={item.momentum_tags} />
          <MomentumMeta item={item} />
          <HomeArticleTile item={item} variant="tile" />
        </div>
      ))}
    </div>
  );
}

function TopicGrid({ topics }: { topics: TrendMomentumTopic[] }) {
  const { t } = useI18n();
  if (!topics.length) return <p className="text-sm text-slate-500">{t("trendsTopicsEmpty")}</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {topics.map((topic) => (
        <div
          key={topic.label}
          className="rounded-xl border border-slate-200/90 bg-gradient-to-br from-white to-slate-50/80 p-4 shadow-sm"
        >
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-base font-bold text-slate-900">{topic.label}</h3>
            <span className="shrink-0 rounded-full bg-violet-100 px-2.5 py-0.5 text-[10px] font-bold text-violet-800">
              {topic.article_count} 篇
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-600">
            {t("trendsTopicMomentum")}{" "}
            <span className="font-semibold tabular-nums text-violet-700">{topic.momentum_score}</span>
            <span className="mx-1 text-slate-300">·</span>
            {t("trendsTopicHeatAvg")} {topic.heat_avg}
          </p>
          {topic.sample_titles.length ? (
            <ul className="mt-3 space-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
              {topic.sample_titles.map((title) => (
                <li key={title} className="line-clamp-1">
                  · {title}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function TrendsPage() {
  const { t } = useI18n();
  const [data, setData] = useState<TrendMomentumResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr("");
    publicApi
      .trendMomentum({ industry_slug: INDUSTRY, period_days: 30, limit_per_track: 8, topic_limit: 12 })
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : t("trendsLoadError"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  return (
    <div className="w-full space-y-6 lg:space-y-8">
      <section className="ui-card overflow-hidden p-5 sm:p-6">
        <div className="flex flex-wrap items-start gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-rose-600 text-white shadow-lg shadow-orange-500/25">
            <TrendingUp className="h-6 w-6" strokeWidth={2.5} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">{t("trendsPageTitle")}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-600 sm:text-[15px]">{t("trendsPageDesc")}</p>
            {data?.scoring_note ? (
              <p className="mt-3 text-[11px] leading-relaxed text-slate-400">{data.scoring_note}</p>
            ) : null}
          </div>
        </div>
      </section>

      {loading ? (
        <p className="text-sm text-slate-500">{t("homeLoading")}</p>
      ) : err ? (
        <p className="text-sm font-medium text-rose-600" role="alert">
          {err}
        </p>
      ) : data ? (
        <>
          <HomeSection
            title={t("trendsTopicsTitle")}
            subtitle={t("trendsTopicsSub")}
            icon={<Flame className="h-5 w-5 text-orange-500" strokeWidth={2} />}
          >
            <TopicGrid topics={data.topics} />
          </HomeSection>

          <div className="grid gap-6 xl:grid-cols-2 xl:gap-8">
            <HomeSection
              title={t("trendsSoftwareTitle")}
              subtitle={t("trendsSoftwareSub")}
              icon={<LayoutGrid className="h-5 w-5 text-sky-600" strokeWidth={2} />}
            >
              <TrackList items={data.software} />
            </HomeSection>

            <HomeSection
              title={t("trendsOssTitle")}
              subtitle={t("trendsOssSub")}
              icon={<GitBranch className="h-5 w-5 text-emerald-600" strokeWidth={2} />}
            >
              <TrackList items={data.oss} />
            </HomeSection>
          </div>

          <HomeSection
            title={t("trendsHotspotsTitle")}
            subtitle={t("trendsHotspotsSub")}
            icon={<Newspaper className="h-5 w-5 text-violet-600" strokeWidth={2} />}
          >
            <TrackList items={data.hotspots} />
          </HomeSection>

          <p className="text-center text-xs text-slate-500">
            {t("trendsPeriodNote")} {data.period_days} {t("trendsPeriodDaysUnit")}
            <span className="mx-2 text-slate-300">·</span>
            <Link to="/apps" className="font-medium text-violet-600 hover:underline">
              {t("navApps")}
            </Link>
            <span className="mx-1 text-slate-300">/</span>
            <Link to="/news" className="font-medium text-violet-600 hover:underline">
              {t("navNews")}
            </Link>
          </p>
        </>
      ) : null}
    </div>
  );
}
