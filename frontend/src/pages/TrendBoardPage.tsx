import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { publicApi } from "@/lib/publicApi";
import { useI18n } from "@/i18n";
import { TrendTimelineChart } from "@/components/TrendTimelineChart";
import { SegmentHeatCompareChart } from "@/components/SegmentHeatCompareChart";
import { buildNormalizedCompareRows, rankByMeanNormalized, type SegmentSeries } from "@/lib/trendCompare";

const DAY_OPTIONS = [7, 30, 90, 180] as const;
/** 趋势页自动与服务器对齐的周期（与后台热门快照调度一致为约每 3 天） */
const TREND_AUTO_REFRESH_MS = 3 * 24 * 60 * 60 * 1000;

function describeTrendZh(points: { t: string; value: number }[], metricName: string): string {
  if (points.length < 2) {
    return `${metricName}：区间内数据点不足，暂无法判断走势。`;
  }
  const vals = points.map((p) => p.value);
  const first = vals[0];
  const last = vals[vals.length - 1];
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const diff = last - first;
  const pct = Math.abs(first) > 1e-9 ? (diff / Math.abs(first)) * 100 : last !== 0 ? 100 : 0;
  const dir = diff > 1e-6 ? "上升" : diff < -1e-6 ? "下降" : "基本持平";
  return `${metricName}：在所选时间范围内走势${dir}，由 ${first.toFixed(2)} 变动至 ${last.toFixed(2)}（相对变化约 ${pct.toFixed(1)}%）；区间内最低 ${min.toFixed(2)}、最高 ${max.toFixed(2)}。`;
}

function describeTrendEn(points: { t: string; value: number }[], metricName: string): string {
  if (points.length < 2) {
    return `${metricName}: not enough points in this window.`;
  }
  const vals = points.map((p) => p.value);
  const first = vals[0];
  const last = vals[vals.length - 1];
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const diff = last - first;
  const pct = Math.abs(first) > 1e-9 ? (diff / Math.abs(first)) * 100 : last !== 0 ? 100 : 0;
  const dir = diff > 1e-6 ? "up" : diff < -1e-6 ? "down" : "flat";
  return `${metricName}: ${dir} from ${first.toFixed(2)} to ${last.toFixed(2)} (~${pct.toFixed(1)}% vs start); min ${min.toFixed(2)}, max ${max.toFixed(2)}.`;
}

type SegmentRow = { id: number; slug: string; name: string };
type IndustryRow = { id: number; slug: string; name: string };

