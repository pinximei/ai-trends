import { useCallback, useEffect, useState } from "react";
import { adminApi, type ConnectorStatsOverview } from "./api";

function maxOf(rows: { value: number }[]) {
  return Math.max(1, ...rows.map((r) => r.value));
}

function BarChart({
  title,
  rows,
  valueKey,
  labelKey,
  color = "#3b82f6",
}: {
  title: string;
  rows: Record<string, unknown>[];
  valueKey: string;
  labelKey: string;
  color?: string;
}) {
  const data = rows.map((r) => ({
    label: String(r[labelKey] ?? ""),
    value: Number(r[valueKey] ?? 0),
  }));
  const max = maxOf(data);
  return (
    <div className="card settings-panel" style={{ marginBottom: 16 }}>
      <h3 className="settings-title" style={{ marginTop: 0 }}>
        {title}
      </h3>
      {data.length === 0 ? (
        <p className="muted tiny">暂无数据</p>
      ) : (
        <div className="connector-chart">
          {data.map((row) => (
            <div key={row.label} className="connector-chart__row">
              <div className="connector-chart__label" title={row.label}>
                {row.label}
              </div>
              <div className="connector-chart__track">
                <div
                  className="connector-chart__bar"
                  style={{ width: `${(row.value / max) * 100}%`, background: color }}
                />
              </div>
              <div className="connector-chart__val">{row.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DailyChart({ daily }: { daily: ConnectorStatsOverview["daily"] }) {
  const max = maxOf(daily.map((d) => ({ value: d.sync_runs })));
  return (
    <div className="card settings-panel" style={{ marginBottom: 16 }}>
      <h3 className="settings-title" style={{ marginTop: 0 }}>
        每日同步次数
      </h3>
      <div className="connector-daily-chart">
        {daily.map((d) => (
          <div key={d.date} className="connector-daily-chart__col" title={`${d.date}\n同步 ${d.sync_runs} · 入库 ${d.rows_ingested} · 文章 ${d.articles_created} · 失败 ${d.errors}`}>
            <div
              className="connector-daily-chart__bar"
              style={{ height: `${(d.sync_runs / max) * 100}%` }}
            />
            <div className="connector-daily-chart__date">{d.date.slice(5)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ConnectorStatsPanel({ onError }: { onError: (msg: string) => void }) {
  const [days, setDays] = useState(14);
  const [stats, setStats] = useState<ConnectorStatsOverview | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await adminApi.connectorStats(days);
      setStats(data);
    } catch (e) {
      onError(e instanceof Error ? e.message : "加载统计失败");
    } finally {
      setLoading(false);
    }
  }, [days, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const s = stats?.summary;

  return (
    <div>
      <div className="row-actions" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
        <h2 style={{ margin: 0, flex: 1 }}>连接器统计</h2>
        <select
          className="btn-ghost"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          style={{ padding: "6px 10px" }}
        >
          <option value={7}>近 7 天</option>
          <option value={14}>近 14 天</option>
          <option value={30}>近 30 天</option>
        </select>
        <button type="button" className="secondary" onClick={() => void load()} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </button>
      </div>

      {s ? (
        <div className="connector-stat-cards" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10, marginBottom: 16 }}>
          <div className="card settings-panel">
            <div className="muted tiny">同步次数</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.sync_runs}</div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">成功率</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {s.success_rate != null ? `${Math.round(s.success_rate * 100)}%` : "—"}
            </div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">新建文章</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.articles_created}</div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">入库行数</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.rows_ingested}</div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">LLM 润色</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {s.llm_polish_ok}/{s.llm_polish_calls}
            </div>
            <div className="muted tiny">
              token {s.llm_input_tokens}+{s.llm_output_tokens}
            </div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">连接器</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>
              {s.connectors_enabled}/{s.connectors_total}
            </div>
            <div className="muted tiny">已启用</div>
          </div>
        </div>
      ) : null}

      {stats ? (
        <>
          <DailyChart daily={stats.daily} />
          <BarChart
            title="各连接器 · 新建文章"
            rows={stats.by_connector}
            valueKey="articles_created"
            labelKey="name"
            color="#22c55e"
          />
          <BarChart
            title="各连接器 · 入库行数"
            rows={stats.by_connector}
            valueKey="rows_ingested"
            labelKey="name"
            color="#3b82f6"
          />
          <BarChart
            title="各数据源 · 新建文章"
            rows={stats.by_source}
            valueKey="articles_created"
            labelKey="source_key"
            color="#a855f7"
          />

          <div className="card settings-panel">
            <h3 className="settings-title" style={{ marginTop: 0 }}>
              连接器明细
            </h3>
            <div style={{ overflowX: "auto" }}>
              <table className="admin-table" style={{ width: "100%", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>数据源</th>
                    <th>同步</th>
                    <th>成功</th>
                    <th>失败</th>
                    <th>入库行</th>
                    <th>文章</th>
                    <th>上次同步</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.by_connector.map((c) => (
                    <tr key={c.connector_id}>
                      <td>
                        {c.name}
                        {!c.enabled ? <span className="muted tiny"> (停)</span> : null}
                      </td>
                      <td>{c.admin_source_key || "—"}</td>
                      <td>{c.sync_runs}</td>
                      <td>{c.ok_runs}</td>
                      <td>{c.error_runs}</td>
                      <td>{c.rows_ingested}</td>
                      <td>{c.articles_created ?? 0}</td>
                      <td className="muted tiny">{c.last_sync_at?.replace("T", " ").replace("Z", "") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <p className="muted">{loading ? "加载中…" : "无数据"}</p>
      )}
    </div>
  );
}
