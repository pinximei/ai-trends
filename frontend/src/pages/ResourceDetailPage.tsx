import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { publicApi, type ArticleDetail, type ArticleTab } from "@/api/public";
import { useI18n } from "@/i18n";

export function ResourceDetailPage() {
  const { t } = useI18n();
  const { id } = useParams();
  const [a, setA] = useState<ArticleDetail | null>(null);
  const [err, setErr] = useState("");
  const [tabIdx, setTabIdx] = useState(0);

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

  if (err) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="glass-light p-6">
          <p className="text-sm font-medium text-rose-600">{err}</p>
          <Link
            to="/apps"
            className="mt-4 inline-flex rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-violet-700 shadow-sm hover:bg-slate-50"
          >
            ← {t("resourceBackList")}
          </Link>
        </div>
      </div>
    );
  }
  if (!a) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <div className="glass-light py-12 text-center">
          <p className="text-sm text-slate-500">{t("resourceLoadingDetail")}</p>
        </div>
      </div>
    );
  }

  const backTo = a.feed_kind === "news" ? "/news" : "/apps";
  const tabs: ArticleTab[] = Array.isArray(a.tabs) && a.tabs.length > 0 ? a.tabs : [];
  const active = tabs[tabIdx];

  const mdBody =
    "max-w-none space-y-4 text-slate-600 leading-relaxed [&_a]:font-medium [&_a]:text-violet-600 hover:[&_a]:underline [&_strong]:text-slate-900 [&_h2]:mt-6 [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-slate-900 [&_h3]:mt-4 [&_h3]:text-base [&_h3]:font-semibold [&_ul]:list-disc [&_ul]:pl-5 [&_li]:marker:text-violet-400 [&_code]:rounded-md [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-sm [&_code]:text-violet-800 [&_pre]:overflow-x-auto [&_pre]:rounded-2xl [&_pre]:border [&_pre]:border-slate-200 [&_pre]:bg-slate-50 [&_pre]:p-4 [&_blockquote]:border-l-4 [&_blockquote]:border-violet-200 [&_blockquote]:pl-4 [&_blockquote]:text-slate-500";

  return (
    <article className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="glass-light p-5 sm:p-7">
        <Link
          to={backTo}
          className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50"
        >
          ← {t("resourceBackList")}
        </Link>
        <h1 className="mt-6 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl lg:text-4xl lg:leading-tight">
          {a.title}
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">{a.summary}</p>
        <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="inline-flex rounded-lg bg-violet-50 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-violet-800 ring-1 ring-violet-100">
            {a.feed_kind === "news" ? t("navNews") : t("navApps")}
          </span>
          {a.content_type ? (
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600">
              {a.content_type}
            </span>
          ) : null}
          {a.third_party_source ? (
            <span className="text-slate-500">
              {t("source")}: {a.third_party_source}
            </span>
          ) : null}
          {a.source_original_url ? (
            <a
              href={a.source_original_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-sky-600 hover:underline"
            >
              {t("sourceOriginal")}
            </a>
          ) : null}
        </div>
        {a.categories && a.categories.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {a.categories.map((c) => (
              <span
                key={c}
                className="rounded-lg bg-fuchsia-50 px-2.5 py-1 text-xs font-semibold text-fuchsia-900 ring-1 ring-fuchsia-100"
              >
                {c}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {tabs.length > 0 ? (
        <div className="mt-8">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-500">{t("resourceTabsHeading")}</div>
          <div
            role="tablist"
            aria-label={t("resourceTabsHeading")}
            className="mt-3 flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:thin] sm:flex-wrap"
          >
            {tabs.map((tab, i) => (
              <button
                key={`${tab.label}-${i}`}
                type="button"
                role="tab"
                aria-selected={i === tabIdx}
                onClick={() => setTabIdx(i)}
                className={`shrink-0 rounded-2xl border px-4 py-3 text-left transition duration-200 sm:min-w-[148px] sm:max-w-[280px] ${
                  i === tabIdx
                    ? "border-violet-300 bg-gradient-to-br from-violet-50 to-sky-50 text-slate-900 shadow-md ring-1 ring-violet-100"
                    : "border-slate-200 bg-white text-slate-600 hover:border-violet-200 hover:bg-slate-50"
                }`}
              >
                <span className="block text-sm font-bold text-violet-800">{tab.label}</span>
                <span className="mt-1 block text-[11px] leading-snug text-slate-500 line-clamp-2">{tab.summary}</span>
              </button>
            ))}
          </div>

          <div role="tabpanel" className="glass-light mt-8 p-5 sm:p-8">
            <div className={mdBody}>
              <ReactMarkdown>{active?.body_md ?? ""}</ReactMarkdown>
            </div>
          </div>
        </div>
      ) : (
        <div className="glass-light mt-8 p-5 sm:p-8">
          <div className={mdBody}>
            <ReactMarkdown>{a.body || ""}</ReactMarkdown>
          </div>
        </div>
      )}
    </article>
  );
}
