import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { publicApi, type ArticleCard } from "@/lib/publicApi";
import { useI18n } from "@/i18n";
import { splitPrimaryOverflow } from "@/lib/segmentNav";

type SegmentRow = { id: number; slug: string; name: string; industry_id: number; industry_slug: string };
type IndustryRow = { id: number; slug: string; name: string };

type TimeKey = "latest_day" | "all" | "d7" | "d30" | "d90";

const TIME_FILTERS: Array<{ key: TimeKey; labelKey: string }> = [
  { key: "latest_day", labelKey: "resourcesLatestDay" },
  { key: "all", labelKey: "resourcesTimeAll" },
  { key: "d7", labelKey: "resourcesDays7" },
  { key: "d30", labelKey: "resourcesDays30" },
  { key: "d90", labelKey: "resourcesDays90" },
];

function timeKeyToArticleParams(timeKey: TimeKey): {
  published_within_days?: number;
  published_on_latest_day?: boolean;
} {
  if (timeKey === "latest_day") return { published_on_latest_day: true };
  if (timeKey === "all") return {};
  const n = timeKey === "d7" ? 7 : timeKey === "d30" ? 30 : 90;
  return { published_within_days: n };
}

export function ResourcesPage() {
  const { t } = useI18n();
  const [industries, setIndustries] = useState<IndustryRow[]>([]);
  const [industrySlug, setIndustrySlug] = useState("");
  const [segments, setSegments] = useState<SegmentRow[] | null>(null);
  /** 全部 | 某一主板块 |「其他」(余下板块合集) */
  const [segmentScope, setSegmentScope] = useState<number | "all" | "other">("all");
  const [timeKey, setTimeKey] = useState<TimeKey>("latest_day");
  const [sort, setSort] = useState<"hot" | "latest">("hot");
  const [list, setList] = useState<ArticleCard[]>([]);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  const { primary: primarySegments, overflow: overflowSegments } = useMemo(
    () => splitPrimaryOverflow(segments ?? []),
    [segments],
  );

  const segmentNameById = useMemo(() => {
    const m = new Map<number, string>();
    (segments ?? []).forEach((s) => m.set(s.id, s.name));
    return m;
  }, [segments]);

  useEffect(() => {
    publicApi
      .industries()
      .then((list) => {
        setIndustries(list);
        const saved = typeof localStorage !== "undefined" ? localStorage.getItem("publicIndustrySlug") : null;
        const pick = list.find((i) => i.slug === saved)?.slug ?? list[0]?.slug ?? "";
        if (pick) setIndustrySlug(pick);
      })
      .catch(() => setIndustrySlug(""));
  }, []);

  useEffect(() => {
    if (!industrySlug) return;
    let cancelled = false;
    publicApi
      .segments({ industry_slug: industrySlug })
      .then((rows) => {
        if (!cancelled) {
          setSegments(rows);
          setSegmentScope("all");
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(String(e));
          setSegments([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [industrySlug]);

  useEffect(() => {
    if (segments === null || !industrySlug) return;
    let cancelled = false;
    setLoading(true);
    setErr("");

    const timeParams = timeKeyToArticleParams(timeKey);
    const optsBase = {
      industry_slug: industrySlug,
      sort,
      ...timeParams,
      page_size: 40,
      page: 1,
    };

    const segmentId = typeof segmentScope === "number" ? segmentScope : undefined;
    const segmentIdsCsv =
      segmentScope === "other" && overflowSegments.length > 0 ? overflowSegments.map((s) => s.id).join(",") : undefined;

    publicApi
      .articles({
        ...optsBase,
        ...(segmentId != null ? { segment_id: segmentId } : {}),
        ...(segmentIdsCsv ? { segment_ids: segmentIdsCsv } : {}),
      })
      .then((d) => {
        if (cancelled) return;
        setList(d.items ?? []);
        setLoading(false);
      })
      .catch((e) => {
        if (!cancelled) {
          setErr(String(e));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [segments, industrySlug, segmentScope, overflowSegments, timeKey, sort]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 text-slate-100">
      <h1 className="text-2xl font-semibold text-white">{t("navResources")}</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-400">{t("resourcesIntro")}</p>
      <p className="mt-2 text-xs text-slate-500">{t("resourcesNavHint")}</p>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("uiNavTheme")}</span>
        {industries.map((ind) => (
          <button
            key={ind.id}
            type="button"
            onClick={() => {
              setIndustrySlug(ind.slug);
              try {
                localStorage.setItem("publicIndustrySlug", ind.slug);
              } catch {
                /* ignore */
              }
            }}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
              industrySlug === ind.slug
                ? "bg-gradient-to-r from-amber-500/30 to-cyan-500/20 text-white ring-1 ring-amber-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {ind.name}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("uiNavSegment")}</span>
        <button
          type="button"
          onClick={() => setSegmentScope("all")}
          className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
            segmentScope === "all"
              ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/20 text-white ring-1 ring-cyan-400/40"
              : "bg-white/5 text-slate-300 hover:text-white"
          }`}
        >
          {t("resourcesSegmentAll")}
        </button>
        {primarySegments.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSegmentScope(s.id)}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
              segmentScope === s.id
                ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/20 text-white ring-1 ring-cyan-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {s.name}
          </button>
        ))}
        {overflowSegments.length > 0 ? (
          <button
            type="button"
            onClick={() => setSegmentScope("other")}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
              segmentScope === "other"
                ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/20 text-white ring-1 ring-cyan-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {t("uiNavOther")}
          </button>
        ) : null}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("resourcesTimeFilter")}</span>
        {TIME_FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setTimeKey(f.key)}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
              timeKey === f.key
                ? "bg-fuchsia-500/25 text-white ring-1 ring-fuchsia-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {t(f.labelKey)}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <span className="self-center text-xs uppercase tracking-wider text-slate-500">{t("resourcesSort")}</span>
        <button
          type="button"
          onClick={() => setSort("hot")}
          className={`rounded-lg px-3 py-1.5 text-sm ${sort === "hot" ? "bg-cyan-500/30 text-white" : "bg-white/5 text-slate-400"}`}
        >
          {t("resourcesSortHot")}
        </button>
        <button
          type="button"
          onClick={() => setSort("latest")}
          className={`rounded-lg px-3 py-1.5 text-sm ${sort === "latest" ? "bg-cyan-500/30 text-white" : "bg-white/5 text-slate-400"}`}
        >
          {t("resourcesSortLatest")}
        </button>
      </div>

      {err ? <p className="mt-4 text-sm text-red-400">{err}</p> : null}
      {loading ? <p className="mt-6 text-sm text-slate-500">{t("resourcesLoading")}</p> : null}

      {!loading ? (
        <ul className="mt-8 space-y-4">
          {list.map((a) => (
            <li key={a.id} className="rounded-2xl border border-white/10 bg-white/5 p-4 transition hover:border-cyan-500/30">
              <Link to={`/resources/${a.id}`} className="block">
                <div className="font-medium text-white">{a.title}</div>
                <div className="mt-1 text-sm text-slate-400">{a.summary}</div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  {segmentScope === "all" && segmentNameById.get(a.segment_id) ? (
                    <span className="text-cyan-300/80">{segmentNameById.get(a.segment_id)}</span>
                  ) : null}
                  {a.published_at ? <span>{a.published_at.slice(0, 10)}</span> : null}
                  <span>{a.content_type}</span>
                  {a.third_party_source ? <span>{t("source")}: {a.third_party_source}</span> : null}
                </div>
              </Link>
            </li>
          ))}
          {list.length === 0 ? <li className="text-sm text-slate-500">{t("resourcesEmptyTopic")}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
