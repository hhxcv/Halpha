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

    button {
      font: inherit;
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

    .view {
      display: block;
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
      overflow-wrap: anywhere;
      text-align: right;
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

    .card-header,
    .panel-heading {
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
    .badge.not_run,
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
      overflow-wrap: anywhere;
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
    .timeline-item.not_run .timeline-dot,
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

    .runs-layout,
    .data-layout {
      display: grid;
      grid-template-columns: minmax(300px, 0.38fr) minmax(0, 1fr);
      gap: 16px;
    }

    .run-list {
      display: grid;
      gap: 8px;
      max-height: 68vh;
      overflow: auto;
      padding-right: 2px;
    }

    .run-row,
    .artifact-button,
    .link-button {
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--text);
      cursor: pointer;
      text-align: left;
    }

    .run-row {
      display: grid;
      gap: 6px;
      width: 100%;
      min-height: 76px;
      padding: 10px;
    }

    .run-row:hover,
    .run-row.selected,
    .artifact-button:hover,
    .link-button:hover {
      border-color: var(--border-strong);
      background: #f1eee7;
    }

    .run-row.selected {
      box-shadow: inset 3px 0 0 var(--teal);
    }

    .run-row-main,
    .artifact-row-main {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .run-id {
      min-width: 0;
      overflow-wrap: anywhere;
      font-weight: 720;
    }

    .run-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .run-detail-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }

    .detail-tile {
      min-height: 72px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
    }

    .detail-label {
      color: var(--muted);
      font-size: 12px;
    }

    .detail-value {
      margin-top: 5px;
      overflow-wrap: anywhere;
      font-weight: 710;
    }

    .detail-sections {
      display: grid;
      gap: 14px;
    }

    .section-block {
      display: grid;
      gap: 10px;
      padding-top: 12px;
      border-top: 1px solid var(--border);
    }

    .subheading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin: 0;
      font-size: 14px;
      font-weight: 740;
    }

    .stage-list,
    .artifact-list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .stage-item {
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
    }

    .stage-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }

    .stage-name {
      min-width: 0;
      overflow-wrap: anywhere;
      font-weight: 700;
    }

    .artifact-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .filter-bar {
      display: grid;
      grid-template-columns: minmax(160px, 0.34fr) minmax(0, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }

    .filter-control {
      min-height: 36px;
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--text);
      padding: 7px 9px;
      font: inherit;
    }

    .store-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .store-card {
      display: grid;
      gap: 8px;
      min-height: 122px;
      padding: 11px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-soft);
      color: var(--text);
      cursor: pointer;
      text-align: left;
    }

    .store-card:hover,
    .store-card.selected {
      border-color: var(--border-strong);
      background: #f1eee7;
    }

    .store-card.selected {
      box-shadow: inset 3px 0 0 var(--teal);
    }

    .store-title-line {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }

    .store-title {
      min-width: 0;
      overflow-wrap: anywhere;
      font-weight: 740;
    }

    .store-metrics {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      color: var(--muted);
      font-size: 12px;
    }

    .source-ref-list {
      display: grid;
      gap: 6px;
      margin: 0;
      padding: 0;
      list-style: none;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .artifact-button,
    .link-button {
      min-height: 30px;
      padding: 5px 8px;
      color: var(--blue);
      font-size: 12px;
      font-weight: 650;
    }

    .preview-panel {
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-soft);
    }

    .preview-heading {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }

    .preview-path {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .preview-body {
      max-height: 520px;
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #ffffff;
    }

    .markdown-reader {
      display: grid;
      gap: 8px;
      line-height: 1.55;
    }

    .markdown-reader h2,
    .markdown-reader h3,
    .markdown-reader h4,
    .markdown-reader p,
    .markdown-reader ul,
    .markdown-reader pre {
      margin: 0;
    }

    .markdown-reader h2 {
      font-size: 20px;
    }

    .markdown-reader h3 {
      font-size: 16px;
    }

    .markdown-reader h4 {
      font-size: 14px;
    }

    .markdown-reader ul {
      padding-left: 18px;
    }

    .preview-pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.45;
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

      .layout-row,
      .runs-layout,
      .data-layout {
        grid-template-columns: 1fr;
      }

      .run-detail-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
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

      .grid,
      .run-detail-grid,
      .store-grid,
      .filter-bar {
        grid-template-columns: 1fr;
      }

      h1 {
        font-size: 24px;
      }
    }
  </style>
