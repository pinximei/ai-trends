import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { publicApi, type ArticleDetail, type ArticleFeedCard, type ArticleTab } from "@/api/public";
import { useI18n } from "@/i18n";
import { pushRecentArticle } from "@/lib/recentArticles";

const INDUSTRY = "ai";

export function ResourceDetailPage() {
  const { t } = useI18n();
  const { id } = useParams();
  const [a, setA] = useState<ArticleDetail | null>(null);
  const [err, setErr] = useState("");
  const [tabIdx, setTabIdx] = useState(0);
  const [sidebar, setSidebar] = useState<ArticleFeedCard[]>([]);

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
    "max-w-none w-full space-y-4 text-slate-600 leading-relaxed [&_a]:font-medium [&_a]:text-brand-600 hover:[&_a]:underline [&_strong]:text-slate-900 [&_h2]:mt-6 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-slate-900 [&_h3]:mt-4 [&_h3]:text-base [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_li]:marker:text-brand-300 [&_code]:rounded-md [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-slate-800 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-4 [&_blockquote]:border-l-4 [&_blockquote]:border-brand-100 [&_blockquote]:pl-4 [&_blockquote]:text-slate-500";

  const backBtnClass =
    "inline-flex w-full items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-brand-300 hover:text-brand-600 sm:w-auto sm:justify-start";

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

  return (
    <div className="w-full px-2 sm:px-4">
      <div className="mb-4 flex justify-end lg:mb-6">
        <span className="rounded-full bg-slate-100 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          {isApp ? t("navApps") : t("navNews")}
        </span>
      </div>

      <div className="sticky top-16 z-30 mb-3 lg:hidden">
        <Link to={backTo} className={backBtnClass}>
          ← {t("detailBackFeed")}
        </Link>
      </div>

      <div className="flex flex-col gap-6 lg:h-[calc(100dvh-10.5rem)] lg:min-h-0 lg:flex-row lg:gap-8 lg:overflow-hidden">
        <aside className="min-w-0 w-full shrink-0 lg:flex lg:h-full lg:min-h-0 lg:w-[min(280px,calc(100%-1rem))] lg:flex-col lg:overflow-hidden xl:w-[300px]">
          <div className="flex flex-col gap-4 lg:h-full lg:min-h-0">
            <Link to={backTo} className={`${backBtnClass} hidden lg:inline-flex`}>
              ← {t("detailBackFeed")}
            </Link>
            <div className="ui-card flex min-h-0 flex-1 flex-col overflow-hidden lg:min-h-0">
              <div className="shrink-0 border-b border-slate-100 bg-slate-50/80 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t("detailSidebarTitle")}</p>
              </div>
              <nav className="min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto overscroll-y-contain">
                {sidebar.map((row) => {
                  const activeHere = row.id === a.id;
                  return (
                    <Link
                      key={row.id}
                      to={`/resources/${row.id}`}
                      className={`block px-4 py-3 text-sm transition-colors hover:bg-slate-50 ${
                        activeHere ? "border-l-[3px] border-l-brand-500 bg-brand-50/60 font-medium text-slate-900" : "text-slate-700"
                      }`}
                    >
                      <span className="line-clamp-2 leading-snug">{row.title}</span>
                      <span className="mt-1 block text-[10px] font-mono uppercase text-slate-400">
                        {row.platform_label || "—"}
                      </span>
                    </Link>
                  );
                })}
              </nav>
            </div>
          </div>
        </aside>

        <div className="min-h-0 w-full flex-1 lg:min-h-0 lg:overflow-y-auto lg:overflow-x-hidden lg:pr-1">
          <article className="min-w-0 w-full max-w-none space-y-6 pb-4">
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
                  <ReactMarkdown>{active?.body_md ?? ""}</ReactMarkdown>
                </div>
              </div>
            </div>
          ) : (
            <div className="ui-card p-5 sm:p-8">
              <div className={mdBody}>
                <ReactMarkdown>{a.body || ""}</ReactMarkdown>
              </div>
            </div>
          )}
          </article>
        </div>
      </div>
    </div>
  );
}
