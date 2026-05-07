import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";
import { publicApi, type ArticleDetail, type ArticleTab } from "@/api/public";

export function ResourceDetailPage() {
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
      <div className="px-4 py-10 text-red-400">
        {err}{" "}
        <Link to="/apps" className="text-cyan-400 underline">
          返回列表
        </Link>
      </div>
    );
  }
  if (!a) {
    return <div className="px-4 py-10 text-slate-400">加载中…</div>;
  }

  const backTo = a.feed_kind === "news" ? "/news" : "/apps";
  const tabs: ArticleTab[] = Array.isArray(a.tabs) && a.tabs.length > 0 ? a.tabs : [];
  const active = tabs[tabIdx];

  return (
    <article className="mx-auto max-w-3xl px-4 py-10 text-slate-200 lg:max-w-4xl">
      <Link to={backTo} className="text-sm text-cyan-400 transition hover:text-cyan-300 hover:underline">
        ← 返回列表
      </Link>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-white sm:text-3xl lg:text-4xl lg:leading-tight">
        {a.title}
      </h1>
      <p className="mt-4 text-sm leading-relaxed text-slate-400 sm:text-base">{a.summary}</p>
      <div className="mt-2 text-xs text-slate-500">
        {a.feed_kind === "news" ? "AI 资讯" : "AI 应用"}
        {" · "}
        {a.content_type}
        {a.third_party_source ? ` · 来源：${a.third_party_source}` : ""}
      </div>
      {a.categories && a.categories.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {a.categories.map((c) => (
            <span
              key={c}
              className="rounded-lg bg-fuchsia-500/20 px-2.5 py-1 text-xs font-medium text-fuchsia-100 ring-1 ring-fuchsia-400/30"
            >
              {c}
            </span>
          ))}
        </div>
      ) : null}

      {tabs.length > 0 ? (
        <div className="mt-10">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">分栏阅读</div>
          <div
            role="tablist"
            aria-label="文章分栏"
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
                    ? "border-cyan-400/50 bg-gradient-to-br from-cyan-500/15 to-fuchsia-500/10 text-white shadow-[inset_0_0_24px_rgba(34,211,238,0.08)] ring-1 ring-cyan-400/25"
                    : "border-white/10 bg-white/[0.04] text-slate-300 hover:border-cyan-500/25 hover:bg-white/[0.07]"
                }`}
              >
                <span className="block text-sm font-semibold text-cyan-100">{tab.label}</span>
                <span className="mt-1 block text-[11px] leading-snug text-slate-400 line-clamp-2">{tab.summary}</span>
              </button>
            ))}
          </div>

          <div
            role="tabpanel"
            className="mt-8 rounded-2xl border border-white/10 bg-gradient-to-b from-white/[0.03] to-night-950/80 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05),0_24px_48px_rgba(0,0,0,0.35)] sm:p-8"
          >
            <div className="prose prose-invert prose-headings:scroll-mt-24 prose-headings:font-semibold prose-h2:mt-8 prose-h2:text-lg prose-h2:text-slate-100 prose-h3:text-base prose-p:text-slate-300 prose-p:leading-relaxed prose-li:text-slate-300 prose-strong:text-white prose-a:text-cyan-300 prose-a:no-underline hover:prose-a:underline prose-code:rounded-md prose-code:bg-slate-900/80 prose-code:px-1 prose-code:text-cyan-200 prose-pre:rounded-xl prose-pre:border prose-pre:border-white/10 prose-pre:bg-slate-950/80 prose-blockquote:border-l-cyan-500/40 prose-blockquote:text-slate-400 max-w-none">
              <ReactMarkdown>{active?.body_md ?? ""}</ReactMarkdown>
            </div>
          </div>
        </div>
      ) : (
        <div className="prose prose-invert prose-headings:text-slate-100 prose-p:text-slate-300 prose-p:leading-relaxed prose-a:text-cyan-300 prose-a:no-underline hover:prose-a:underline mt-10 max-w-none">
          <ReactMarkdown>{a.body || ""}</ReactMarkdown>
        </div>
      )}
    </article>
  );
}