</head>
<body>
  <div
    id="halpha-dashboard-app"
    class="app-shell"
    data-overview-endpoint="/api/overview"
    data-runs-endpoint="/api/runs"
    data-stores-endpoint="/api/data/stores"
    data-preview-endpoint="/api/artifacts/preview"
  >
    <aside class="sidebar" aria-label="Dashboard navigation">
      <div class="brand">
        <div class="brand-name">Halpha</div>
        <div class="local-pill">Local</div>
      </div>
      <nav class="nav">
        <a class="nav-item active" href="#overview" data-view-target="overview" aria-current="page">
          <span>Overview</span>
          <span class="nav-state">active</span>
        </a>
        <a class="nav-item" href="#runs" data-view-target="runs">
          <span>Runs &amp; reports</span>
          <span class="nav-state">available</span>
        </a>
        <span class="nav-item">
          <span>Artifacts</span>
          <span class="nav-state">pending</span>
        </span>
        <a class="nav-item" href="#data" data-view-target="data">
          <span>Data stores</span>
          <span class="nav-state">available</span>
        </a>
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
      <section id="overview-view" class="view" data-view="overview">
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
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Artifact review</span>
                <span class="planned-state">planned</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Local data explorer</span>
                <span class="planned-state">available</span>
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
      </section>

      <section id="runs-view" class="view hidden" data-view="runs">
        <section class="topbar" aria-labelledby="runs-title">
          <div>
            <p class="eyebrow">Run history and reports</p>
            <h1 id="runs-title">Runs &amp; reports</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Run index</span>
              <span id="runs-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="selected-run-status" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="runs-layout">
          <article class="wide-panel" aria-labelledby="run-list-title">
            <div class="panel-heading">
              <h2 id="run-list-title" class="panel-title">Run history</h2>
              <span id="run-count" class="badge unknown">loading</span>
            </div>
            <div id="run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="run-detail-title">
            <div class="panel-heading">
              <h2 id="run-detail-title" class="panel-title">Run detail</h2>
              <span id="run-detail-badge" class="badge unknown">waiting</span>
            </div>
            <div id="run-detail-summary" class="run-detail-grid"></div>
            <div class="detail-sections">
              <section class="section-block">
                <h3 class="subheading">
                  <span>Report preview</span>
                  <span id="report-status" class="badge unknown">waiting</span>
                </h3>
                <div id="report-preview" class="preview-panel">
                  <div class="message">Select a run to preview its report.</div>
                </div>
              </section>
              <section class="section-block">
                <h3 class="subheading">
                  <span>Stage timeline</span>
                  <span id="stage-count" class="badge unknown">waiting</span>
                </h3>
                <ul id="stage-list" class="stage-list"></ul>
              </section>
              <section class="section-block">
                <h3 class="subheading">
                  <span>Artifact refs</span>
                  <span id="artifact-count" class="badge unknown">waiting</span>
                </h3>
                <ul id="artifact-list" class="artifact-list"></ul>
                <div id="artifact-preview" class="preview-panel">
                  <div class="message">Open a report, stage artifact, or run artifact to inspect a bounded preview.</div>
                </div>
              </section>
            </div>
          </article>
        </section>
      </section>

      <section id="data-view" class="view hidden" data-view="data">
        <section class="topbar" aria-labelledby="data-title">
          <div>
            <p class="eyebrow">Local research data</p>
            <h1 id="data-title">Data stores</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Stores</span>
              <span id="data-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Visible</span>
              <span id="data-visible-count" class="status-value">...</span>
            </div>
          </div>
        </section>
        <section class="data-layout">
          <article class="wide-panel" aria-labelledby="data-store-list-title">
            <div class="panel-heading">
              <h2 id="data-store-list-title" class="panel-title">Store coverage</h2>
              <span id="data-store-count" class="badge unknown">loading</span>
            </div>
            <div class="filter-bar">
              <select id="data-group-filter" class="filter-control" aria-label="Store group filter">
                <option value="all">All groups</option>
                <option value="system">System</option>
                <option value="market">Market</option>
                <option value="derivatives">Derivatives</option>
                <option value="macro">Macro/calendar</option>
                <option value="onchain">On-chain</option>
                <option value="text">Text</option>
                <option value="outcome">Outcome</option>
              </select>
              <input id="data-search-filter" class="filter-control" type="search" placeholder="Filter by source, symbol, timeframe, data class, asset, chain, or store">
            </div>
            <div id="data-store-list" class="store-grid">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="data-store-detail-title">
            <div class="panel-heading">
              <h2 id="data-store-detail-title" class="panel-title">Store detail</h2>
              <span id="data-store-detail-badge" class="badge unknown">waiting</span>
            </div>
            <div id="data-store-detail" class="detail-sections">
              <div class="message">Select a store to inspect its metadata summary.</div>
            </div>
            <div id="data-preview" class="preview-panel">
              <div class="message">Open a metadata preview to inspect bounded JSON or text output.</div>
            </div>
          </article>
        </section>
      </section>
    </main>
  </div>
  <script>
    const app = document.querySelector("#halpha-dashboard-app");
    const endpoints = {
      overview: app.dataset.overviewEndpoint,
      runs: app.dataset.runsEndpoint,
      stores: app.dataset.storesEndpoint,
      preview: app.dataset.previewEndpoint
    };
    const statusLabels = {
      available: "Available",
      succeeded: "Succeeded",
      success: "Succeeded",
      ok: "OK",
      warning: "Warning",
      partial: "Partial",
      missing: "Missing",
      skipped: "Skipped",
      disabled: "Disabled",
      not_run: "Not run",
      degraded: "Degraded",
      failed: "Failed",
      unknown: "Unknown"
    };
    const overviewCards = [
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
    let runsLoaded = false;
    let selectedRunId = null;
    let dataStoresLoaded = false;
    let dataStoresPayload = null;
    let selectedStoreName = null;

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

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function normalizeStatus(status) {
      const value = String(status || "unknown").toLowerCase();
      if (["ok", "success", "succeeded"].includes(value)) {
        return "available";
      }
      if (["not_run", "disabled", "skipped"].includes(value)) {
        return value;
      }
      if (["available", "warning", "partial", "missing", "degraded", "failed"].includes(value)) {
        return value;
      }
      return "unknown";
    }

    function label(status) {
      return statusLabels[status] || statusLabels[normalizeStatus(status)] || statusLabels.unknown;
    }

    function badge(status) {
      const normalized = normalizeStatus(status);
      return `<span class="badge ${normalized}">${label(status)}</span>`;
    }

    function metric(labelText, value) {
      return `<div class="metric"><span class="metric-key">${labelText}</span><span class="metric-value">${escapeHtml(text(value))}</span></div>`;
    }

    function messages(section) {
      const warnings = Array.isArray(section.warnings) ? section.warnings : [];
      const errors = Array.isArray(section.errors) ? section.errors : [];
      const rows = [
        ...warnings.slice(0, 3).map((value) => `<li class="message warning">${escapeHtml(value)}</li>`),
        ...errors.slice(0, 3).map((value) => `<li class="message error">${escapeHtml(value)}</li>`)
      ];
      return rows.length ? `<ul class="message-list">${rows.join("")}</ul>` : "";
    }

    async function fetchJson(url) {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    }

    function viewFromHash() {
      if (window.location.hash === "#runs") {
        return "runs";
      }
      if (window.location.hash === "#data") {
        return "data";
      }
      return "overview";
    }

    function setView(view) {
      document.querySelectorAll("[data-view]").forEach((node) => {
        node.classList.toggle("hidden", node.dataset.view !== view);
      });
      document.querySelectorAll("[data-view-target]").forEach((node) => {
        const active = node.dataset.viewTarget === view;
        node.classList.toggle("active", active);
        node.toggleAttribute("aria-current", active);
        const state = node.querySelector(".nav-state");
        if (state) {
          state.textContent = active ? "active" : "available";
        }
      });
      if (view === "runs" && !runsLoaded) {
        loadRuns();
      }
      if (view === "data" && !dataStoresLoaded) {
        loadDataStores();
      }
    }

    function renderOverviewCards(sections) {
      const html = overviewCards.map((card) => {
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
        return [{ status, title: section.name || "section", primary, source }];
      });
      const count = document.querySelector("#attention-count");
      count.className = `badge ${items.length ? "partial" : "available"}`;
      count.textContent = items.length ? `${items.length} item${items.length === 1 ? "" : "s"}` : "clear";
      document.querySelector("#attention-list").innerHTML = items.length
        ? items.map((item) => `
            <li class="timeline-item ${normalizeStatus(item.status)}">
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

    function renderOverview(payload) {
      const sections = payload.sections || {};
      const overall = payload.status || "unknown";
      document.querySelector("#overall-status").textContent = label(overall);
      document.querySelector("#config-ref").textContent = text(payload.config && payload.config.ref);
      renderOverviewCards(sections);
      renderAttention(sections);
    }

    function renderOverviewFailure(error) {
      document.querySelector("#overall-status").textContent = "Failed";
      document.querySelector("#overview-cards").innerHTML = `
        <article class="card">
          <div class="card-header">
            <h2 class="card-title">Dashboard API</h2>
            ${badge("failed")}
          </div>
          <div class="card-body">
            ${metric("Endpoint", endpoints.overview)}
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

    async function loadRuns() {
      runsLoaded = true;
      document.querySelector("#runs-status").textContent = "Loading";
      try {
        const payload = await fetchJson(endpoints.runs);
        renderRunList(payload);
        const runs = Array.isArray(payload.runs) ? payload.runs : [];
        if (runs.length) {
          selectRun(runs[0].run_id);
        } else {
          renderRunDetailEmpty(payload);
        }
      } catch (error) {
        renderRunListFailure(error);
      }
    }

    function renderRunList(payload) {
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      document.querySelector("#runs-status").textContent = label(payload.status);
      const count = document.querySelector("#run-count");
      count.className = `badge ${runs.length ? "available" : normalizeStatus(payload.status)}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      const list = document.querySelector("#run-list");
      if (!runs.length) {
        list.innerHTML = `
          <div class="message warning">${escapeHtml((payload.warnings && payload.warnings[0]) || "No runs are recorded in the local run index.")}</div>
          ${messages(payload)}`;
        return;
      }
      list.innerHTML = runs.map((run) => `
        <button class="run-row" type="button" data-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Codex: ${escapeHtml(text(run.codex_status))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      list.querySelectorAll("[data-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectRun(button.dataset.runId));
      });
    }

    function renderRunListFailure(error) {
      document.querySelector("#runs-status").textContent = "Failed";
      document.querySelector("#run-count").className = "badge failed";
      document.querySelector("#run-count").textContent = "failed";
      document.querySelector("#run-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      renderRunDetailEmpty({ warnings: [], errors: [error.message] });
    }

    async function selectRun(runId) {
      if (!runId) {
        return;
      }
      selectedRunId = runId;
      document.querySelector("#selected-run-status").textContent = runId;
      document.querySelectorAll("[data-run-id]").forEach((button) => {
        button.classList.toggle("selected", button.dataset.runId === runId);
      });
      document.querySelector("#run-detail-badge").className = "badge unknown";
      document.querySelector("#run-detail-badge").textContent = "loading";
      document.querySelector("#run-detail-summary").innerHTML = "";
      document.querySelector("#stage-list").innerHTML = "";
      document.querySelector("#artifact-list").innerHTML = "";
      document.querySelector("#report-preview").innerHTML = `<div class="message">Loading report reference.</div>`;
      try {
        const detail = await fetchJson(`${endpoints.runs}/${encodeURIComponent(runId)}`);
        renderRunDetail(detail);
        await loadReportPreview(detail);
      } catch (error) {
        renderRunDetailFailure(runId, error);
      }
    }

    function renderRunDetailEmpty(payload) {
      document.querySelector("#selected-run-status").textContent = "none";
      document.querySelector("#run-detail-badge").className = `badge ${normalizeStatus(payload.status)}`;
      document.querySelector("#run-detail-badge").textContent = label(payload.status || "missing");
      document.querySelector("#run-detail-summary").innerHTML = "";
      document.querySelector("#stage-count").className = "badge missing";
      document.querySelector("#stage-count").textContent = "0 stages";
      document.querySelector("#artifact-count").className = "badge missing";
      document.querySelector("#artifact-count").textContent = "0 refs";
      document.querySelector("#stage-list").innerHTML = messages(payload) || `<li class="message warning">Run detail is not available.</li>`;
      document.querySelector("#artifact-list").innerHTML = "";
      document.querySelector("#report-status").className = "badge missing";
      document.querySelector("#report-status").textContent = "missing";
      document.querySelector("#report-preview").innerHTML = `<div class="message warning">No report preview is available.</div>`;
    }

    function renderRunDetailFailure(runId, error) {
      renderRunDetailEmpty({ status: "failed", errors: [`${runId}: ${error.message}`], warnings: [] });
      document.querySelector("#selected-run-status").textContent = runId;
    }

    function renderRunDetail(detail) {
      const fields = detail.fields || {};
      document.querySelector("#run-detail-title").textContent = fields.run_id || detail.run_id || "Run detail";
      document.querySelector("#run-detail-badge").className = `badge ${normalizeStatus(detail.status)}`;
      document.querySelector("#run-detail-badge").textContent = label(detail.status);
      document.querySelector("#selected-run-status").textContent = fields.run_id || detail.run_id || selectedRunId;
      document.querySelector("#run-detail-summary").innerHTML = [
        detailTile("Run status", fields.status || fields.manifest_status),
        detailTile("Codex", get("codex.status", fields) || fields.codex_status),
        detailTile("Started", fields.started_at),
        detailTile("Finished", fields.finished_at),
        detailTile("Warnings", fields.warning_count),
        detailTile("Errors", fields.error_count),
        detailTile("Run dir", fields.run_dir),
        detailTile("Manifest", fields.manifest)
      ].join("");
      renderStageList(detail);
      renderArtifactList(detail);
    }

    function detailTile(labelText, value) {
      return `
        <div class="detail-tile">
          <div class="detail-label">${escapeHtml(labelText)}</div>
          <div class="detail-value">${escapeHtml(text(value))}</div>
        </div>`;
    }

    function renderStageList(detail) {
      const fields = detail.fields || {};
      const stages = Array.isArray(detail.stages) ? detail.stages : [];
      const count = document.querySelector("#stage-count");
      count.className = `badge ${stages.length ? "available" : "missing"}`;
      count.textContent = `${stages.length} stage${stages.length === 1 ? "" : "s"}`;
      if (!stages.length) {
        document.querySelector("#stage-list").innerHTML = `<li class="message warning">No stage timeline is available for this run.</li>`;
        return;
      }
      document.querySelector("#stage-list").innerHTML = stages.map((stage) => {
        const artifacts = Array.isArray(stage.artifacts) ? stage.artifacts : [];
        return `
          <li class="stage-item">
            <div class="stage-top">
              <span class="stage-name">${escapeHtml(text(stage.name))}</span>
              ${badge(stage.status)}
            </div>
            <div class="run-meta">
              <span>Started: ${escapeHtml(text(stage.started_at))}</span>
              <span>Finished: ${escapeHtml(text(stage.finished_at))}</span>
              <span>Artifacts: ${escapeHtml(text(stage.artifact_count))}</span>
              <span>Warnings: ${escapeHtml(text(stage.warning_count))}</span>
              <span>Errors: ${escapeHtml(text(stage.error_count))}</span>
              ${stage.reason ? `<span>Reason: ${escapeHtml(stage.reason)}</span>` : ""}
            </div>
            ${artifacts.length ? artifactButtons(artifacts, fields.run_dir) : ""}
            ${stage.artifact_omitted_count ? `<div class="message warning">${escapeHtml(stage.artifact_omitted_count)} stage artifact ref(s) omitted.</div>` : ""}
          </li>`;
      }).join("");
      wireArtifactButtons();
    }

    function renderArtifactList(detail) {
      const fields = detail.fields || {};
      const artifacts = Array.isArray(detail.artifacts) ? detail.artifacts : [];
      const count = document.querySelector("#artifact-count");
      count.className = `badge ${artifacts.length ? "available" : "missing"}`;
      count.textContent = `${artifacts.length} ref${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#artifact-list").innerHTML = `<li class="message warning">No artifact refs are recorded in this manifest.</li>`;
        return;
      }
      document.querySelector("#artifact-list").innerHTML = artifacts.map((artifact) => `
        <li>
          <button class="artifact-button" type="button" data-artifact-path="${escapeHtml(previewPath(fields.run_dir, artifact.path))}">
            <span class="artifact-row-main">
              <span>${escapeHtml(artifact.key || artifact.kind || "artifact")}</span>
              <span>${escapeHtml(artifact.path)}</span>
            </span>
          </button>
        </li>`).join("");
      wireArtifactButtons();
    }

    function artifactButtons(artifacts, runDir) {
      return `
        <div class="artifact-actions">
          ${artifacts.map((artifact) => `
            <button class="artifact-button" type="button" data-artifact-path="${escapeHtml(previewPath(runDir, artifact.path))}">
              ${escapeHtml(artifact.path)}
            </button>`).join("")}
        </div>`;
    }

    function wireArtifactButtons() {
      document.querySelectorAll("[data-artifact-path]").forEach((button) => {
        button.addEventListener("click", () => {
          loadArtifactPreview(button.dataset.artifactPath, button.dataset.previewTarget || "#artifact-preview");
        });
      });
    }

    async function loadDataStores() {
      dataStoresLoaded = true;
      document.querySelector("#data-status").textContent = "Loading";
      try {
        dataStoresPayload = await fetchJson(endpoints.stores);
        renderDataStores();
      } catch (error) {
        renderDataStoresFailure(error);
      }
    }

    function renderDataStoresFailure(error) {
      document.querySelector("#data-status").textContent = "Failed";
      document.querySelector("#data-store-count").className = "badge failed";
      document.querySelector("#data-store-count").textContent = "failed";
      document.querySelector("#data-visible-count").textContent = "0";
      document.querySelector("#data-store-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#data-store-detail-badge").className = "badge failed";
      document.querySelector("#data-store-detail-badge").textContent = "failed";
      document.querySelector("#data-store-detail").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
    }

    function renderDataStores() {
      const payload = dataStoresPayload || { status: "unknown", stores: [] };
      const stores = Array.isArray(payload.stores) ? payload.stores : [];
      const visible = stores.filter(storeMatchesFilters);
      document.querySelector("#data-status").textContent = label(payload.status);
      document.querySelector("#data-visible-count").textContent = `${visible.length}`;
      const count = document.querySelector("#data-store-count");
      count.className = `badge ${stores.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${stores.length} store${stores.length === 1 ? "" : "s"}`;
      if (!visible.length) {
        document.querySelector("#data-store-list").innerHTML = `<div class="message warning">No stores match the current filter.</div>`;
        renderDataStoreDetail(null);
        return;
      }
      if (!visible.some((store) => store.name === selectedStoreName)) {
        selectedStoreName = visible[0].name;
      }
      document.querySelector("#data-store-list").innerHTML = visible.map((store) => `
        <button class="store-card ${store.name === selectedStoreName ? "selected" : ""}" type="button" data-store-name="${escapeHtml(store.name)}">
          <span class="store-title-line">
            <span class="store-title">${escapeHtml(store.title || store.name)}</span>
            ${badge(store.status)}
          </span>
          <span class="store-metrics">
            <span>Group: ${escapeHtml(storeGroup(store))}</span>
            ${store.fields && store.fields.records !== undefined ? `<span>Records: ${escapeHtml(text(store.fields.records))}</span>` : ""}
            ${store.fields && store.fields.updated_at ? `<span>Updated: ${escapeHtml(text(store.fields.updated_at))}</span>` : ""}
            ${store.fields && store.fields.schema_version !== undefined ? `<span>Schema: ${escapeHtml(text(store.fields.schema_version))}</span>` : ""}
          </span>
          <span class="timeline-meta">${escapeHtml(store.artifact || "metadata not recorded")}</span>
        </button>`).join("");
      document.querySelectorAll("[data-store-name]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedStoreName = button.dataset.storeName;
          renderDataStores();
        });
      });
      renderDataStoreDetail(visible.find((store) => store.name === selectedStoreName) || visible[0]);
    }

    function storeMatchesFilters(store) {
      const group = document.querySelector("#data-group-filter").value;
      const query = document.querySelector("#data-search-filter").value.trim().toLowerCase();
      if (group !== "all" && storeGroup(store) !== group) {
        return false;
      }
      if (!query) {
        return true;
      }
      return dataStoreSearchText(store).includes(query);
    }

    function dataStoreSearchText(store) {
      return [
        store.name,
        store.title,
        store.status,
        store.artifact,
        store.preview_path,
        JSON.stringify(store.fields || {}),
        JSON.stringify(store.extra || {}),
        (store.source_artifacts || []).join(" ")
      ].join(" ").toLowerCase();
    }

    function storeGroup(store) {
      const name = String(store && store.name || "");
      if (name.includes("ohlcv")) {
        return "market";
      }
      if (name.includes("derivatives")) {
        return "derivatives";
      }
      if (name.includes("macro")) {
        return "macro";
      }
      if (name.includes("onchain")) {
        return "onchain";
      }
      if (name.includes("text")) {
        return "text";
      }
      if (name.includes("outcome")) {
        return "outcome";
      }
      return "system";
    }

    function renderDataStoreDetail(store) {
      if (!store) {
        document.querySelector("#data-store-detail-badge").className = "badge missing";
        document.querySelector("#data-store-detail-badge").textContent = "missing";
        document.querySelector("#data-store-detail").innerHTML = `<div class="message warning">No store is selected.</div>`;
        return;
      }
      document.querySelector("#data-store-detail-title").textContent = store.title || store.name;
      document.querySelector("#data-store-detail-badge").className = `badge ${normalizeStatus(store.status)}`;
      document.querySelector("#data-store-detail-badge").textContent = label(store.status);
      const fields = store.fields || {};
      const refs = Array.isArray(store.source_artifacts) ? store.source_artifacts : [];
      document.querySelector("#data-store-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>Coverage summary</span>
            <span class="badge ${normalizeStatus(store.status)}">${label(store.status)}</span>
          </h3>
          <div class="run-detail-grid">
            ${Object.entries(fields).slice(0, 12).map(([key, value]) => detailTile(key, value)).join("") || detailTile("status", store.status)}
          </div>
          ${messages(store)}
        </section>
        <section class="section-block">
          <h3 class="subheading">
            <span>Source refs</span>
            <span class="badge ${refs.length ? "available" : "missing"}">${refs.length} ref${refs.length === 1 ? "" : "s"}</span>
          </h3>
          <ul class="source-ref-list">
            ${refs.length ? refs.slice(0, 8).map((ref) => `<li>${escapeHtml(ref)}</li>`).join("") : `<li>No source refs recorded.</li>`}
          </ul>
        </section>
        <section class="section-block">
          <h3 class="subheading">
            <span>Metadata preview</span>
            ${store.preview_path ? `<button class="link-button" type="button" data-artifact-path="${escapeHtml(store.preview_path)}" data-preview-target="#data-preview">Open preview</button>` : `<span class="badge missing">not available</span>`}
          </h3>
          <div class="message ${store.preview_path ? "" : "warning"}">${escapeHtml(store.preview_path || "This store does not expose a bounded metadata preview path.")}</div>
        </section>`;
      wireArtifactButtons();
      if (store.preview_path) {
        loadArtifactPreview(store.preview_path, "#data-preview");
      } else {
        document.querySelector("#data-preview").innerHTML = `<div class="message warning">No bounded metadata preview is available for this store.</div>`;
      }
    }

    async function loadReportPreview(detail) {
      const path = reportPreviewPath(detail);
      if (!path) {
        document.querySelector("#report-status").className = "badge missing";
        document.querySelector("#report-status").textContent = "missing";
        document.querySelector("#report-preview").innerHTML = `<div class="message warning">Report artifact is not recorded for this run.</div>`;
        return;
      }
      document.querySelector("#report-preview").innerHTML = `
        <div class="preview-heading">
          <div class="preview-path">${escapeHtml(path)}</div>
          <button class="link-button" type="button" data-artifact-path="${escapeHtml(path)}">Open artifact preview</button>
        </div>
        <div class="message">Loading report preview.</div>`;
      wireArtifactButtons();
      await loadArtifactPreview(path, "#report-preview", { report: true });
    }

    function reportPreviewPath(detail) {
      const fields = detail.fields || {};
      if (!fields.run_dir || !fields.report) {
        return "";
      }
      return previewPath(fields.run_dir, fields.report);
    }

    async function loadArtifactPreview(path, targetSelector, options = {}) {
      const target = document.querySelector(targetSelector);
      if (!path) {
        target.innerHTML = `<div class="message warning">Artifact path is not available.</div>`;
        return;
      }
      target.innerHTML = `<div class="message">Loading ${escapeHtml(path)}.</div>`;
      try {
        const url = `${endpoints.preview}?path=${encodeURIComponent(path)}`;
        const payload = await fetchJson(url);
        renderArtifactPreview(payload, target, options);
      } catch (error) {
        target.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    function renderArtifactPreview(payload, target, options) {
      const status = payload.status || "unknown";
      const preview = payload.preview;
      if (options.report) {
        document.querySelector("#report-status").className = `badge ${normalizeStatus(status)}`;
        document.querySelector("#report-status").textContent = label(status);
      }
      const body = payload.kind === "markdown"
        ? `<div class="markdown-reader">${markdownToHtml(text(preview))}</div>`
        : `<pre class="preview-pre">${escapeHtml(formatPreview(preview))}</pre>`;
      target.innerHTML = `
        <div class="preview-heading">
          <div>
            <div class="preview-path">${escapeHtml(payload.path || "")}</div>
            ${payload.truncated ? `<div class="message warning">Preview is truncated.</div>` : ""}
          </div>
          ${badge(status)}
        </div>
        ${messages(payload)}
        <div class="preview-body">${body}</div>`;
    }

    function formatPreview(value) {
      if (typeof value === "string") {
        return value;
      }
      return JSON.stringify(value, null, 2);
    }

    function markdownToHtml(markdown) {
      const lines = markdown.split(/\\r?\\n/);
      const html = [];
      let inList = false;
      let inCode = false;
      let codeLines = [];
      const closeList = () => {
        if (inList) {
          html.push("</ul>");
          inList = false;
        }
      };
      const closeCode = () => {
        if (inCode) {
          html.push(`<pre class="preview-pre">${escapeHtml(codeLines.join("\\n"))}</pre>`);
          codeLines = [];
          inCode = false;
        }
      };
      lines.forEach((raw) => {
        if (raw.startsWith("```")) {
          if (inCode) {
            closeCode();
          } else {
            closeList();
            inCode = true;
            codeLines = [];
          }
          return;
        }
        if (inCode) {
          codeLines.push(raw);
          return;
        }
        if (!raw.trim()) {
          closeList();
          return;
        }
        if (raw.startsWith("### ")) {
          closeList();
          html.push(`<h4>${escapeHtml(raw.slice(4))}</h4>`);
          return;
        }
        if (raw.startsWith("## ")) {
          closeList();
          html.push(`<h3>${escapeHtml(raw.slice(3))}</h3>`);
          return;
        }
        if (raw.startsWith("# ")) {
          closeList();
          html.push(`<h2>${escapeHtml(raw.slice(2))}</h2>`);
          return;
        }
        if (raw.startsWith("- ")) {
          if (!inList) {
            html.push("<ul>");
            inList = true;
          }
          html.push(`<li>${escapeHtml(raw.slice(2))}</li>`);
          return;
        }
        closeList();
        html.push(`<p>${escapeHtml(raw)}</p>`);
      });
      closeList();
      closeCode();
      return html.join("");
    }

    function joinPath(base, path) {
      const left = String(base || "").replace(/\\/$/, "");
      const right = String(path || "").replace(/^\\//, "");
      return left && right ? `${left}/${right}` : "";
    }

    function previewPath(runDir, path) {
      const value = String(path || "").replace(/^\\//, "");
      if (value.startsWith("runs/") || value.startsWith("data/")) {
        return value;
      }
      return joinPath(runDir, value);
    }

    document.querySelectorAll("[data-view-target]").forEach((node) => {
      node.addEventListener("click", () => setView(node.dataset.viewTarget));
    });
    document.querySelector("#data-group-filter").addEventListener("change", renderDataStores);
    document.querySelector("#data-search-filter").addEventListener("input", renderDataStores);
    window.addEventListener("hashchange", () => setView(viewFromHash()));

    fetchJson(endpoints.overview).then(renderOverview).catch(renderOverviewFailure);
    setView(viewFromHash());
  </script>
</body>
</html>
"""
