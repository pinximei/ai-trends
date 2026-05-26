import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Search } from "lucide-react";
import { publicApi, type ArticleDetail, type ArticleFeedCard } from "@/api/public";
import { ArticleDetailHero } from "@/components/articleDetail/ArticleDetailHero";
import { ArticleDetailMetrics } from "@/components/articleDetail/ArticleDetailMetrics";
import { ArticleReplicationPanel } from "@/components/articleDetail/ArticleReplicationPanel";
import { ArticleDetailSection } from "@/components/articleDetail/ArticleDetailSection";
import { ArticleDetailSectionNav } from "@/components/articleDetail/ArticleDetailSectionNav";
import { useI18n } from "@/i18n";
import {
  ARTICLE_MD_PROSE_CLASS,
  ArticleMarkdownContent,
  DETAIL_DATA_TAB_LABELS,
  DETAIL_REPLICATION_TAB_LABEL,
  markdownComponentsForBody,
  pickDetailTabs,
  prepareArticleTabMarkdown,
} from "@/lib/articleMarkdown";
import {
  getDetailLayout,
  profileBadgeI18nKey,
  type DetailSectionKind,
} from "@/lib/articleDetailLayout";
import { pushRecentArticle } from "@/lib/recentArticles";

const INDUSTRY = "ai";
const DESC_TAB_LABEL = "描述";

