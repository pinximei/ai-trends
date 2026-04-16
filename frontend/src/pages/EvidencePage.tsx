import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";
import { ExternalLink, FileSearch, Link2 } from "lucide-react";
import { getTrendDisplay } from "@/lib/trendCopy";

type Ev = {
  signal_id: string;
  trend_key: string;
  source: string;
  evidence_url: string;
  trace: string;
};

export function EvidencePage() {
  const { signalId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const id = decodeURIComponent(signalId);
  const from = searchParams.get("from") ?? "trends";
  const period = searchParams.get("period") ?? "week";
  const backTo = from === "inspirations" ? `/inspirations?period=${period}` : `/trends?period=${period}`;
  const { lang, t } = useI18n();
  const [ev, setEv] = useState<Ev | null>(null);

  useEffect(() => {
    if (!id) return;
    apiGet<Ev>(`/api/v1/evidences/${encodeURIComponent(id)}`, lang).then(setEv);
  }, [id, lang]);

  if (!ev) return <div className="animate-pulse text-slate-500">{lang === "zh" ? "加载证据中…" : "Loading evidence…"}</div>;

  return (
    <div className="space-y-8">
      <Link to={backTo} className="text-sm text-rose-400">
        ← {from === "inspirations" ? t("navInspirations") : t("navTrends")}
      </Link>
      <div className="grid gap-6 lg:grid-cols-12">
        <section className="glass rounded-3xl p-8 lg:col-span-7">
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <FileSearch className="h-6 w-6 text-cyan-300" />
            {t("evidence")} · {ev.signal_id}
          </h1>
          <p className="mt-3 text-sm text-slate-400">
            {lang === "zh" ? "用于验证趋势结论的原始依据与追溯路径。" : "Raw backing evidence and trace path behind trend judgments."}
          </p>
          <div className="mt-6 rounded-2xl border border-white/10 bg-black/20 p-4">
            <div className="text-xs uppercase tracking-wider text-slate-500">{t("trace")}</div>
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-xs text-cyan-200">{ev.trace}</pre>
          </div>
        </section>

        <aside className="space-y-4 lg:col-span-5">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <div className="text-xs text-slate-500">{t("navTrends")}</div>
            <Link
              className="mt-2 block text-rose-200 transition hover:text-rose-100"
              to={`/trends/${encodeURIComponent(ev.trend_key)}?period=${period}&from=${from}`}
            >
              <span className="text-base font-semibold">{getTrendDisplay(ev.trend_key, lang).title}</span>
              <span className="mt-1 block font-mono text-[11px] text-slate-500">{t("trendCodeLabel")}: {ev.trend_key}</span>
            </Link>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
            <div className="text-xs uppercase tracking-wider text-slate-500">{t("source")}</div>
            <div className="mt-2 inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-1 text-sm text-slate-200">
              <Link2 className="h-4 w-4 text-cyan-300" />
              {ev.source}
            </div>
          </div>
          <div className="rounded-2xl border border-cyan-500/25 bg-cyan-500/10 p-5">
            <div className="text-xs uppercase tracking-wider text-cyan-100/70">{t("link")}</div>
            <a href={ev.evidence_url} className="mt-2 inline-flex items-start gap-2 break-all text-cyan-200 hover:underline" target="_blank" rel="noreferrer">
              <ExternalLink className="mt-0.5 h-4 w-4 shrink-0" />
              {ev.evidence_url}
            </a>
          </div>
        </aside>
      </div>
    </div>
  );
}
