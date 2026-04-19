import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { adminApi } from "./api";

type TableMeta = {
  key: string;
  label: string;
  has_time: boolean;
  time_hint: string | null;
  dimensions: Array<{ name: string; label: string }>;
};

function isoLocal(d: Date) {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function toIsoParam(s: string) {
  if (!s.trim()) return undefined;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

export function DataQueryPanel({ onError }: { onError: (msg: string) => void }) {
  const [meta, setMeta] = useState<TableMeta[]>([]);
  const [tableKey, setTableKey] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [segmentId, setSegmentId] = useState("");
  const [metricId, setMetricId] = useState("");
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [columns, setColumns] = useState<string[]>([]);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [segments, setSegments] = useState<Array<{ id: number; name: string }>>([]);
  const [metrics, setMetrics] = useState<Array<{ id: number; key: string; name: string }>>([]);

  const selected = useMemo(() => meta.find((m) => m.key === tableKey), [meta, tableKey]);

  useEffect(() => {
    adminApi
      .dataTables()
      .then((d) => {
        setMeta(d);
        setTableKey((k) => (k && d.some((x) => x.key === k) ? k : d[0]?.key ?? ""));
      })
      .catch((e) => onError(e instanceof Error ? e.message : "load tables failed"));
  }, [onError]);

  useEffect(() => {
    adminApi
      .productSegments()
      .then((list) =>
        setSegments(
          (list as Array<{ id: number; name: string }>).map((s) => ({
            id: Number(s.id),
            name: String(s.name ?? s.id),
          }))
        )
      )
      .catch(() => {});
    adminApi
      .productMetrics()
      .then((list) =>
        setMetrics(
          (list as Array<{ id: number; key: string; name: string }>).map((m) => ({
            id: Number(m.id),
            key: String(m.key),
            name: String(m.name),
          }))
        )
      )
      .catch(() => {});
  }, []);

  useEffect(() => {
    const u = new Date();
    const s = new Date(u.getTime() - 7 * 24 * 60 * 60 * 1000);
    setUntil(isoLocal(u));
    setSince(isoLocal(s));
  }, []);

  const runQuery = useCallback(
    async (nextOffset: number) => {
      if (!tableKey.trim()) return;
      setBusy(true);
      try {
        const r = await adminApi.dataRows({
          table: tableKey,
          since: selected?.has_time ? toIsoParam(since) : undefined,
          until: selected?.has_time ? toIsoParam(until) : undefined,
          segment_id: segmentId ? Number(segmentId) : undefined,
          metric_id: metricId ? Number(metricId) : undefined,
          status: status.trim() || undefined,
          limit,
          offset: nextOffset,
        });
        setColumns(r.columns);
        setRows(r.rows);
        setOffset(nextOffset);
        try {
          const c = await adminApi.dataRowsCount({
            table: tableKey,
            since: selected?.has_time ? toIsoParam(since) : undefined,
            until: selected?.has_time ? toIsoParam(until) : undefined,
            segment_id: segmentId ? Number(segmentId) : undefined,
            metric_id: metricId ? Number(metricId) : undefined,
            status: status.trim() || undefined,
          });
          setTotal(c.total);
        } catch {
          setTotal(null);
        }
      } catch (e) {
        onError(e instanceof Error ? e.message : "query failed");
      } finally {
        setBusy(false);
      }
    },
    [tableKey, since, until, segmentId, metricId, status, limit, selected, onError]
  );

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    runQuery(0).catch(() => {});
  }

  const showSeg = selected?.dimensions.some((d) => d.name === "segment_id");
  const showMet = selected?.dimensions.some((d) => d.name === "metric_id");
  const showStatus = selected?.dimensions.some((d) => d.name === "status");

  return (
    <section className="card data-query">
      <h3>数据查询</h3>
      <p className="muted tiny" style={{ marginTop: 0 }}>
        选择库表并筛选条件；长文本与 JSON 字段展示时可能截断。
      </p>

      <form className="grid" onSubmit={onSubmit}>
        <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          <label className="form-field" style={{ minWidth: 200 }}>
            数据表
            {meta.length === 0 ? (
              <span className="muted tiny" style={{ display: "block", marginTop: 6 }}>
                暂无可用表
              </span>
            ) : (
              <select value={tableKey} onChange={(e) => setTableKey(e.target.value)}>
                {meta.map((m) => (
                  <option key={m.key} value={m.key}>
                    {m.label} ({m.key})
                  </option>
                ))}
              </select>
            )}
          </label>
          {selected?.has_time ? (
            <>
              <label className="form-field">
                开始时间
                <input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} />
              </label>
              <label className="form-field">
                结束时间
                <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} />
              </label>
              <span className="muted tiny" style={{ alignSelf: "center" }}>
                时间列: {selected.time_hint ?? "—"}
              </span>
            </>
          ) : (
            <span className="muted tiny">此表无统一时间列，可不选时间。</span>
          )}
        </div>
        <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
          {showSeg ? (
            <label className="form-field" style={{ minWidth: 180 }}>
              板块
              <select value={segmentId} onChange={(e) => setSegmentId(e.target.value)}>
                <option value="">全部</option>
                {segments.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {showMet ? (
            <label className="form-field" style={{ minWidth: 200 }}>
              指标
              <select value={metricId} onChange={(e) => setMetricId(e.target.value)}>
                <option value="">全部</option>
                {metrics.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.key})
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {showStatus ? (
            <label className="form-field" style={{ minWidth: 140 }}>
              状态
              <input value={status} onChange={(e) => setStatus(e.target.value)} placeholder="如 published" />
            </label>
          ) : null}
          <label className="form-field" style={{ width: 100 }}>
            条数
            <input type="number" min={1} max={500} value={limit} onChange={(e) => setLimit(Number(e.target.value) || 100)} />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "查询中…" : "查询"}
          </button>
        </div>
      </form>

      <hr className="data-query__divider" />

      <div className="row between" style={{ marginBottom: 8 }}>
        <strong>结果</strong>
        <span className="muted tiny">
          {total != null ? `约 ${total} 条匹配 · ` : ""}
          本页 {rows.length} 条 · offset {offset}
        </span>
      </div>
      {columns.length === 0 ? (
        <div className="muted tiny">提交查询后显示结果。</div>
      ) : (
        <div className="data-query__table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>
                      <span className="data-query__cell" title={String(row[c] ?? "")}>
                        {formatCell(row[c])}
                      </span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length >= limit ? (
        <div className="row" style={{ marginTop: 10 }}>
          <button type="button" disabled={busy} onClick={() => runQuery(offset + limit).catch(() => {})}>
            下一页
          </button>
          {offset > 0 ? (
            <button type="button" disabled={busy} onClick={() => runQuery(Math.max(0, offset - limit)).catch(() => {})}>
              上一页
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
