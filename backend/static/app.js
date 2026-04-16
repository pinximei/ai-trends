async function api(path, options = {}) {
  const res = await fetch(path, options);
  const json = await res.json();
  if (!res.ok || json.code !== 0) throw new Error(json.message || "request failed");
  return json.data;
}

function byId(id) {
  return document.getElementById(id);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function renderDashboard() {
  const [summary, trends] = await Promise.all([api("/api/v1/dashboard/summary"), api("/api/v1/trends")]);
  byId("kpis").innerHTML = `
    <div class="card"><h3>Active Use Cases</h3><p>${summary.active_use_cases}</p></div>
    <div class="card"><h3>New Apps</h3><p>${summary.new_apps}</p></div>
    <div class="card"><h3>Emerging Trends</h3><p>${summary.emerging_trends}</p></div>
    <div class="card"><h3>Updated At</h3><p>${esc(summary.updated_at || "-")}</p></div>
  `;
  byId("top-trends").innerHTML = trends.items
    .map(
      (t) => `<tr><td><a href="/trend/${esc(t.trend_key)}">${esc(t.trend_key)}</a></td><td>${t.trend_score}</td><td>${t.confidence}</td><td>${t.sample_size}</td></tr>`
    )
    .join("");
}

async function renderTrends() {
  const data = await api("/api/v1/trends");
  byId("trend-rows").innerHTML = data.items
    .map(
      (t) =>
        `<tr><td><a href="/trend/${esc(t.trend_key)}">${esc(t.trend_key)}</a></td><td>${t.trend_score}</td><td>${esc(
          t.lifecycle_stage
        )}</td><td>${t.confidence}</td><td>${t.sample_size}</td></tr>`
    )
    .join("");
}

async function renderInspirations() {
  const data = await api("/api/v1/inspirations");
  byId("inspiration-list").innerHTML = data.items
    .map(
      (i) =>
        `<article class="card"><h3>${esc(i.title)}</h3><p>Source: ${esc(i.source)} | Score: ${i.evidence_score}</p><p><a href="/trend/${esc(
          i.trend_key
        )}">Trend</a> · <a href="/evidence/${esc(i.signal_id)}">Evidence</a></p></article>`
    )
    .join("");
}

async function renderTrendDetail(key) {
  const [trend, timeline] = await Promise.all([api(`/api/v1/trends/${key}`), api(`/api/v1/trends/${key}/timeline`)]);
  byId("trend-title").textContent = key;
  byId("trend-meta").innerHTML = `Score ${trend.trend_score} · Confidence ${trend.confidence || "-"} · Stage ${trend.lifecycle_stage}`;
  byId("trend-points").innerHTML = timeline.points
    .map((p) => `<li>${esc(p.period_start)} : ${p.score}</li>`)
    .join("");
  byId("suggestion").textContent =
    "Next Step: define one hypothesis, run a 2-week pilot, track one success metric, and record risks before scaling.";
}

async function renderEvidence(signalId) {
  const ev = await api(`/api/v1/evidences/${signalId}`);
  byId("evidence-meta").innerHTML = `
    <p><strong>Signal:</strong> ${esc(ev.signal_id)}</p>
    <p><strong>Trend:</strong> <a href="/trend/${esc(ev.trend_key)}">${esc(ev.trend_key)}</a></p>
    <p><strong>Source:</strong> ${esc(ev.source)}</p>
    <p><strong>URL:</strong> <a href="${esc(ev.evidence_url)}" target="_blank">${esc(ev.evidence_url)}</a></p>
    <p><strong>Trace:</strong> ${esc(ev.trace)}</p>
  `;
}

async function renderCategories() {
  const c = await api("/api/v1/categories");
  byId("category-list").innerHTML = c.items.map((x) => `<li>${esc(x)}</li>`).join("");
}

async function renderMethodology() {
  const m = await api("/api/v1/meta/methodology");
  byId("methodology-text").textContent = m.summary;
}

async function renderAdminCompliance() {
  const data = await api("/api/v1/admin/compliance/removal-requests");
  byId("admin-removal-rows").innerHTML = data.items
    .map(
      (r) =>
        `<tr><td>${esc(r.ticket_id)}</td><td>${esc(r.status)}</td><td><button data-ticket="${esc(
          r.ticket_id
        )}" class="resolve-btn">Resolve</button></td></tr>`
    )
    .join("");
  document.querySelectorAll(".resolve-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/v1/admin/compliance/removal-requests/${btn.dataset.ticket}/resolve`, { method: "POST" });
      renderAdminCompliance();
    });
  });
}

async function init() {
  const page = document.body.dataset.view;
  try {
    if (page === "dashboard") await renderDashboard();
    if (page === "trends") await renderTrends();
    if (page === "inspirations") await renderInspirations();
    if (page === "trend-detail") await renderTrendDetail(document.body.dataset.trendKey);
    if (page === "evidence") await renderEvidence(document.body.dataset.signalId);
    if (page === "categories") await renderCategories();
    if (page === "methodology") await renderMethodology();
    if (page === "admin-compliance") await renderAdminCompliance();
  } catch (e) {
    const box = byId("error-box");
    if (box) {
      box.style.display = "block";
      box.textContent = `Load failed: ${e.message}`;
    }
  }
}

document.addEventListener("DOMContentLoaded", init);