export function ResourceDetailPage() {
  const { t } = useI18n();
  const location = useLocation();
  const { id } = useParams();
  const [a, setA] = useState<ArticleDetail | null>(null);
  const [err, setErr] = useState("");
  const [sidebar, setSidebar] = useState<ArticleFeedCard[]>([]);
  const [sidebarQuery, setSidebarQuery] = useState("");
  const detailColumnScrollRef = useRef<HTMLDivElement>(null);
  const articleScrollRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!id) return;
    const col = detailColumnScrollRef.current;
    const art = articleScrollRef.current;
    if (col) col.scrollTop = 0;
    if (art) art.scrollTop = 0;
  }, [id]);

  useEffect(() => {
    if (!id) return;
    publicApi
      .article(Number(id))
      .then((row) => setA(row))
      .catch((e) => setErr(String(e)));
  }, [id]);

  useEffect(() => {
    if (!a) return;
    pushRecentArticle({
      id: a.id,
      title: a.title || "",
      feed: a.feed_kind === "apps" ? "apps" : "news",
    });
  }, [a]);

  useEffect(() => {
    if (!a) return;
    const feed = a.feed_kind === "apps" ? "apps" : "news";
    let cancelled = false;
    publicApi
      .articlesFeed({
        feed,
        industry_slug: INDUSTRY,
        page_size: 24,
        published_within_days: 120,
      })
      .then((d) => {
        if (cancelled) return;
        const items = d.items ?? [];
        const cur = a.id;
        const hit = items.find((x) => x.id === cur);
        const rest = items.filter((x) => x.id !== cur);
        setSidebar(hit ? [hit, ...rest.slice(0, 14)] : rest.slice(0, 15));
      })
      .catch(() => {
        if (!cancelled) setSidebar([]);
      });
    return () => {
      cancelled = true;
    };
  }, [a]);

  const layout = useMemo(() => (a ? getDetailLayout(a) : null), [a]);

  const rawTabs = useMemo(
    () => (Array.isArray(a?.tabs) && a!.tabs!.length > 0 ? a!.tabs! : []),
    [a],
  );
  const detailTabs = useMemo(() => pickDetailTabs(rawTabs), [rawTabs]);

  const descTab = useMemo(
    () => detailTabs.find((tab) => tab.label === DESC_TAB_LABEL),
    [detailTabs],
  );
  const replicationTab = useMemo(
    () => detailTabs.find((tab) => tab.label === DETAIL_REPLICATION_TAB_LABEL),
    [detailTabs],
  );
  const dataTab = useMemo(
    () => detailTabs.find((tab) => DETAIL_DATA_TAB_LABELS.has(tab.label)),
    [detailTabs],
  );

  const tagline = useMemo(() => {
    const fromDesc = (descTab?.summary || "").trim();
    if (fromDesc.length >= 24) return fromDesc;
    return (a?.summary || "").trim();
  }, [a?.summary, descTab?.summary]);

  const sectionContent = useMemo(() => {
    type SectionBlock = {
      title: string;
      summary: string;
      bodyMd: string;
      components: ReturnType<typeof markdownComponentsForBody>;
    };
    if (!layout) {
      return {
        description: null as SectionBlock | null,
        replication: null as SectionBlock | null,
        data: null as SectionBlock | null,
      };
    }
    const build = (tab: typeof descTab, kind: DetailSectionKind): SectionBlock | null => {
      if (!tab?.body_md?.trim()) return null;
      const bodyMd = prepareArticleTabMarkdown(tab.body_md, kind);
      if (!bodyMd) return null;
      let title = t(layout.dataTitleKey);
      if (kind === "description") title = t("detailSectionDescription");
      if (kind === "replication") title = t("detailSectionReplication");
      return {
        title,
        summary: kind === "description" ? "" : (tab.summary || "").trim(),
        bodyMd,
        components: markdownComponentsForBody(bodyMd, `detail-${kind}`),
      };
    };
    return {
      description: build(descTab, "description"),
      replication: build(replicationTab, "replication"),
      data: build(dataTab, "data"),
    };
  }, [layout, descTab, replicationTab, dataTab, t]);

  const hasDescTab = Boolean(descTab);
  const fallbackBodyMd = useMemo(
    () => (a?.body ? prepareArticleTabMarkdown(a.body, "description") : ""),
    [a?.body],
  );
  const showFallbackBody = !hasDescTab && fallbackBodyMd.length > 60;
  const fallbackMdComponents = useMemo(
    () => markdownComponentsForBody(fallbackBodyMd, "body"),
    [fallbackBodyMd],
  );

  const markdownFingerprint = useMemo(() => {
    const parts = [
      sectionContent.description?.bodyMd,
      sectionContent.replication?.bodyMd,
      sectionContent.data?.bodyMd,
    ].filter(Boolean);
    if (parts.length) return parts.join("\0");
    return fallbackBodyMd;
  }, [sectionContent, fallbackBodyMd]);

  const sidebarFilterQ = sidebarQuery.trim().toLowerCase();
  const filteredSidebar = useMemo(() => {
    if (!sidebarFilterQ) return sidebar;
    return sidebar.filter((row) => {
      const title = row.title.toLowerCase();
      const plat = (row.platform_label || "").toLowerCase();
      return title.includes(sidebarFilterQ) || plat.includes(sidebarFilterQ);
    });
  }, [sidebar, sidebarFilterQ]);

  useEffect(() => {
    setSidebarQuery("");
  }, [a?.id, markdownFingerprint]);

  const scrollToHeading = useCallback((headingId: string) => {
    const root = articleScrollRef.current;
    if (!root) return;
    const el = root.querySelector(`#${CSS.escape(headingId)}`) as HTMLElement | null;
    if (!el) return;
    const rootRect = root.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const nextTop = elRect.top - rootRect.top + root.scrollTop;
    root.scrollTo({ top: Math.max(0, nextTop - 6), behavior: "smooth" });
  }, []);

  useEffect(() => {
    const raw = location.hash.replace(/^#/, "");
    if (!raw || !articleScrollRef.current) return;
    const el = articleScrollRef.current.querySelector(`#${CSS.escape(raw)}`);
    if (!el) return;
    const timer = window.setTimeout(() => scrollToHeading(raw), 80);
    return () => window.clearTimeout(timer);
  }, [location.hash, markdownFingerprint, scrollToHeading]);

  const backBtnClass =
    "inline-flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200/90 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 sm:w-auto sm:justify-start " +
    "lg:border-slate-200/60 lg:bg-white/80 lg:shadow-sm lg:backdrop-blur-sm lg:hover:bg-white";

  if (err) {
    return (
      <div className="w-full px-2 sm:px-4">
        <div className="ui-card mx-auto max-w-lg p-6">
          <p className="text-sm font-medium text-rose-600">{err}</p>
          <Link
            to="/"
            className="mt-4 inline-flex rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-brand-600 shadow-sm hover:bg-slate-50"
          >
            ← {t("resourceBackList")}
          </Link>
        </div>
      </div>
    );
  }

  if (!a || !layout) {
    return (
      <div className="w-full px-2 sm:px-4">
        <div className="ui-card mx-auto max-w-lg py-12 text-center">
          <p className="text-sm text-slate-500">{t("resourceLoadingDetail")}</p>
        </div>
      </div>
    );
  }

  const feedKind: "news" | "apps" = a.feed_kind === "apps" ? "apps" : "news";
  const backTo = feedKind === "apps" ? "/apps" : "/news";
  const profileBadge = t(profileBadgeI18nKey(layout.profile));
  const showStructuredReplication =
    feedKind === "apps" && Boolean(a.replication_analysis && a.replication_analysis.verdict);

  const categoryTagsEl =
    a.categories && a.categories.length > 0 ? (
      <div
        data-testid="resource-detail-category-tags"
        className="mt-4 flex flex-wrap gap-2 border-t border-slate-200/60 pt-4"
      >
        {a.categories.map((c) => (
          <span
            key={c}
            className="inline-flex items-center rounded-full border border-slate-200/90 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 shadow-sm"
          >
            {c}
          </span>
        ))}
      </div>
    ) : null;

  const navSections = [
    {
      kind: "description" as const,
      label: t("detailNavDescription"),
      present: Boolean(sectionContent.description),
    },
    {
      kind: "replication" as const,
      label: t("detailNavReplication"),
      present: Boolean(showStructuredReplication || sectionContent.replication),
    },
    {
      kind: "data" as const,
      label: t("detailNavData"),
      present: Boolean(sectionContent.data),
    },
  ];

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden px-2 sm:px-4 lg:px-0">
      <div className="sticky top-16 z-30 mb-3 shrink-0 lg:hidden">
        <Link to={backTo} className={backBtnClass}>
          ← {t("detailBackFeed")}
        </Link>
      </div>

      <div
        ref={detailColumnScrollRef}
        className={
          "flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-y-contain " +
          "lg:flex-row lg:items-stretch lg:gap-0 lg:overflow-hidden lg:rounded-none lg:border-0 lg:bg-transparent lg:shadow-none"
        }
      >
        <aside
          className={
            "flex w-full shrink-0 flex-col self-start overflow-hidden " +
            "max-h-[min(52vh,30rem)] min-h-0 lg:max-h-none lg:min-h-0 lg:w-[260px] lg:shrink-0 lg:self-stretch xl:w-[272px] " +
            "lg:border-r lg:border-slate-300/35 lg:bg-[#ecedf2]"
          }
        >
          <div className="shrink-0 space-y-2 px-1.5 pb-2 pt-1 lg:px-2.5 lg:pt-3">
            <div className="ui-card hidden overflow-hidden p-1 shadow-sm lg:block">
              <Link to={backTo} className={`${backBtnClass} flex w-full border-0 shadow-none`}>
                ← {t("detailBackFeed")}
              </Link>
            </div>
            <div className="ui-card overflow-hidden p-2.5 shadow-sm">
              <label htmlFor="resource-detail-sidebar-search" className="sr-only">
                {t("resourcesSearchLabel")}
              </label>
              <div className="relative">
                <Search
                  className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                  strokeWidth={2}
                  aria-hidden
                />
                <input
                  id="resource-detail-sidebar-search"
                  type="search"
                  value={sidebarQuery}
                  onChange={(e) => setSidebarQuery(e.target.value)}
                  autoComplete="off"
                  placeholder={t("detailSidebarSearchPlaceholder")}
                  className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-2 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
                />
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-1.5 pb-2 scrollbar-hide lg:px-2.5 lg:pb-3">
            <div className="ui-card overflow-hidden shadow-sm">
              <div className="border-b border-slate-100 bg-slate-50/90 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{t("detailSidebarRelatedTitle")}</p>
              </div>
              <nav className="flex flex-col gap-0.5 px-1 py-2" aria-label={t("detailSidebarRelatedTitle")}>
                {filteredSidebar.length === 0 ? (
                  <p className="px-2 py-2 text-xs text-slate-500">
                    {sidebarQuery.trim() ? t("detailSidebarNoMatch") : t("detailSidebarFeedEmpty")}
                  </p>
                ) : (
                  filteredSidebar.map((row) => {
                    const activeHere = row.id === a.id;
                    return (
                      <Link
                        key={row.id}
                        to={`/resources/${row.id}`}
                        className={`mx-1 block rounded-lg px-3 py-2.5 text-sm transition-colors ${
                          activeHere
                            ? "bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/70"
                            : "text-slate-700 hover:bg-white/50"
                        }`}
                      >
                        <span className="line-clamp-2 leading-snug">{row.title}</span>
                        <span className="mt-0.5 block text-[10px] font-mono uppercase tracking-wide text-slate-400">
                          {row.platform_label || "—"}
                        </span>
                      </Link>
                    );
                  })
                )}
              </nav>
            </div>
          </div>
        </aside>

        <div
          ref={articleScrollRef}
          data-testid="resource-detail-article"
          data-detail-profile={layout.profile}
          className="min-h-0 w-full min-w-0 flex-1 overflow-y-auto overscroll-y-contain bg-white article-scrollbar lg:overflow-x-hidden"
        >
          <article className="min-w-0 w-full max-w-none space-y-5 px-1 pb-4 pt-1 sm:px-0 sm:pt-0 lg:px-6 lg:pb-8 lg:pt-4 xl:px-10">
            <ArticleDetailHero
              article={a}
              layout={layout}
              tagline={tagline}
              profileBadge={profileBadge}
              categoryTags={categoryTagsEl}
            />

            <ArticleDetailMetrics
              article={a}
              layout={layout}
              starsLabel={t("detailMetricStars")}
              heatLabel={t("detailMetricHeat")}
              starsTodayTemplate={(n) => t("feedStarsToday").replace("{n}", n)}
            />

            <ArticleDetailSectionNav layout={layout} sections={navSections} onJump={scrollToHeading} />

            {layout.sectionOrder.map((kind) => {
              if (kind === "replication") {
                if (showStructuredReplication && a.replication_analysis) {
                  return (
                    <div
                      key={kind}
                      id="detail-section-replication"
                      className="ui-card overflow-hidden border-brand-100/80 p-5 sm:p-8"
                    >
                      <h2 className="text-base font-semibold text-slate-900">{t("detailSectionReplication")}</h2>
                      <div className="mt-4">
                        <ArticleReplicationPanel
                          analysis={a.replication_analysis}
                          replicationTier={a.replication_tier}
                        />
                      </div>
                      {sectionContent.replication ? (
                        <div className={`mt-6 border-t border-slate-100 pt-6 ${ARTICLE_MD_PROSE_CLASS}`}>
                          <ArticleMarkdownContent
                            bodyMd={sectionContent.replication.bodyMd}
                            components={sectionContent.replication.components}
                          />
                        </div>
                      ) : null}
                    </div>
                  );
                }
                const block = sectionContent.replication;
                if (!block) return null;
                return (
                  <ArticleDetailSection
                    key={kind}
                    kind={kind}
                    layout={layout}
                    title={block.title}
                    summary={block.summary}
                    bodyMd={block.bodyMd}
                    components={block.components}
                  />
                );
              }
              const block = kind === "description" ? sectionContent.description : sectionContent.data;
              if (!block) return null;
              return (
                <ArticleDetailSection
                  key={kind}
                  kind={kind}
                  layout={layout}
                  title={block.title}
                  summary={block.summary}
                  bodyMd={block.bodyMd}
                  components={block.components}
                />
              );
            })}

            {showFallbackBody ? (
              <div className="ui-card overflow-hidden p-5 sm:p-8">
                <h2 className="text-base font-semibold text-slate-900">{t("detailOverview")}</h2>
                <div className={`mt-4 ${ARTICLE_MD_PROSE_CLASS}`}>
                  <ArticleMarkdownContent bodyMd={fallbackBodyMd} components={fallbackMdComponents} />
                </div>
              </div>
            ) : null}
          </article>
        </div>
      </div>
    </div>
  );
}
