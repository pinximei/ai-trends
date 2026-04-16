import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiGet } from "@/api";
import { useI18n } from "@/i18n";

type Period = "day" | "week" | "month" | "quarter" | "year";
type Section = { title: string; content: string; citations: string[] };
type Fact = { kind: string; id: string; text: string; source: string; url: string };
type Media = { type: "image" | "video" | "link"; title: string; url: string; source: string };
type Briefing = {
  title: string;
  summary: string;
  period: Period;
  generated_at: string;
  hero: { kicker: string; headline: string; subheadline: string };
  selection?: { trend_selection_mode: string; signal_selection_mode: string };
  sections: Section[];
  facts: Fact[];
  media: Media[];
};

const PERIODS: Period[] = ["day", "week", "month", "quarter", "year"];

export function BriefingPage() {
  const { lang } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const period = (searchParams.get("period") as Period) || "week";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr("");
    setData(null);
    apiGet<Briefing>(`/api/v1/content/briefing?period=${period}`, lang)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lang, period]);

  const factsById = useMemo(() => {
    const map = new Map<string, Fact>();
    (data?.facts ?? []).forEach((f) => map.set(f.id, f));
    return map;
  }, [data]);

  return (
    <div className="space-y-8">
      <section className="glass relative overflow-hidden rounded-3xl border border-cyan-400/20 p-8">
        <div className="pointer-events-none absolute -mt-8 h-24 w-24 animate-ping rounded-full bg-cyan-400/20 blur-xl" />
        <p className="font-mono text-xs uppercase tracking-[0.28em] text-cyan-300/90">{data?.hero.kicker ?? "AI briefing"}</p>
        <h1 className="mt-3 text-3xl font-bold text-white sm:text-4xl">{data?.hero.headline ?? "Loading..."}</h1>
        <p className="mt-3 max-w-3xl text-slate-300">{data?.hero.subheadline ?? ""}</p>
        <div className="mt-5 flex flex-wrap gap-2">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setSearchParams({ period: p })}
              className={`rounded-full px-3 py-1 text-xs ${p === period ? "bg-cyan-300 text-slate-900" : "border border-white/15 bg-white/5 text-slate-300"}`}
            >
              {lang === "zh" ? { day: "日", week: "周", month: "月", quarter: "季度", year: "年" }[p] : p}
            </button>
          ))}
        </div>
        <p className="mt-4 text-sm text-slate-400">{data?.summary}</p>
        <p className="mt-2 text-xs text-slate-500">
          {lang === "zh" ? "生成时间" : "Generated at"}: {data?.generated_at ? new Date(data.generated_at).toLocaleString() : "-"}
        </p>
      </section>

      {loading ? <div className="glass rounded-2xl p-6 text-slate-300">{lang === "zh" ? "正在加载简报..." : "Loading briefing..."}</div> : null}
      {err ? <div className="glass rounded-2xl border border-rose-500/25 p-6 text-rose-300">{err}</div> : null}

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {(data?.sections ?? []).map((section, idx) => (
            <article key={`${section.title}-${idx}`} className="glass rounded-2xl p-6">
              <h2 className="text-xl font-semibold text-white">{section.title}</h2>
              <p className="mt-3 whitespace-pre-wrap leading-7 text-slate-200">{section.content}</p>
              {section.citations.length > 0 ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {section.citations.map((id) => {
                    const fact = factsById.get(id);
                    return (
                      <span key={id} className="rounded-full border border-cyan-500/35 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-100">
                        {id}
                        {fact?.url ? (
                          <>
                            {" · "}
                            <a href={fact.url} target="_blank" rel="noreferrer" className="underline">
                              {lang === "zh" ? "来源" : "source"}
                            </a>
                          </>
                        ) : null}
                      </span>
                    );
                  })}
                </div>
              ) : null}
            </article>
          ))}
        </div>

        <aside className="space-y-5">
          <div className="glass rounded-2xl p-5">
            <h3 className="text-lg font-semibold text-white">{lang === "zh" ? "事实清单" : "Facts"}</h3>
            <div className="mt-3 max-h-[460px] space-y-3 overflow-auto pr-1">
              {(data?.facts ?? []).map((f) => (
                <div key={f.id} className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="text-xs text-cyan-200">{f.kind} · {f.id}</div>
                  <p className="mt-1 text-sm text-slate-300">{f.text}</p>
                  <div className="mt-1 text-xs text-slate-500">{f.source}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="glass rounded-2xl p-5">
            <h3 className="text-lg font-semibold text-white">{lang === "zh" ? "媒体与网页元素" : "Media elements"}</h3>
            <div className="mt-3 space-y-3">
              {(data?.media ?? []).length === 0 ? (
                <p className="text-sm text-slate-400">
                  {lang === "zh" ? "当前信号来源中暂无可用媒体链接。" : "No media URLs in current sources."}
                </p>
              ) : null}
              {(data?.media ?? []).map((m) => (
                <div key={`${m.url}-${m.title}`} className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="text-xs text-cyan-100">{m.type.toUpperCase()} · {m.source}</div>
                  {m.type === "image" ? (
                    <img src={m.url} alt={m.title} className="mt-2 max-h-48 w-full rounded-lg object-cover" loading="lazy" />
                  ) : null}
                  {m.type === "video" ? (
                    <video src={m.url} controls className="mt-2 max-h-48 w-full rounded-lg" />
                  ) : null}
                  <a href={m.url} target="_blank" rel="noreferrer" className="mt-1 block text-sm text-slate-200 underline">
                    {m.title}
                  </a>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>

      {data?.selection ? (
        <div className="glass rounded-2xl p-4 text-xs text-slate-400">
          {lang === "zh" ? "数据选择策略" : "Selection mode"}: trend={data.selection.trend_selection_mode} / signal=
          {data.selection.signal_selection_mode}
        </div>
      ) : null}

      <div className="text-sm text-slate-400">
        {lang === "zh"
          ? "说明：文章仅根据已采集事实生成，不会补充无证据结论。你可以在后台先初始化模拟数据，再回到此页面查看完整效果。"
          : "Only evidence-backed facts are used. Seed demo data in admin if you need a fuller page for testing."}
        {" "}
        <Link to="/inspirations" className="text-cyan-300 underline">
          {lang === "zh" ? "查看信号源" : "View signals"}
        </Link>
      </div>
    </div>
  );
}
