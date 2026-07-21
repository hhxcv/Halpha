const state = { summary: null, rows: [], filtered: [], selected: "ETHUSDT", sort: "pearson", direction: -1, page: 1 };
const columns = [
  ["symbol", "对象", "symbol"], ["pearson", "Pearson", "number"], ["spearman", "Spearman", "number"],
  ["beta", "BTC β", "number"], ["r_squared", "R²", "number"], ["volatility_ratio", "波动倍数", "ratio"],
  ["relative_strength_7d", "7日相对", "percent"], ["relative_strength_30d", "30日相对", "percent"],
  ["relative_strength_90d", "90日相对", "percent"], ["q_value_by", "BY q值", "q"], ["n_obs", "N", "integer"]
];
const el = (id) => document.getElementById(id);
const number = (value, digits = 2) => value == null || !Number.isFinite(Number(value)) ? "—" : Number(value).toFixed(digits);
const pct = (value) => value == null || !Number.isFinite(Number(value)) ? "—" : `${Number(value) >= 0 ? "+" : ""}${(Number(value) * 100).toFixed(1)}%`;
const qfmt = (value) => value == null ? "—" : Number(value) < 0.001 ? Number(value).toExponential(1) : Number(value).toFixed(3);
const utc = (value) => value ? new Intl.DateTimeFormat("zh-CN", { timeZone: "UTC", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) + " UTC" : "—";
const signedClass = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";

async function api(path, options) {
  const response = await fetch(path, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function renderSummary() {
  const s = state.summary;
  el("cutoff").textContent = utc(s.data_cutoff_utc);
  el("next-refresh").textContent = utc(s.monitor?.next_attempt_utc);
  el("universe-time").textContent = utc(s.universe.snapshot_time_utc);
  const status = s.monitor?.last_error ? "刷新失败 · 保留上次结果" : s.monitor?.refresh_in_progress ? "刷新中" : s.status;
  el("status").textContent = status;
  el("status").className = `status ${s.status === "OK" && !s.monitor?.last_error ? "" : s.status === "PARTIAL" ? "partial" : "error"}`;
  el("eligible").textContent = s.counts.eligible_objects.toLocaleString("zh-CN");
  el("coverage").textContent = `已分析 ${s.counts.analyzed} · 样本不足 ${s.counts.insufficient_sample}`;
  el("significant").textContent = s.counts.statistically_significant.toLocaleString("zh-CN");
  el("strong").textContent = s.counts.strong_association.toLocaleString("zh-CN");
  el("median-beta").textContent = number(s.median_beta, 2);
  el("scatter-scope").textContent = `${s.counts.analyzed} 个同口径对象 · 365 日 · 点大小为波动倍数`;
  el("refresh-button").disabled = Boolean(s.monitor?.refresh_in_progress);
  el("warnings").innerHTML = s.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("");
  renderCrosschecks();
  renderFailures();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[character]);
}

function renderCrosschecks() {
  const checks = state.summary.cross_source_checks || [];
  el("crosschecks").innerHTML = checks.length ? checks.map((row) => row.status === "COMPARED"
    ? `<div class="evidence-row"><b>${escapeHtml(row.symbol)}</b><span>ρ ${number(row.coin_metrics_pearson)} · β ${number(row.coin_metrics_beta)}</span><strong class="${row.direction_agreement ? "positive" : "negative"}">${row.direction_agreement ? "同向" : "异向"}</strong></div>`
    : `<div class="evidence-row"><b>${escapeHtml(row.symbol)}</b><span>${escapeHtml(row.status)}</span><strong>—</strong></div>`).join("")
    : `<p class="boundary">本次没有可用跨源结果；主数据仍完整保留。</p>`;
}

function renderFailures() {
  const failures = state.summary.failures || [];
  const monitorError = state.summary.monitor?.last_error;
  const items = monitorError ? [{ symbol: "MONITOR", status: "REFRESH_ERROR", error: monitorError }, ...failures] : failures;
  el("failures").innerHTML = items.length ? items.slice(0, 8).map((row) => `<div class="evidence-row"><b>${escapeHtml(row.symbol)}</b><span title="${escapeHtml(row.error)}">${escapeHtml(row.status)}</span><strong class="negative">需检查</strong></div>`).join("") : `<div class="evidence-row"><b>完整</b><span>无失败或陈旧对象</span><strong class="positive">OK</strong></div>`;
}

function renderScatter() {
  const rows = state.rows.filter((row) => row.status === "ANALYZED");
  const colors = rows.map((row) => row.strong_association ? "#e8a93d" : row.statistically_significant ? "#34bdd6" : "#49616f");
  const sizes = rows.map((row) => Math.max(6, Math.min(30, 5 + 6 * Math.sqrt(Number(row.volatility_ratio || 0)))));
  const labels = new Set(["ETHUSDT", "SOLUSDT", "SUIUSDT", "DOGEUSDT"]);
  Plotly.react("scatter", [{
    // SVG scatter is ample for the current ~400-point universe and remains
    // usable in hardened browsers where WebGL is disabled.
    type: "scatter", mode: "markers", x: rows.map((row) => row.pearson), y: rows.map((row) => row.beta),
    text: rows.map((row) => `${row.symbol}<br>Pearson ${number(row.pearson)}<br>β ${number(row.beta)}<br>波动 ${number(row.volatility_ratio)}×`),
    customdata: rows.map((row) => row.symbol), hovertemplate: "%{text}<extra></extra>",
    marker: { color: colors, size: sizes, opacity: .78, line: { color: "#0a1116", width: 1 } }
  }, {
    type: "scatter", mode: "text", x: rows.filter((row) => labels.has(row.symbol)).map((row) => row.pearson),
    y: rows.filter((row) => labels.has(row.symbol)).map((row) => row.beta), text: rows.filter((row) => labels.has(row.symbol)).map((row) => row.base_asset),
    textposition: "top center", textfont: { color: "#edf3f6", size: 11 }, hoverinfo: "skip"
  }], plotLayout("Pearson 日收益相关", "BTC β", { x: [-1, 1], y: null, shapes: [
    { type: "line", x0: .5, x1: .5, y0: 0, y1: 1, yref: "paper", line: { color: "#936f32", dash: "dot" } },
    { type: "line", x0: -.5, x1: -.5, y0: 0, y1: 1, yref: "paper", line: { color: "#936f32", dash: "dot" } },
    { type: "line", x0: -1, x1: 1, y0: 0, y1: 0, line: { color: "#54636d", dash: "dot" } }
  ]}), { displayModeBar: false, responsive: true });
  el("scatter").on("plotly_click", (event) => selectSymbol(event.points[0].customdata));
}

function plotLayout(xTitle, yTitle, options = {}) {
  return {
    paper_bgcolor: "#0c151c", plot_bgcolor: "#0c151c", margin: { l: 58, r: 18, t: 18, b: 50 },
    font: { family: "Inter, system-ui, sans-serif", color: "#8e9da7", size: 11 }, showlegend: false,
    xaxis: { title: xTitle, range: options.x, gridcolor: "#1b2831", zerolinecolor: "#40515c", fixedrange: true },
    yaxis: { title: yTitle, range: options.y, gridcolor: "#1b2831", zerolinecolor: "#40515c", fixedrange: true },
    shapes: options.shapes || [], hoverlabel: { bgcolor: "#101b23", bordercolor: "#34bdd6", font: { color: "#edf3f6" } }
  };
}

async function selectSymbol(symbol) {
  state.selected = symbol;
  el("selected-symbol").textContent = symbol;
  el("rolling-scope").textContent = `90 日窗口 · 至 ${utc(state.summary?.data_cutoff_utc)} · 点击散点或表格切换`;
  renderTable();
  const detail = await api(`/api/detail?symbol=${encodeURIComponent(symbol)}`);
  const rolling = detail.rolling || [];
  Plotly.react("rolling", [{ type: "scatter", mode: "lines", x: rolling.map((item) => item.time), y: rolling.map((item) => item.pearson), line: { color: "#34bdd6", width: 2 }, hovertemplate: "%{x|%Y-%m-%d}<br>ρ %{y:.3f}<extra></extra>" }], plotLayout("UTC 日期", "90 日 Pearson", { x: null, y: [-1, 1], shapes: [{ type: "line", x0: 0, x1: 1, xref: "paper", y0: 0, y1: 0, line: { color: "#54636d", dash: "dot" } }] }), { displayModeBar: false, responsive: true });
}

function applyFilters() {
  const query = el("search").value.trim().toUpperCase();
  const strongOnly = el("strong-only").checked;
  state.filtered = state.rows.filter((row) => row.statistically_significant && (!strongOnly || row.strong_association) && (!query || row.symbol.includes(query) || String(row.base_asset).includes(query)));
  state.filtered.sort((a, b) => {
    const av = a[state.sort], bv = b[state.sort];
    if (av == null) return 1; if (bv == null) return -1;
    return (typeof av === "string" ? av.localeCompare(bv) : Number(av) - Number(bv)) * state.direction;
  });
  const size = Number(el("page-size").value);
  state.page = Math.min(state.page, Math.max(1, Math.ceil(state.filtered.length / size)));
  renderTable();
}

function renderTableHead() {
  el("table-head").innerHTML = columns.map(([key, label]) => `<th data-key="${key}">${label}${state.sort === key ? state.direction < 0 ? " ↓" : " ↑" : ""}</th>`).join("");
  el("table-head").querySelectorAll("th").forEach((head) => head.addEventListener("click", () => {
    const key = head.dataset.key; state.direction = state.sort === key ? -state.direction : key === "symbol" ? 1 : -1; state.sort = key; applyFilters(); renderTableHead();
  }));
}

function renderTable() {
  renderTableHead();
  const size = Number(el("page-size").value), pages = Math.max(1, Math.ceil(state.filtered.length / size));
  const visible = state.filtered.slice((state.page - 1) * size, state.page * size);
  el("table-body").innerHTML = visible.map((row) => `<tr data-symbol="${escapeHtml(row.symbol)}" class="${row.symbol === state.selected ? "selected" : ""}">${columns.map(([key, , type]) => {
    let value = row[key], display = type === "percent" ? pct(value) : type === "ratio" ? `${number(value)}×` : type === "q" ? qfmt(value) : type === "integer" ? Number(value).toFixed(0) : type === "number" ? number(value) : escapeHtml(value);
    const tag = key === "symbol" && row.strong_association ? `<span class="tag">强</span>` : "";
    return `<td class="${type === "percent" || type === "number" ? signedClass(value) : ""}">${display}${tag}</td>`;
  }).join("")}</tr>`).join("");
  el("table-body").querySelectorAll("tr").forEach((row) => row.addEventListener("click", () => selectSymbol(row.dataset.symbol)));
  el("table-count").textContent = `共 ${state.filtered.length} 个显著对象 · 第 ${(state.page - 1) * size + (visible.length ? 1 : 0)}–${(state.page - 1) * size + visible.length}`;
  el("page-label").textContent = `${state.page} / ${pages}`;
  el("prev-page").disabled = state.page <= 1; el("next-page").disabled = state.page >= pages;
}

async function load() {
  try {
    const [summary, rows] = await Promise.all([api("/api/summary"), api("/api/results")]);
    state.summary = summary; state.rows = rows; renderSummary(); renderScatter(); applyFilters();
    if (!rows.some((row) => row.symbol === state.selected && row.status === "ANALYZED")) state.selected = rows.find((row) => row.status === "ANALYZED")?.symbol || "";
    if (state.selected) await selectSymbol(state.selected);
  } catch (error) {
    el("status").textContent = `页面载入失败：${error.message}`; el("status").className = "status error";
  }
}

el("search").addEventListener("input", () => { state.page = 1; applyFilters(); });
el("strong-only").addEventListener("change", () => { state.page = 1; applyFilters(); });
el("page-size").addEventListener("change", () => { state.page = 1; applyFilters(); });
el("prev-page").addEventListener("click", () => { state.page -= 1; renderTable(); });
el("next-page").addEventListener("click", () => { state.page += 1; renderTable(); });
el("refresh-button").addEventListener("click", async () => { await api("/api/refresh", { method: "POST" }); await load(); });
load();
setInterval(load, 60_000);
