import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useLocation, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { publicApi, type ArticleDetail, type ArticleFeedCard, type ArticleTab } from "@/api/public";
import { useI18n } from "@/i18n";
import { parseMarkdownToc, type TocItem } from "@/lib/markdownToc";
import { pushRecentArticle } from "@/lib/recentArticles";

const INDUSTRY = "ai";

/** 顶栏 sticky + 侧栏 sticky 与锚点 scroll-margin 对齐（约 5.75rem） */
const SCROLL_MARGIN_TOP = "scroll-mt-[5.75rem]";

function createArticleMarkdownComponents(toc: TocItem[]) {
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
  };
}

export function ResourceDetailPage() {
  const { t } = useI18n();
  const location = useLocation();
  const { id } = useParams();
  const [a, setA] = useState<ArticleDetail | null>(null);
  const [err, setErr] = useState("");
  const [tabIdx, setTabIdx] = useState(0);
  const [sidebar, setSidebar] = useState<ArticleFeedCard[]>([]);
  const [activeTocId, setActiveTocId] = useState<string | null>(null);
  const articleScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    publicApi
      .article(Number(id))
      .then((row) => {
        setA(row);
        setTabIdx(0);
      })
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

  const tabs: ArticleTab[] = useMemo(
    () => (Array.isArray(a?.tabs) && a!.tabs!.length > 0 ? a!.tabs! : []),
    [a],
  );
  const active = tabs[tabIdx];

  const markdownSource = useMemo(() => {
    if (!a) return "";
    if (tabs.length > 0) return active?.body_md ?? "";
    return a.body || "";
  }, [a, tabs.length, active?.body_md, a?.body]);

  const toc = useMemo(() => parseMarkdownToc(markdownSource), [markdownSource]);

  const mdComponents = useMemo(() => createArticleMarkdownComponents(toc), [toc]);

  useEffect(() => {
    setActiveTocId(null);
  }, [tabIdx, markdownSource, a?.id]);

  useEffect(() => {
    const root = articleScrollRef.current;
    if (!root || toc.length === 0) return;
    const heads = [...root.querySelectorAll("[data-toc-heading]")] as HTMLElement[];
    if (heads.length === 0) return;

    let raf = 0;
    const pickActive = () => {
      const rootRect = root.getBoundingClientRect();
      const band = rootRect.top + rootRect.height * 0.18;
      let best: string | null = null;
      let bestDist = Infinity;
      for (const el of heads) {
        if (!el.id) continue;
        const r = el.getBoundingClientRect();
        if (r.bottom < rootRect.top + 2) continue;
        if (r.top > rootRect.bottom - 2) continue;
        const d = Math.abs(r.top - band);
        if (d < bestDist) {
          bestDist = d;
          best = el.id;
        }
      }
      if (best) setActiveTocId((cur) => (cur === best ? cur : best));
    };

    const ob = new IntersectionObserver(
      () => {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(pickActive);
      },
      { root, rootMargin: "-8% 0px -70% 0px", threshold: [0, 0.04, 0.15, 0.35, 0.6] },
    );
    heads.forEach((h) => ob.observe(h));
    pickActive();

    return () => {
      cancelAnimationFrame(raf);
      ob.disconnect();
    };
  }, [toc, markdownSource, a?.id, tabIdx]);

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
    const t = window.setTimeout(() => scrollToHeading(raw), 80);
    return () => window.clearTimeout(t);
  }, [location.hash, markdownSource, scrollToHeading]);

  const highlights = useMemo(() => {
    if (!a) return [];
    if (tabs.length > 0) {
      return tabs.slice(0, 5).map((tab) => {
        const line = `${tab.label}：${tab.summary || ""}`.trim();
        return line.length > 140 ? `${line.slice(0, 138)}…` : line;
      });
    }
    return (a.summary || "")
      .split(/[。；\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 5);
  }, [a, tabs]);

  const backTo = a?.feed_kind === "apps" ? "/apps" : "/news";
  const isApp = a?.feed_kind === "apps";

  const mdBody =
    "max-w-none w-full space-y-4 text-slate-600 leading-relaxed [&_a]:font-medium [&_a]:text-brand-600 hover:[&_a]:underline [&_strong]:text-slate-900 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:marker:text-brand-300 [&_code]:rounded-md [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-slate-800 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-4 [&_blockquote]:border-l-4 [&_blockquote]:border-brand-100 [&_blockquote]:pl-4 [&_blockquote]:text-slate-500";

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
  if (!a) {
    return (
      <div className="w-full px-2 sm:px-4">
        <div className="ui-card mx-auto max-w-lg py-12 text-center">
          <p className="text-sm text-slate-500">{t("resourceLoadingDetail")}</p>
        </div>
      </div>
    );
  }

  const tocLinkClass = (id: string) =>
    `mx-1 block rounded-lg px-2.5 py-1.5 text-left text-[13px] leading-snug transition-colors ${
      activeTocId === id
        ? "bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/70"
        : "text-slate-600 hover:bg-white/50"
    }`;

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden px-2 sm:px-4 lg:px-0">
      <div className="mb-3 flex shrink-0 justify-end lg:hidden">
        <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {isApp ? t("navApps") : t("navNews")}
        </span>
      </div>

      <div className="sticky top-16 z-30 mb-3 shrink-0 lg:hidden">
        <Link to={backTo} className={backBtnClass}>
          ← {t("detailBackFeed")}
        </Link>
      </div>

      {/* 大屏：对齐 DeepSeek — 扁平分栏、左列冷灰底、右列白底双区独立滚动；小屏整列可滚 */}
      <div
        className={
          "flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto overscroll-y-contain " +
          "lg:flex-row lg:items-stretch lg:gap-0 lg:overflow-hidden lg:rounded-none lg:border-0 lg:bg-transparent lg:shadow-none"
        }
      >
        <aside
          className={
            "flex w-full shrink-0 flex-col self-start overflow-hidden " +
            "max-h-[min(42vh,26rem)] min-h-0 lg:max-h-none lg:min-h-0 lg:w-[260px] lg:shrink-0 lg:self-stretch xl:w-[272px] " +
            "lg:border-r lg:border-slate-300/35 lg:bg-[#ecedf2]"
          }
        >
          <div
            className={
              "flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-y-contain px-1 py-1 scrollbar-hide " +
              "lg:px-2.5 lg:py-3"
            }
          >
            <Link to={backTo} className={`${backBtnClass} hidden shrink-0 lg:inline-flex`}>
              ← {t("detailBackFeed")}
            </Link>

            {!isApp && toc.length > 0 ? (
              <div className="min-w-0">
                <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{t("detailTocTitle")}</p>
                <nav className="pb-1" aria-label={t("detailTocTitle")}>
                  {toc.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={tocLinkClass(item.id)}
                      style={{ paddingLeft: item.level === 3 ? "0.875rem" : undefined }}
                      onClick={() => scrollToHeading(item.id)}
                    >
                      <span className="line-clamp-3">{item.text}</span>
                    </button>
                  ))}
                </nav>
              </div>
            ) : !isApp && toc.length === 0 ? (
              <p className="px-3 py-1 text-xs text-slate-500">{t("detailTocEmpty")}</p>
            ) : null}

            <div className="min-w-0 flex-1 lg:min-h-0">
              <p className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{t("detailSidebarTitle")}</p>
              <nav className="flex flex-col gap-0.5 pb-1">
                {sidebar.map((row) => {
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
                })}
              </nav>
            </div>
          </div>
        </aside>

        <div
          ref={articleScrollRef}
          data-testid="resource-detail-article"
          className="min-h-0 w-full min-w-0 flex-1 overflow-y-auto overscroll-y-contain bg-white article-scrollbar lg:overflow-x-hidden"
        >
          <div className="sticky top-0 z-10 hidden shrink-0 border-b border-slate-200/70 bg-white/90 px-4 py-2.5 backdrop-blur-md supports-[backdrop-filter]:bg-white/75 lg:flex lg:items-center lg:justify-between lg:gap-3 lg:px-6 xl:px-10">
            <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{a.title}</p>
            <span className="shrink-0 rounded-full border border-slate-200/80 bg-slate-50 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              {isApp ? t("navApps") : t("navNews")}
            </span>
          </div>
          <article className="min-w-0 w-full max-w-none space-y-6 px-1 pb-4 pt-1 sm:px-0 sm:pt-0 lg:px-6 lg:pb-8 lg:pt-3 xl:px-10">
            {isApp ? (
              <div className="ui-card overflow-hidden p-6 sm:p-8">
                <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
                  <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-md bg-brand-500 text-2xl font-semibold text-white shadow-sm">
                    {(a.title || "?").slice(0, 1)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-slate-500">{t("detailAppMeta")}</p>
                    <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">{a.title}</h1>
                    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
                      {a.published_at ? (
                        <span className="tabular-nums">{a.published_at.slice(0, 10)}</span>
                      ) : null}
                      {a.platform_label ? <span>{a.platform_label}</span> : null}
                    </div>
                    {a.summary ? <p className="mt-4 text-sm leading-relaxed text-slate-600">{a.summary}</p> : null}
                  </div>
                </div>
              </div>
            ) : (
              <div className="ui-card border-l-4 border-l-brand-500 bg-brand-50/40 px-6 py-8 sm:px-8">
                <p className="text-xs font-medium uppercase tracking-wide text-brand-700">{t("detailFeaturedTag")}</p>
                <h1 className="mt-2 text-2xl font-semibold leading-tight text-slate-900 sm:text-3xl">{a.title}</h1>
                {a.summary ? (
                  <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">{a.summary}</p>
                ) : null}
              </div>
            )}

            {!isApp && highlights.length > 0 ? (
              <div className="ui-card p-6 sm:p-7">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500">{t("detailHighlights")}</h2>
                <ul className="mt-4 space-y-2">
                  {highlights.map((line, i) => (
                    <li key={i} className="flex gap-3 text-sm leading-relaxed text-slate-700">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {a.categories && a.categories.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {a.categories.map((c) => (
                  <span
                    key={c}
                    className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700"
                  >
                    {c}
                  </span>
                ))}
              </div>
            ) : null}

            {tabs.length > 0 ? (
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{t("resourceTabsHeading")}</div>
                <div
                  role="tablist"
                  className="mt-3 flex flex-wrap gap-2"
                  aria-label={t("resourceTabsHeading")}
                >
                  {tabs.map((tab, i) => (
                    <button
                      key={`${tab.label}-${i}`}
                      type="button"
                      role="tab"
                      aria-selected={i === tabIdx}
                      onClick={() => setTabIdx(i)}
                      className={`flex min-w-0 shrink-0 items-center gap-1 rounded-md border px-3 py-1.5 text-sm font-medium transition ${
                        i === tabIdx
                          ? "border-brand-500 bg-brand-500 text-white shadow-sm"
                          : "border-slate-200 bg-white text-slate-600 hover:border-brand-300"
                      }`}
                    >
                      {tab.label}
                      <ChevronRight className={`h-4 w-4 ${i === tabIdx ? "text-white/90" : "text-slate-400"}`} />
                    </button>
                  ))}
                </div>
                <div role="tabpanel" className="ui-card mt-6 p-5 sm:p-8">
                  <div className={mdBody}>
                    <ReactMarkdown components={mdComponents}>{active?.body_md ?? ""}</ReactMarkdown>
                  </div>
                </div>
              </div>
            ) : (
              <div className="ui-card p-5 sm:p-8">
                <div className={mdBody}>
                  <ReactMarkdown components={mdComponents}>{a.body || ""}</ReactMarkdown>
                </div>
              </div>
            )}
          </article>
        </div>
      </div>
    </div>
  );
}
