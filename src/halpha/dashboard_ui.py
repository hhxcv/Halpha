from __future__ import annotations


def dashboard_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Halpha Dashboard</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f4ef;
      --panel: #ffffff;
      --panel-soft: #fbfaf7;
      --border: #dedbd2;
      --border-strong: #c6c1b6;
      --text: #202124;
      --muted: #68635a;
      --muted-2: #857f75;
      --teal: #0f766e;
      --teal-soft: #e0f2ef;
      --amber: #a16207;
      --amber-soft: #fff4d6;
      --red: #b42318;
      --red-soft: #fde7e4;
      --blue: #1d4ed8;
      --blue-soft: #e7efff;
      --shadow: 0 1px 2px rgba(32, 33, 36, 0.08);
      font-family:
        Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-size: 14px;
      letter-spacing: 0;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    .app-shell {
      display: grid;
      grid-template-columns: 248px minmax(0, 1fr);
      min-height: 100vh;
    }

    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 22px 18px;
      border-right: 1px solid var(--border);
      background: #24221f;
      color: #f8f4ea;
    }

    .brand {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 36px;
    }

    .brand-name {
      font-size: 18px;
      font-weight: 720;
    }

    .local-pill {
      padding: 4px 8px;
      border: 1px solid rgba(255, 255, 255, 0.22);
      border-radius: 999px;
      color: #d8d2c4;
      font-size: 12px;
    }

    .nav {
      display: grid;
      gap: 6px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 36px;
      padding: 8px 10px;
      border-radius: 6px;
      color: #d8d2c4;
    }

    .nav-item.active {
      background: #f8f4ea;
      color: #24221f;
      box-shadow: var(--shadow);
    }

    .nav-state {
      color: #aaa194;
      font-size: 11px;
    }

    .nav-item.active .nav-state {
      color: var(--teal);
      font-weight: 650;
    }

    .sidebar-footer {
      margin-top: auto;
      padding-top: 16px;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
      color: #bdb5a8;
      font-size: 12px;
      line-height: 1.5;
    }

    .main {
      min-width: 0;
      padding: 22px;
    }

    .topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 18px;
    }

    .eyebrow {
      margin: 0 0 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.15;
      font-weight: 760;
    }

    .status-panel {
      display: grid;
      min-width: 260px;
      gap: 6px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .status-line {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .status-label {
      color: var(--muted);
      font-size: 12px;
    }

    .status-value {
      font-weight: 690;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .card,
    .wide-panel {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .card {
      display: grid;
      min-height: 218px;
      grid-template-rows: auto 1fr auto;
      gap: 12px;
      padding: 14px;
    }

    .card-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }

    .card-title {
      margin: 0;
      font-size: 14px;
      font-weight: 740;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 22px;
      padding: 3px 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--panel-soft);
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }

    .badge::before {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
      content: "";
    }

    .badge.available {
      border-color: #b7ded8;
      background: var(--teal-soft);
      color: var(--teal);
    }

    .badge.warning,
    .badge.partial,
    .badge.missing,
    .badge.skipped,
    .badge.unknown {
      border-color: #f0d38b;
      background: var(--amber-soft);
      color: var(--amber);
    }

    .badge.failed,
    .badge.degraded {
      border-color: #f0b6af;
      background: var(--red-soft);
      color: var(--red);
    }

    .card-body {
      display: grid;
      align-content: start;
      gap: 8px;
    }

    .metric {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      min-height: 22px;
      padding-bottom: 6px;
      border-bottom: 1px solid #eeece5;
    }

    .metric:last-child {
      border-bottom: 0;
    }

    .metric-key {
      color: var(--muted);
      font-size: 12px;
    }

    .metric-value {
      min-width: 0;
      max-width: 58%;
      overflow-wrap: anywhere;
      text-align: right;
      font-weight: 650;
    }

    .message-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .message {
      padding: 8px;
      border-radius: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    .message.warning {
      background: var(--amber-soft);
      color: var(--amber);
    }

    .message.error {
      background: var(--red-soft);
      color: var(--red);
    }

    .layout-row {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(280px, 0.9fr);
      gap: 16px;
    }

    .wide-panel {
      min-height: 260px;
      padding: 16px;
    }

    .panel-heading {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .panel-title {
      margin: 0;
      font-size: 16px;
      font-weight: 740;
    }

    .timeline {
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .timeline-item {
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 10px;
      align-items: start;
    }

    .timeline-dot {
      width: 10px;
      height: 10px;
      margin-top: 4px;
      border-radius: 999px;
      background: var(--teal);
    }

    .timeline-item.partial .timeline-dot,
    .timeline-item.missing .timeline-dot,
    .timeline-item.skipped .timeline-dot,
    .timeline-item.unknown .timeline-dot {
      background: var(--amber);
    }

    .timeline-item.failed .timeline-dot,
    .timeline-item.degraded .timeline-dot {
      background: var(--red);
    }

    .timeline-title {
      font-weight: 680;
    }

    .timeline-meta {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
      overflow-wrap: anywhere;
    }

    .planned-grid {
      display: grid;
      gap: 8px;
    }

    .planned-item {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      min-height: 38px;
      padding: 9px 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
    }

    .planned-title {
      font-weight: 650;
    }

    .planned-state {
      color: var(--muted-2);
      font-size: 12px;
      white-space: nowrap;
    }

    .skeleton {
      position: relative;
      overflow: hidden;
      min-height: 12px;
      border-radius: 4px;
      background: #ebe7dc;
    }

    .skeleton::after {
      position: absolute;
      inset: 0;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent);
      animation: shimmer 1.3s infinite;
      content: "";
    }

    .hidden {
      display: none;
    }

    @keyframes shimmer {
      from {
        transform: translateX(-100%);
      }
      to {
        transform: translateX(100%);
      }
    }

    @media (max-width: 1180px) {
      .grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .layout-row {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 760px) {
      .app-shell {
        grid-template-columns: 1fr;
      }

      .sidebar {
        position: static;
        min-height: auto;
      }

      .nav {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .topbar {
        display: grid;
      }

      .status-panel {
        min-width: 0;
      }

      .grid {
        grid-template-columns: 1fr;
      }

      h1 {
        font-size: 24px;
      }
    }
  </style>
</head>
<body>
  <div id="halpha-dashboard-app" class="app-shell" data-endpoint="/api/overview">
    <aside class="sidebar" aria-label="Dashboard navigation">
      <div class="brand">
        <div class="brand-name">Halpha</div>
        <div class="local-pill">Local</div>
      </div>
      <nav class="nav">
        <a class="nav-item active" href="/">
          <span>Overview</span>
          <span class="nav-state">active</span>
        </a>
        <span class="nav-item">
          <span>Runs &amp; reports</span>
          <span class="nav-state">pending</span>
        </span>
        <span class="nav-item">
          <span>Artifacts</span>
          <span class="nav-state">pending</span>
        </span>
        <span class="nav-item">
          <span>Data stores</span>
          <span class="nav-state">pending</span>
        </span>
        <span class="nav-item">
          <span>Strategy lab</span>
          <span class="nav-state">pending</span>
        </span>
        <span class="nav-item">
          <span>Monitor</span>
          <span class="nav-state">pending</span>
        </span>
        <span class="nav-item">
          <span>Command center</span>
          <span class="nav-state">pending</span>
        </span>
      </nav>
      <div class="sidebar-footer">
        Market output is research material, not financial advice.
      </div>
    </aside>
    <main class="main">
      <section class="topbar" aria-labelledby="overview-title">
        <div>
          <p class="eyebrow">Local research operations</p>
          <h1 id="overview-title">Operational overview</h1>
        </div>
        <div class="status-panel" aria-live="polite">
          <div class="status-line">
            <span class="status-label">Overview</span>
            <span id="overall-status" class="status-value">Loading</span>
          </div>
          <div class="status-line">
            <span class="status-label">Config</span>
            <span id="config-ref" class="status-value">...</span>
          </div>
        </div>
      </section>
      <section id="overview-cards" class="grid" aria-label="Overview sections">
        <article class="card">
          <div class="card-header">
            <h2 class="card-title">Loading dashboard</h2>
            <span class="badge unknown">loading</span>
          </div>
          <div class="card-body">
            <div class="skeleton"></div>
            <div class="skeleton"></div>
            <div class="skeleton"></div>
          </div>
        </article>
      </section>
      <section class="layout-row">
        <article class="wide-panel" aria-labelledby="signals-title">
          <div class="panel-heading">
            <h2 id="signals-title" class="panel-title">Current attention</h2>
            <span id="attention-count" class="badge unknown">loading</span>
          </div>
          <ul id="attention-list" class="timeline"></ul>
        </article>
        <article class="wide-panel" aria-labelledby="planned-title">
          <div class="panel-heading">
            <h2 id="planned-title" class="panel-title">Dashboard areas</h2>
            <span class="badge partial">incremental</span>
          </div>
          <div class="planned-grid">
            <div class="planned-item">
              <span class="planned-title">Runs &amp; reports</span>
              <span class="planned-state">next slice</span>
            </div>
            <div class="planned-item">
              <span class="planned-title">Artifact review</span>
              <span class="planned-state">planned</span>
            </div>
            <div class="planned-item">
              <span class="planned-title">Local data explorer</span>
              <span class="planned-state">planned</span>
            </div>
            <div class="planned-item">
              <span class="planned-title">Strategy lab</span>
              <span class="planned-state">planned</span>
            </div>
            <div class="planned-item">
              <span class="planned-title">Monitor control</span>
              <span class="planned-state">planned</span>
            </div>
            <div class="planned-item">
              <span class="planned-title">Command center</span>
              <span class="planned-state">planned</span>
            </div>
          </div>
        </article>
      </section>
    </main>
  </div>
  <script>
    const app = document.querySelector("#halpha-dashboard-app");
    const endpoint = app.dataset.endpoint;
    const statusLabels = {
      available: "Available",
      warning: "Warning",
      partial: "Partial",
      missing: "Missing",
      skipped: "Skipped",
      degraded: "Degraded",
      failed: "Failed",
      unknown: "Unknown"
    };
    const cards = [
      {
        key: "latest_run",
        title: "Latest run",
        fields: [["run_id", "Run"], ["run_status", "Status"], ["codex_status", "Codex"], ["report.status", "Report"]]
      },
      {
        key: "product_validation",
        title: "Product validation",
        fields: [["artifact_status", "Artifact"], ["counts.checks", "Checks"], ["warning_count", "Warnings"], ["error_count", "Errors"]]
      },
      {
        key: "data_quality",
        title: "Data quality",
        fields: [["artifact_status", "Artifact"], ["counts.checks", "Checks"], ["warning_count", "Warnings"], ["error_count", "Errors"]]
      },
      {
        key: "monitor",
        title: "Monitor",
        fields: [["cycle_count", "Cycles"], ["latest_cycle_status", "Latest"], ["alert_counts.emitted", "Alerts"], ["error_count", "Errors"]]
      },
      {
        key: "workbench",
        title: "Workbench",
        fields: [["artifact_status", "Status"], ["generated_at", "Generated"], ["latest_run.run_id", "Run"], ["errors", "Errors"]]
      }
    ];

    function text(value) {
      if (value === null || value === undefined || value === "") {
        return "n/a";
      }
      if (typeof value === "object") {
        return JSON.stringify(value);
      }
      return String(value);
    }

    function get(path, source) {
      return path.split(".").reduce((value, key) => {
        if (value === null || value === undefined || typeof value !== "object") {
          return undefined;
        }
        return value[key];
      }, source);
    }

    function label(status) {
      return statusLabels[status] || statusLabels.unknown;
    }

    function badge(status) {
      const normalized = status || "unknown";
      return `<span class="badge ${normalized}">${label(normalized)}</span>`;
    }

    function metric(labelText, value) {
      return `<div class="metric"><span class="metric-key">${labelText}</span><span class="metric-value">${escapeHtml(text(value))}</span></div>`;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function messages(section) {
      const warnings = Array.isArray(section.warnings) ? section.warnings : [];
      const errors = Array.isArray(section.errors) ? section.errors : [];
      const rows = [
        ...warnings.slice(0, 2).map((value) => `<li class="message warning">${escapeHtml(value)}</li>`),
        ...errors.slice(0, 2).map((value) => `<li class="message error">${escapeHtml(value)}</li>`)
      ];
      return rows.length ? `<ul class="message-list">${rows.join("")}</ul>` : "";
    }

    function renderCards(sections) {
      const html = cards.map((card) => {
        const section = sections[card.key] || { status: "missing", fields: {}, warnings: ["section is not available."], errors: [] };
        const fields = section.fields || {};
        const metrics = card.fields.map(([field, labelText]) => metric(labelText, get(field, fields))).join("");
        return `
          <article class="card">
            <div class="card-header">
              <h2 class="card-title">${card.title}</h2>
              ${badge(section.status)}
            </div>
            <div class="card-body">${metrics}</div>
            ${messages(section)}
          </article>`;
      });
      document.querySelector("#overview-cards").innerHTML = html.join("");
    }

    function renderAttention(sections) {
      const items = Object.values(sections).flatMap((section) => {
        const status = section.status || "unknown";
        const warnings = Array.isArray(section.warnings) ? section.warnings : [];
        const errors = Array.isArray(section.errors) ? section.errors : [];
        if (!warnings.length && !errors.length && status === "available") {
          return [];
        }
        const primary = errors[0] || warnings[0] || `${section.name || "section"} status is ${status}.`;
        const source = Array.isArray(section.source_artifacts) ? section.source_artifacts[0] : "";
        return [{
          status,
          title: section.name || "section",
          primary,
          source
        }];
      });
      const count = document.querySelector("#attention-count");
      count.className = `badge ${items.length ? "partial" : "available"}`;
      count.textContent = items.length ? `${items.length} item${items.length === 1 ? "" : "s"}` : "clear";
      document.querySelector("#attention-list").innerHTML = items.length
        ? items.map((item) => `
            <li class="timeline-item ${item.status}">
              <span class="timeline-dot"></span>
              <span>
                <span class="timeline-title">${escapeHtml(item.title)}</span>
                <span class="timeline-meta">${escapeHtml(item.primary)}${item.source ? ` Source: ${escapeHtml(item.source)}` : ""}</span>
              </span>
            </li>`).join("")
        : `<li class="timeline-item available">
            <span class="timeline-dot"></span>
            <span>
              <span class="timeline-title">No current attention items</span>
              <span class="timeline-meta">All overview sections are available with no emitted warnings.</span>
            </span>
          </li>`;
    }

    function render(payload) {
      const sections = payload.sections || {};
      const overall = payload.status || "unknown";
      document.querySelector("#overall-status").textContent = label(overall);
      document.querySelector("#config-ref").textContent = text(payload.config && payload.config.ref);
      renderCards(sections);
      renderAttention(sections);
    }

    function renderFailure(error) {
      document.querySelector("#overall-status").textContent = "Failed";
      document.querySelector("#overview-cards").innerHTML = `
        <article class="card">
          <div class="card-header">
            <h2 class="card-title">Dashboard API</h2>
            ${badge("failed")}
          </div>
          <div class="card-body">
            ${metric("Endpoint", endpoint)}
          </div>
          <ul class="message-list"><li class="message error">${escapeHtml(error.message || "overview request failed.")}</li></ul>
        </article>`;
      document.querySelector("#attention-count").className = "badge failed";
      document.querySelector("#attention-count").textContent = "failed";
      document.querySelector("#attention-list").innerHTML = `
        <li class="timeline-item failed">
          <span class="timeline-dot"></span>
          <span>
            <span class="timeline-title">Overview API failed</span>
            <span class="timeline-meta">${escapeHtml(error.message || "Request failed.")}</span>
          </span>
        </li>`;
    }

    fetch(endpoint, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then(render)
      .catch(renderFailure);
  </script>
</body>
</html>
"""
