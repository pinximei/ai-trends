import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { publicApi, type ArticleDetail } from "@/lib/publicApi";

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
        <Link to="/resources" className="text-cyan-400 underline">
          返回列表
        </Link>
      </div>
    );
  }
  if (!a) {
    return <div className="px-4 py-10 text-slate-400">加载中…</div>;
  }

  return (
    <article className="mx-auto max-w-3xl px-4 py-10 text-slate-200">
      <Link to="/resources" className="text-sm text-cyan-400 hover:underline">
        ← 资源列表
      </Link>
      <h1 className="mt-4 text-2xl font-semibold text-white">{a.title}</h1>
      <div className="mt-2 text-xs text-slate-500">
        {a.content_type}
        {a.third_party_source ? ` · 来源：${a.third_party_source}` : ""}
      </div>
      <div className="prose prose-invert mt-8 max-w-none whitespace-pre-wrap text-slate-300">{a.body}</div>
    </article>
  );
}
