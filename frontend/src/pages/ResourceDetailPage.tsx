import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { publicApi, type ArticleDetail } from "@/api/public";

export function ResourceDetailPage() {
  const { id } = useParams();
  const [a, setA] = useState<ArticleDetail | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!id) return;
    publicApi
      .article(Number(id))
      .then(setA)
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

  return (
    <article className="mx-auto max-w-3xl px-4 py-10 text-slate-200">
      <Link to={backTo} className="text-sm text-cyan-400 hover:underline">
        ← 返回列表
      </Link>
      <h1 className="mt-4 text-2xl font-semibold text-white">{a.title}</h1>
      <div className="mt-2 text-xs text-slate-500">
        {a.feed_kind === "news" ? "AI 资讯" : "AI 应用"}
        {" · "}
        {a.content_type}
        {a.third_party_source ? ` · 来源：${a.third_party_source}` : ""}
      </div>
      {a.categories && a.categories.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
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
      <div className="prose prose-invert mt-8 max-w-none whitespace-pre-wrap text-slate-300">{a.body}</div>
    </article>
  );
}