export function TrendBoardPage() {
  const { t, lang } = useI18n();
  const [industries, setIndustries] = useState<IndustryRow[]>([]);
  /** 与资源页共用 localStorage，便于切换页面时保持同一行业 */
  const [industrySlug, setIndustrySlug] = useState("");
  /** 元数据（板块 + 指标）是否已从首屏请求落地；避免 segments===null 时趋势 effect 空跑导致一直「加载中」。 */
  const [metaReady, setMetaReady] = useState(false);
  const [segments, setSegments] = useState<SegmentRow[]>([]);
  const [metricsBySeg, setMetricsBySeg] = useState<Record<number, { key: string; name: string }[]>>({});
  const [days, setDays] = useState<number>(30);
  const [focusSegmentId, setFocusSegmentId] = useState<number | null>(null);
  const [summary, setSummary] = useState<{ key: string; name: string; avg: number | null }[]>([]);
  const [seriesMap, setSeriesMap] = useState<Record<string, { t: string; value: number }[]>>({});
  const [hotAt, setHotAt] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [trendsLoading, setTrendsLoading] = useState(false);
  const [topBlock, setTopBlock] = useState<Awaited<ReturnType<typeof publicApi.segmentTopProducts>> | null>(null);
  const [topLoading, setTopLoading] = useState(false);
  const [topErr, setTopErr] = useState("");
  /** 每约 3 天递增一次，触发趋势与 TOP 数据重新请求 */
  const [trendAutoRefreshTick, setTrendAutoRefreshTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setTrendAutoRefreshTick((n) => n + 1);
      if (industrySlug) {
        publicApi
          .hot({ industry_slug: industrySlug })
          .then((h) => setHotAt(h.generated_at ?? null))
          .catch(() => {});
      }
    }, TREND_AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [industrySlug]);

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
    publicApi
      .hot({ industry_slug: industrySlug })
      .then((h) => setHotAt(h.generated_at))
      .catch(() => {});
  }, [industrySlug]);

  useEffect(() => {
    setFocusSegmentId(null);
  }, [industrySlug]);

  useEffect(() => {
    setSummary([]);
    setSeriesMap({});
    setErr("");
  }, [industrySlug]);

  useEffect(() => {
    if (!industrySlug) return;
    let cancelled = false;
    setMetaReady(false);
    (async () => {
      try {
        /** 并行拉取；metrics 按行业过滤，只加载当前行业下板块的指标。 */
        const [segs, allM] = await Promise.all([
          publicApi.segments({ industry_slug: industrySlug }),
          publicApi.metrics({ industry_slug: industrySlug }),
        ]);
        if (cancelled) return;
        const map: Record<number, { id: number; key: string; name: string }[]> = {};
        for (const m of allM) {
          const sid = Number(m.segment_id);
          if (Number.isNaN(sid)) continue;
          if (!map[sid]) map[sid] = [];
          map[sid].push({ id: m.id, key: m.key, name: m.name });
        }
        for (const sid of Object.keys(map)) {
          map[Number(sid)].sort((a, b) => a.id - b.id);
        }
        setSegments(segs);
        setMetricsBySeg(map);
      } catch (e) {
        if (!cancelled) {
          setErr(String(e));
          setSegments([]);
          setMetricsBySeg({});
        }
      } finally {
        if (!cancelled) setMetaReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [industrySlug]);

  useEffect(() => {
    if (focusSegmentId == null) {
      setTopBlock(null);
      setTopErr("");
      setTopLoading(false);
      return;
    }
    let cancelled = false;
    setTopLoading(true);
    setTopErr("");
    publicApi
      .segmentTopProducts(focusSegmentId, { limit: 10 })
      .then((d) => {
        if (!cancelled) setTopBlock(d);
      })
      .catch((e) => {
        if (!cancelled) {
          setTopBlock(null);
          setTopErr(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setTopLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [focusSegmentId, trendAutoRefreshTick]);

  useEffect(() => {
    if (!metaReady) return;

    /** 单板块：必须已有该板块指标列表。多板块：至少一个板块有指标即可（不要求每个板块都有，避免永远 loading）。 */
    if (focusSegmentId != null) {
      if (!(metricsBySeg[focusSegmentId]?.length)) {
        setTrendsLoading(false);
        setErr(
          lang === "en"
            ? "This segment has no metrics yet. Add metrics in the admin console."
            : "该板块暂无指标数据，请稍后在后台为该板块配置指标。"
        );
        return;
      }
    } else if (segments.length > 0 && !segments.some((s) => (metricsBySeg[s.id]?.length ?? 0) > 0)) {
      setTrendsLoading(false);
      setErr(lang === "en" ? "No metric metadata yet. Configure metrics per segment in the admin console." : "暂无指标元数据，请稍后在后台配置各板块指标。");
      return;
    }

    let cancelled = false;
    setTrendsLoading(true);
    setErr("");
    (async () => {
      try {
        const sum = await publicApi.trendSummary({
          days,
          segment_id: focusSegmentId ?? undefined,
          industry_slug: industrySlug,
        });
        if (cancelled) return;
        setSummary(sum.metrics ?? []);

        const keysToLoad: { segId: number; key: string }[] = [];
        if (focusSegmentId != null) {
          const ms = metricsBySeg[focusSegmentId] ?? [];
          for (const m of ms) keysToLoad.push({ segId: focusSegmentId, key: m.key });
        } else {
          for (const s of segments) {
            const first = (metricsBySeg[s.id] ?? [])[0];
            if (first) keysToLoad.push({ segId: s.id, key: first.key });
          }
        }

        const next: Record<string, { t: string; value: number }[]> = {};
        await Promise.all(
          keysToLoad.map(async ({ segId, key }) => {
            const id = `${segId}:${key}`;
            const ser = await publicApi.trendSeries(key, { days, segment_id: segId, industry_slug: industrySlug });
            if (!cancelled) next[id] = ser.points ?? [];
          })
        );
        if (!cancelled) {
          setSeriesMap(next);
          setTrendsLoading(false);
        }
      } catch (e) {
        if (!cancelled) {
          setErr(String(e));
          setTrendsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [metaReady, industrySlug, days, focusSegmentId, segments, metricsBySeg, lang, trendAutoRefreshTick]);

  const chartBlocks = useMemo(() => {
    if (!metaReady) return [];
    if (focusSegmentId != null) {
      const ms = metricsBySeg[focusSegmentId] ?? [];
      return ms.map((m) => ({
        segmentId: focusSegmentId,
        segmentName: segments.find((s) => s.id === focusSegmentId)?.name ?? "",
        metricKey: m.key,
        metricName: m.name,
        points: seriesMap[`${focusSegmentId}:${m.key}`] ?? [],
      }));
    }
    return segments.map((s) => {
      const first = (metricsBySeg[s.id] ?? [])[0];
      const key = first?.key ?? "";
      return {
        segmentId: s.id,
        segmentName: s.name,
        metricKey: key,
        metricName: first?.name ?? "—",
        points: key ? seriesMap[`${s.id}:${key}`] ?? [] : [],
      };
    });
  }, [metaReady, focusSegmentId, segments, metricsBySeg, seriesMap]);

  /** 是否已有上一轮趋势结果；用于区分「首屏加载」与「切换筛选时的刷新」，避免整页被 loading 顶替。 */
  const hasTrendData = useMemo(() => {
    if (summary.length > 0) return true;
    return Object.values(seriesMap).some((pts) => pts.length > 0);
  }, [summary, seriesMap]);

  const overviewCompare = useMemo(() => {
    if (focusSegmentId != null || !metaReady || segments.length < 2) return null;
    const series: SegmentSeries[] = chartBlocks.map((b) => ({
      segmentId: b.segmentId,
      segmentName: b.segmentName,
      metricKey: b.metricKey,
      metricName: b.metricName,
      points: b.points,
    }));
    const rows = buildNormalizedCompareRows(series);
    const ranking = rankByMeanNormalized(series);
    const names: Record<number, string> = {};
    for (const s of segments) names[s.id] = s.name;
    return { rows, ranking, segmentIds: segments.map((s) => s.id), segmentNames: names, series };
  }, [metaReady, focusSegmentId, segments, chartBlocks]);

  const describe = lang === "en" ? describeTrendEn : describeTrendZh;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 text-slate-100">
      <h1 className="text-2xl font-semibold text-white">{t("navTrends")}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">{t("trendIntro")}</p>
      <p className="mt-2 text-xs text-slate-500">{t("publicIndustryHint")}</p>
      <p className="mt-2 text-xs text-cyan-400/90">
        {t("trendHotSnapshot")}: {hotAt ?? t("trendHotSnapshotPending")}
      </p>
      <p className="mt-2 max-w-3xl text-xs leading-relaxed text-slate-500">{t("trendAutoRefreshHint")}</p>

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("publicIndustry")}</span>
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
            className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
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
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("publicSegmentsInIndustry")}</span>
        <button
          type="button"
          onClick={() => setFocusSegmentId(null)}
          className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
            focusSegmentId == null
              ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/20 text-white ring-1 ring-cyan-400/40"
              : "bg-white/5 text-slate-300 hover:text-white"
          }`}
        >
          {t("trendAllSegments")}
        </button>
        {segments.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setFocusSegmentId(s.id)}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
              focusSegmentId === s.id
                ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/20 text-white ring-1 ring-cyan-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {s.name}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wider text-slate-500">{t("trendTimeRange")}</span>
        {DAY_OPTIONS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDays(d)}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium ${
              days === d
                ? "bg-fuchsia-500/25 text-white ring-1 ring-fuchsia-400/40"
                : "bg-white/5 text-slate-300 hover:text-white"
            }`}
          >
            {t("trendDays").replace("{n}", String(d))}
          </button>
        ))}
        {trendsLoading && hasTrendData ? (
          <span className="inline-flex items-center gap-2 text-xs text-slate-400" aria-live="polite">
            <span
              className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-600 border-t-cyan-400"
              aria-hidden
            />
            {t("trendLoading")}
          </span>
        ) : null}
      </div>

      {err ? <p className="mt-4 text-sm text-red-400">{err}</p> : null}

      {focusSegmentId != null ? (
        <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-4 shadow-[inset_0_0_40px_rgba(0,0,0,0.2)]">
          <h2 className="text-lg font-semibold text-white">{t("trendTop10Title")}</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">{t("trendTop10Hint")}</p>
          {topLoading ? <p className="mt-4 text-sm text-slate-500">{t("trendLoading")}</p> : null}
          {topErr ? <p className="mt-4 text-sm text-red-400">{topErr}</p> : null}
          {!topLoading && !topErr && topBlock ? (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-slate-500">
                    <th className="py-2 pr-3 font-medium">{t("trendColRank")}</th>
                    <th className="py-2 pr-3 font-medium">{t("trendColProduct")}</th>
                    <th className="py-2 pr-3 font-medium">{t("trendColHeat")}</th>
                    <th className="py-2 pr-3 font-medium">{t("trendColUsage")}</th>
                    <th className="py-2 pr-3 font-medium">{t("trendColSummary")}</th>
                    <th className="py-2 font-medium">{t("trendViewDetail")}</th>
                  </tr>
                </thead>
                <tbody>
                  {topBlock.items.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-slate-500">
                        {lang === "zh" ? "该板块下暂无已发布内容。" : "No published items in this segment."}
                      </td>
                    </tr>
                  ) : (
                    topBlock.items.map((row) => (
                      <tr key={row.id} className="border-b border-white/5 text-slate-300">
                        <td className="py-2 pr-3 font-mono text-slate-400">{row.rank}</td>
                        <td className="py-2 pr-3 font-medium text-white">{row.title}</td>
                        <td className="py-2 pr-3 font-mono text-slate-200">{row.heat_score.toFixed(1)}</td>
                        <td className="py-2 pr-3 font-mono text-slate-200">{row.activity_index.toFixed(1)}</td>
                        <td className="max-w-md py-2 pr-3 text-slate-400">
                          {row.summary ? (row.summary.length > 120 ? `${row.summary.slice(0, 120)}…` : row.summary) : "—"}
                        </td>
                        <td className="py-2">
                          <Link className="text-sky-400 hover:underline" to={`/resources/${row.id}`}>
                            {t("trendViewDetail")}
                          </Link>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      ) : null}

      {!metaReady ? <p className="mt-8 text-sm text-slate-500">{t("trendMetaLoading")}</p> : null}
      {metaReady && trendsLoading && !hasTrendData ? (
        <p className="mt-8 text-sm text-slate-500">{t("trendLoading")}</p>
      ) : null}

      {metaReady && overviewCompare && (!trendsLoading || hasTrendData) ? (
        <div
          className={`mt-8 space-y-6 transition-opacity duration-200 ${
            trendsLoading && hasTrendData ? "opacity-75" : "opacity-100"
          }`}
        >
          <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 shadow-[inset_0_0_40px_rgba(0,0,0,0.2)]">
            <h2 className="text-lg font-semibold text-white">{t("trendCompareTitle")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">{t("trendCompareHint")}</p>
            <div className="mt-4 h-[22rem] w-full min-h-[320px]">
              {overviewCompare.rows.length > 0 ? (
                <SegmentHeatCompareChart
                  rows={overviewCompare.rows}
                  segmentNames={overviewCompare.segmentNames}
                  segmentIds={overviewCompare.segmentIds}
                />
              ) : (
                <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-white/10 text-sm text-slate-500">
                  {t("trendNoSeries")}
                </div>
              )}
            </div>
            {overviewCompare.ranking.length > 0 ? (
              <div className="mt-4 rounded-xl border border-white/10 bg-slate-950/40 p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("trendCompareRank")}</div>
                <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-200">
                  {overviewCompare.ranking.map((r) => (
                    <li key={r.segmentId}>
                      <span className="font-medium text-white">{r.segmentName}</span>
                      <span className="text-slate-500"> — μ≈{r.meanNorm.toFixed(1)}</span>
                    </li>
                  ))}
                </ol>
                <p className="mt-3 text-sm text-slate-300">
                  {t("trendCompareLeader")}: <strong className="text-white">{overviewCompare.ranking[0]?.segmentName}</strong>
                </p>
              </div>
            ) : null}
          </section>

          <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <h2 className="text-base font-semibold text-white">{t("trendRawTableTitle")}</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[480px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-slate-500">
                    <th className="py-2 pr-4 font-medium">{t("trendTopic")}</th>
                    <th className="py-2 pr-4 font-medium">{t("trendMetricCol")}</th>
                    <th className="py-2 font-medium">{t("trendAvgCol")}</th>
                  </tr>
                </thead>
                <tbody>
                  {chartBlocks.map((b) => {
                    const avg = summary.find((m) => m.key === b.metricKey)?.avg;
                    return (
                      <tr key={b.segmentId} className="border-b border-white/5 text-slate-300">
                        <td className="py-2 pr-4 text-white">{b.segmentName}</td>
                        <td className="py-2 pr-4">{b.metricName}</td>
                        <td className="py-2 font-mono text-slate-200">{avg != null ? avg.toFixed(2) : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {lang === "zh"
                ? "上表为各板块「列表中的第一个指标」的原始均值；与折线图的 0–100 归一化尺度不同。"
                : "Table uses each segment’s first listed metric; units differ from the normalized chart."}
            </p>
          </section>
        </div>
      ) : null}

      {metaReady && !overviewCompare && chartBlocks.length > 0 && (!trendsLoading || hasTrendData) ? (
        <div
          className={`mt-8 grid gap-6 lg:grid-cols-2 transition-opacity duration-200 ${
            trendsLoading && hasTrendData ? "opacity-75" : "opacity-100"
          }`}
        >
          {chartBlocks.map((b) => {
            const data = b.points.map((p) => ({ x: p.t.slice(0, 10), y: p.value }));
            return (
              <section key={`${b.segmentId}-${b.metricKey}`} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4 shadow-[inset_0_0_40px_rgba(0,0,0,0.2)]">
                <div className="flex items-baseline justify-between gap-2">
                  <div>
                    <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{b.segmentName}</div>
                    <div className="mt-1 text-lg font-semibold text-white">{b.metricName}</div>
                  </div>
                  {summary.find((m) => m.key === b.metricKey) ? (
                    <div className="text-right text-sm text-slate-300">
                      μ {(summary.find((m) => m.key === b.metricKey)?.avg ?? 0).toFixed(2)}
                    </div>
                  ) : null}
                </div>
                <div className="mt-3 h-52 w-full">
                  {data.length > 0 ? <TrendTimelineChart data={data} /> : (
                    <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-white/10 text-sm text-slate-500">
                      {t("trendNoSeries")}
                    </div>
                  )}
                </div>
                <p className="mt-3 text-sm leading-relaxed text-slate-400">{describe(b.points, b.metricName)}</p>
              </section>
            );
          })}
        </div>
      ) : null}

      {metaReady && !trendsLoading && segments.length === 0 ? (
        <p className="mt-8 text-sm text-slate-500">{t("trendNoSegments")}</p>
      ) : null}
    </div>
  );
}
