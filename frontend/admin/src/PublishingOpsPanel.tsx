import { useCallback, useEffect, useState } from "react";
import { adminApi, type PublishingOpsOverview } from "./api";

const SITE_ORDER = ["ai-trends-news", "ai-trends-apps", "douyin", "xhs", "toutiao", "douban"];

function StackedDailyChart({ daily }: { daily: PublishingOpsOverview["daily"] }) {
  if (!daily.length) return <p className="muted tiny">暂无发布记录</p>;
  const totals = daily.map((row) => {
    let articles = 0;
    let videos = 0;
    for (const sk of SITE_ORDER) {
      const c = row.sites[sk];
      if (c) {
        articles += c.articles;
        videos += c.videos;
      }
    }
    return { date: row.date, articles, videos, total: articles + videos };
  });
  const max = Math.max(1, ...totals.map((t) => t.total));
  return (
    <div className="connector-daily-chart">
      {totals.map((t) => (
        <div
          key={t.date}
          className="connector-daily-chart__col"
          title={`${t.date}\n文章 ${t.articles} · 视频 ${t.videos}`}
        >
          <div style={{ display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%", width: "100%", alignItems: "center", gap: 2 }}>
            {t.videos > 0 ? (
              <div
                className="connector-daily-chart__bar"
                style={{ height: `${(t.videos / max) * 55}%`, background: "linear-gradient(180deg,#f59e0b,#d97706)", maxWidth: 28 }}
              />
            ) : null}
            {t.articles > 0 ? (
              <div
                className="connector-daily-chart__bar"
                style={{ height: `${(t.articles / max) * 55}%`, maxWidth: 28 }}
              />
            ) : null}
          </div>
          <div className="connector-daily-chart__date">{t.date.slice(5)}</div>
        </div>
      ))}
    </div>
  );
}

export function PublishingOpsPanel({ onError }: { onError: (msg: string) => void }) {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<PublishingOpsOverview | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await adminApi.publishingStats(days));
    } catch (e) {
      onError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [days, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const s = data?.summary;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>发布运营统计</h2>
      <p className="muted tiny" style={{ marginBottom: 12 }}>
        本站已发文章按日/分类统计；外站（抖音等）请在 <strong>Pipeline 中控台</strong> 标记发布后汇总。
        {data?.external_channels_note ? ` ${data.external_channels_note}` : null}
      </p>

      <div className="row-actions" style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="btn-ghost" style={{ padding: "6px 10px" }}>
          <option value={7}>近 7 天</option>
          <option value={30}>近 30 天</option>
          <option value={90}>近 90 天</option>
        </select>
        <button type="button" className="secondary" onClick={() => void load()} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </button>
      </div>

      {s ? (
        <div className="connector-stat-cards" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 10, marginBottom: 16 }}>
          <div className="card settings-panel">
            <div className="muted tiny">期内发文</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.published_in_period}</div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">今日发文</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.today_articles_on_site}</div>
          </div>
          <div className="card settings-panel">
            <div className="muted tiny">草稿箱</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{s.draft_count}</div>
          </div>
        </div>
      ) : null}

      {data ? (
        <>
          <div className="card settings-panel" style={{ marginBottom: 16 }}>
            <h3 className="settings-title" style={{ marginTop: 0 }}>
              站内 · 每日发布（蓝=文章）
            </h3>
            <StackedDailyChart daily={data.daily} />
          </div>

          <div className="card settings-panel" style={{ marginBottom: 16 }}>
            <h3 className="settings-title" style={{ marginTop: 0 }}>
              分类分布（期内站内已发）
            </h3>
            {data.categories.length ? (
              <table className="admin-table" style={{ width: "100%", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th>分类</th>
                    <th>篇数</th>
                  </tr>
                </thead>
                <tbody>
                  {data.categories.map((c) => (
                    <tr key={c.category}>
                      <td>{c.category}</td>
                      <td>{c.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted tiny">暂无</p>
            )}
          </div>

          {data.categories_by_site?.map((block) => (
            <div key={block.site_key} className="card settings-panel" style={{ marginBottom: 16 }}>
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                {block.site_label} · 分类
              </h3>
              {block.items.length ? (
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                  {block.items.map((it) => (
                    <li key={it.category}>
                      {it.category} <span className="muted">({it.count})</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted tiny">暂无</p>
              )}
            </div>
          ))}

          <div className="card settings-panel" style={{ marginBottom: 16 }}>
            <h3 className="settings-title" style={{ marginTop: 0 }}>
              数据源维护（多久没出新稿）
            </h3>
            <table className="admin-table" style={{ width: "100%", fontSize: 13 }}>
              <thead>
                <tr>
                  <th>数据源</th>
                  <th>连接器</th>
                  <th>期内文章</th>
                  <th>最近发布</th>
                  <th>最近同步</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {data.sources_maintenance.map((r) => (
                  <tr key={r.source_key + r.connector_name}>
                    <td>{r.source_key}</td>
                    <td>
                      {r.connector_name}
                      {!r.enabled ? <span className="muted"> (停)</span> : null}
                    </td>
                    <td>{r.articles_in_period}</td>
                    <td className="muted tiny">{r.last_published_at?.replace("T", " ").replace("Z", "") || "—"}</td>
                    <td className="muted tiny">{r.last_sync_at?.replace("T", " ").replace("Z", "") || "—"}</td>
                    <td>{r.stale ? <span style={{ color: "#b45309" }}>久未更新</span> : "正常"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.digest_maintenance ? (
            <div className="card settings-panel">
              <h3 className="settings-title" style={{ marginTop: 0 }}>
                日报/飞书维护
              </h3>
              <p className="tiny" style={{ margin: 0 }}>
                最近摘要日 {data.digest_maintenance.digest_date} · 状态 {data.digest_maintenance.status} · 更新{" "}
                {data.digest_maintenance.updated_at?.replace("T", " ").replace("Z", "")}
              </p>
            </div>
          ) : null}
        </>
      ) : (
        <p className="muted">{loading ? "加载中…" : "无数据"}</p>
      )}
    </div>
  );
}
