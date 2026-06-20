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
    .artifacts-layout,
    .data-layout,
    .strategy-layout,
    .monitor-layout,
    .command-center-layout,
    .workbench-layout,
    .decision-risk-layout,
    .event-alert-layout,
    .outcomes-layout,
    .text-intelligence-layout {
      display: grid;
      grid-template-columns: minmax(300px, 0.38fr) minmax(0, 1fr);
      gap: 16px;
    }

    .run-list,
    .artifact-explorer-list,
    .strategy-list,
    .job-list {
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

    .strategy-layout .filter-bar {
      grid-template-columns: 1fr;
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

    .strategy-chart {
      display: grid;
      gap: 8px;
      min-height: 160px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-soft);
    }

    .strategy-chart svg {
      width: 100%;
      height: 136px;
      overflow: visible;
    }

    .command-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .command-inline {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: end;
    }

    .checkbox-line {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .checkbox-line input {
      width: 16px;
      height: 16px;
      margin: 0;
    }

    .command-button {
      display: grid;
      gap: 5px;
      min-height: 64px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
      color: var(--text);
      cursor: pointer;
      text-align: left;
    }

    .command-button:hover,
    .command-button:focus-visible {
      border-color: var(--border-strong);
      background: #f1eee7;
    }

    .command-title {
      font-weight: 720;
    }

    .command-meta {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }

    .number-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }

    .job-row {
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-soft);
    }

    .job-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .chart-label {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
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
      .artifacts-layout,
      .data-layout,
      .strategy-layout,
      .monitor-layout,
      .command-center-layout,
      .workbench-layout,
      .decision-risk-layout,
      .event-alert-layout,
      .outcomes-layout,
      .text-intelligence-layout {
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
      .filter-bar,
      .command-grid,
      .command-inline,
      .number-row {
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
    data-workbench-endpoint="/api/workbench"
    data-decision-risk-endpoint="/api/decision-risk"
    data-event-alert-endpoint="/api/event-alert"
    data-outcomes-endpoint="/api/outcomes"
    data-text-intelligence-endpoint="/api/text-intelligence"
    data-runs-endpoint="/api/runs"
    data-stores-endpoint="/api/data/stores"
    data-strategies-endpoint="/api/strategies"
    data-monitor-endpoint="/api/monitor"
    data-jobs-endpoint="/api/jobs"
    data-schedule-endpoint="/api/schedule/daily-report"
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
        <a class="nav-item" href="#artifacts" data-view-target="artifacts">
          <span>Artifacts</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#data" data-view-target="data">
          <span>Data stores</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#strategies" data-view-target="strategies">
          <span>Strategy lab</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#monitor" data-view-target="monitor">
          <span>Monitor</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#workbench" data-view-target="workbench">
          <span>Workbench</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#decision-risk" data-view-target="decision-risk">
          <span>Decision &amp; risk</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#event-alert" data-view-target="event-alert">
          <span>Event &amp; alerts</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#text-intelligence" data-view-target="text-intelligence">
          <span>Text intelligence</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#outcomes" data-view-target="outcomes">
          <span>Outcomes</span>
          <span class="nav-state">available</span>
        </a>
        <a class="nav-item" href="#commands" data-view-target="commands">
          <span>Command center</span>
          <span class="nav-state">available</span>
        </a>
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
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Local data explorer</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Strategy lab</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Monitor control</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Workbench</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Decision &amp; risk</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Event &amp; alerts</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Text intelligence</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Outcome tracking</span>
                <span class="planned-state">available</span>
              </div>
              <div class="planned-item">
                <span class="planned-title">Command center</span>
                <span class="planned-state">available</span>
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

      <section id="artifacts-view" class="view hidden" data-view="artifacts">
        <section class="topbar" aria-labelledby="artifacts-title">
          <div>
            <p class="eyebrow">Bounded local artifacts</p>
            <h1 id="artifacts-title">Artifact explorer</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Run index</span>
              <span id="artifact-runs-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="selected-artifact-run-status" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="artifacts-layout">
          <article class="wide-panel" aria-labelledby="artifact-run-list-title">
            <div class="panel-heading">
              <h2 id="artifact-run-list-title" class="panel-title">Artifact runs</h2>
              <span id="artifact-run-count" class="badge unknown">loading</span>
            </div>
            <div id="artifact-run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="artifact-explorer-title">
            <div class="panel-heading">
              <h2 id="artifact-explorer-title" class="panel-title">Artifact inventory</h2>
              <span id="artifact-explorer-count" class="badge unknown">waiting</span>
            </div>
            <div class="filter-bar">
              <select id="artifact-layer-filter" class="filter-control" aria-label="Artifact layer filter">
                <option value="all">All layers</option>
                <option value="manifest">Manifest</option>
                <option value="raw">Raw</option>
                <option value="analysis">Analysis</option>
                <option value="report">Report</option>
                <option value="codex_context">Codex context</option>
                <option value="data">Data</option>
                <option value="monitor">Monitor</option>
                <option value="dashboard">Dashboard</option>
                <option value="other">Other</option>
              </select>
              <input id="artifact-search-filter" class="filter-control" type="search" placeholder="Filter by key, path, layer, stage, kind, warning, or error">
            </div>
            <div id="artifact-explorer-list" class="artifact-explorer-list">
              <div class="message">Select a run to inspect recorded artifact refs.</div>
            </div>
            <div id="artifact-explorer-preview" class="preview-panel">
              <div class="message">Open an artifact to inspect a bounded preview.</div>
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

      <section id="strategies-view" class="view hidden" data-view="strategies">
        <section class="topbar" aria-labelledby="strategies-title">
          <div>
            <p class="eyebrow">Historical strategy research</p>
            <h1 id="strategies-title">Strategy lab</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Research state</span>
              <span id="strategy-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected item</span>
              <span id="selected-strategy-status" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="strategy-layout">
          <article class="wide-panel" aria-labelledby="strategy-list-title">
            <div class="panel-heading">
              <h2 id="strategy-list-title" class="panel-title">Strategy outputs</h2>
              <span id="strategy-count" class="badge unknown">loading</span>
            </div>
            <div class="filter-bar">
              <select id="strategy-scope-filter" class="filter-control" aria-label="Strategy output filter">
                <option value="all">All outputs</option>
                <option value="pipeline">Pipeline artifacts</option>
                <option value="backtests">Standalone backtests</option>
                <option value="experiments">Standalone experiments</option>
                <option value="gates">Gates</option>
                <option value="lifecycle">Lifecycle</option>
                <option value="warnings">Warnings</option>
              </select>
              <input id="strategy-search-filter" class="filter-control" type="search" placeholder="Filter by strategy, symbol, timeframe, gate, lifecycle, or artifact">
            </div>
            <div id="strategy-list" class="strategy-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="strategy-detail-title">
            <div class="panel-heading">
              <h2 id="strategy-detail-title" class="panel-title">Strategy detail</h2>
              <span id="strategy-detail-badge" class="badge unknown">waiting</span>
            </div>
            <div id="strategy-detail" class="detail-sections">
              <div class="message">Select a strategy output to inspect bounded metrics, gates, lifecycle state, warnings, and source refs.</div>
            </div>
            <div id="strategy-preview" class="preview-panel">
              <div class="message">Open a strategy artifact preview to inspect bounded JSON or text output.</div>
            </div>
          </article>
        </section>
      </section>

      <section id="monitor-view" class="view hidden" data-view="monitor">
        <section class="topbar" aria-labelledby="monitor-title">
          <div>
            <p class="eyebrow">Local monitoring operations</p>
            <h1 id="monitor-title">Monitor control</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Monitor state</span>
              <span id="monitor-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Monitor jobs</span>
              <span id="monitor-job-status" class="status-value">Loading</span>
            </div>
          </div>
        </section>
        <section class="monitor-layout">
          <article class="wide-panel" aria-labelledby="monitor-health-title">
            <div class="panel-heading">
              <h2 id="monitor-health-title" class="panel-title">Monitor health</h2>
              <span id="monitor-health-badge" class="badge unknown">loading</span>
            </div>
            <div id="monitor-summary-grid" class="run-detail-grid"></div>
            <div class="detail-sections">
              <section class="section-block">
                <h3 class="subheading">
                  <span>Alert counts</span>
                  <span id="monitor-alert-badge" class="badge unknown">loading</span>
                </h3>
                <div id="monitor-alert-counts" class="run-detail-grid"></div>
              </section>
              <section class="section-block">
                <h3 class="subheading">
                  <span>Explicit controls</span>
                  <span class="badge partial">bounded local jobs</span>
                </h3>
                <div class="message warning">Monitor commands start explicit bounded local jobs from this dashboard; they are not hidden services.</div>
                <div class="command-grid" aria-label="Monitor commands">
                  <button class="command-button" type="button" data-monitor-action="dry-run">
                    <span class="command-title">Dry run</span>
                    <span class="command-meta">Validate monitor configuration without executing a cycle.</span>
                  </button>
                  <button class="command-button" type="button" data-monitor-action="once">
                    <span class="command-title">Run one cycle</span>
                    <span class="command-meta">Start one bounded monitor cycle.</span>
                  </button>
                </div>
                <div class="number-row">
                  <label>
                    <span class="status-label">Max cycles</span>
                    <input id="monitor-loop-cycles" class="filter-control" type="number" min="1" value="1">
                  </label>
                  <label>
                    <span class="status-label">Interval seconds</span>
                    <input id="monitor-loop-interval" class="filter-control" type="number" min="1" value="300">
                  </label>
                </div>
                <button class="command-button" type="button" data-monitor-action="loop">
                  <span class="command-title">Start finite loop</span>
                  <span class="command-meta">Run the configured max cycles, then stop.</span>
                </button>
              </section>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="monitor-activity-title">
            <div class="panel-heading">
              <h2 id="monitor-activity-title" class="panel-title">Monitor activity</h2>
              <span id="monitor-cycle-count" class="badge unknown">loading</span>
            </div>
            <div class="detail-sections">
              <section class="section-block">
                <h3 class="subheading">
                  <span>Recent cycles</span>
                  <span id="monitor-cycle-badge" class="badge unknown">loading</span>
                </h3>
                <ul id="monitor-cycle-list" class="stage-list"></ul>
              </section>
              <section class="section-block">
                <h3 class="subheading">
                  <span>Monitor jobs</span>
                  <span id="monitor-job-count" class="badge unknown">loading</span>
                </h3>
                <div id="monitor-job-list" class="job-list"></div>
              </section>
              <section class="section-block">
                <h3 class="subheading">
                  <span>Alert sample</span>
                  <span id="monitor-alert-sample-badge" class="badge unknown">loading</span>
                </h3>
                <ul id="monitor-alert-sample" class="stage-list"></ul>
              </section>
            </div>
          </article>
        </section>
      </section>

      <section id="workbench-view" class="view hidden" data-view="workbench">
        <section class="topbar" aria-labelledby="workbench-title">
          <div>
            <p class="eyebrow">Local delivery workbench</p>
            <h1 id="workbench-title">Workbench</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Workbench state</span>
              <span id="workbench-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Generated</span>
              <span id="workbench-generated" class="status-value">...</span>
            </div>
          </div>
        </section>
        <section class="workbench-layout">
          <article class="wide-panel" aria-labelledby="workbench-summary-title">
            <div class="panel-heading">
              <h2 id="workbench-summary-title" class="panel-title">Workbench summary</h2>
              <span id="workbench-summary-badge" class="badge unknown">loading</span>
            </div>
            <div id="workbench-summary-grid" class="run-detail-grid"></div>
            <div class="command-grid">
              <button class="command-button" type="button" data-command-intent="workbench_build">
                <span class="command-title">Build workbench</span>
                <span class="command-meta">Create a visible dashboard job; this page does not build implicitly.</span>
              </button>
              <button class="command-button" type="button" data-command-intent="workbench_inspect">
                <span class="command-title">Inspect workbench</span>
                <span class="command-meta">Create a read-only inspection job for the latest summary.</span>
              </button>
            </div>
            <div id="workbench-messages"></div>
            <section class="section-block">
              <h3 class="subheading">
                <span>Source refs</span>
                <span id="workbench-source-count" class="badge unknown">loading</span>
              </h3>
              <div id="workbench-source-list" class="artifact-actions"></div>
            </section>
            <div id="workbench-preview" class="preview-panel">
              <div class="message">Open a workbench source ref to inspect a bounded preview.</div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="workbench-sections-title">
            <div class="panel-heading">
              <h2 id="workbench-sections-title" class="panel-title">State sections</h2>
              <span id="workbench-section-count" class="badge unknown">loading</span>
            </div>
            <div id="workbench-section-list" class="detail-sections">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
        </section>
      </section>

      <section id="decision-risk-view" class="view hidden" data-view="decision-risk">
        <section class="topbar" aria-labelledby="decision-risk-title">
          <div>
            <p class="eyebrow">Deterministic decision support</p>
            <h1 id="decision-risk-title">Decision &amp; risk</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Decision state</span>
              <span id="decision-risk-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="decision-risk-selected-run" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="decision-risk-layout">
          <article class="wide-panel" aria-labelledby="decision-run-list-title">
            <div class="panel-heading">
              <h2 id="decision-run-list-title" class="panel-title">Runs</h2>
              <span id="decision-run-count" class="badge unknown">loading</span>
            </div>
            <div id="decision-run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="decision-artifacts-title">
            <div class="panel-heading">
              <h2 id="decision-artifacts-title" class="panel-title">Decision artifacts</h2>
              <span id="decision-artifact-count" class="badge unknown">waiting</span>
            </div>
            <div id="decision-artifact-list" class="store-grid">
              <div class="message">Select a run to inspect decision and risk artifacts.</div>
            </div>
            <div id="decision-artifact-detail" class="detail-sections">
              <div class="message">Open an artifact summary to inspect counts, status, warnings, and refs.</div>
            </div>
            <div id="decision-preview" class="preview-panel">
              <div class="message">Open a decision or risk source ref to inspect a bounded preview.</div>
            </div>
          </article>
        </section>
      </section>

      <section id="event-alert-view" class="view hidden" data-view="event-alert">
        <section class="topbar" aria-labelledby="event-alert-title">
          <div>
            <p class="eyebrow">Event intelligence and alert decisions</p>
            <h1 id="event-alert-title">Event &amp; alerts</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Event state</span>
              <span id="event-alert-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="event-alert-selected-run" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="event-alert-layout">
          <article class="wide-panel" aria-labelledby="event-run-list-title">
            <div class="panel-heading">
              <h2 id="event-run-list-title" class="panel-title">Runs</h2>
              <span id="event-run-count" class="badge unknown">loading</span>
            </div>
            <div id="event-run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="event-artifacts-title">
            <div class="panel-heading">
              <h2 id="event-artifacts-title" class="panel-title">Event and alert artifacts</h2>
              <span id="event-artifact-count" class="badge unknown">waiting</span>
            </div>
            <div id="event-artifact-list" class="store-grid">
              <div class="message">Select a run to inspect event and alert artifacts.</div>
            </div>
            <div id="event-artifact-detail" class="detail-sections">
              <div class="message">Open an artifact summary to inspect status, counts, warnings, and refs.</div>
            </div>
            <div id="event-preview" class="preview-panel">
              <div class="message">Open an event or alert source ref to inspect a bounded preview.</div>
            </div>
          </article>
        </section>
      </section>

      <section id="text-intelligence-view" class="view hidden" data-view="text-intelligence">
        <section class="topbar" aria-labelledby="text-intelligence-title">
          <div>
            <p class="eyebrow">Source-aware text processing</p>
            <h1 id="text-intelligence-title">Text intelligence</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Text state</span>
              <span id="text-intelligence-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="text-intelligence-selected-run" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="text-intelligence-layout">
          <article class="wide-panel" aria-labelledby="text-run-list-title">
            <div class="panel-heading">
              <h2 id="text-run-list-title" class="panel-title">Runs</h2>
              <span id="text-run-count" class="badge unknown">loading</span>
            </div>
            <div id="text-run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
            <section class="section-block">
              <h3 class="subheading">
                <span>Text commands</span>
                <span id="text-command-status" class="badge partial">ready</span>
              </h3>
              <div class="number-row">
                <label>
                  <span class="status-label">Input path</span>
                  <input id="text-input-path" class="filter-control" type="text" placeholder="runs/&lt;run_id&gt;/raw/text_events.json">
                </label>
                <label>
                  <span class="status-label">Output dir</span>
                  <input id="text-output-dir" class="filter-control" type="text" placeholder="runs/text_intelligence">
                </label>
              </div>
              <div class="command-grid">
                <button class="command-button" type="button" data-text-command-intent="text_models_prepare">
                  <span class="command-title">Prepare text models</span>
                  <span class="command-meta">Prepare configured local text model artifacts.</span>
                </button>
                <button class="command-button" type="button" data-text-command-intent="text_intel">
                  <span class="command-title">Run text intelligence</span>
                  <span class="command-meta">Process configured or selected text event input.</span>
                </button>
              </div>
            </section>
          </article>
          <article class="wide-panel" aria-labelledby="text-artifacts-title">
            <div class="panel-heading">
              <h2 id="text-artifacts-title" class="panel-title">Text artifacts</h2>
              <span id="text-artifact-count" class="badge unknown">waiting</span>
            </div>
            <div id="text-artifact-list" class="store-grid">
              <div class="message">Select a run to inspect text intelligence artifacts.</div>
            </div>
            <div id="text-artifact-detail" class="detail-sections">
              <div class="message">Open a text artifact summary to inspect status, counts, warnings, and refs.</div>
            </div>
            <section class="section-block">
              <div class="panel-heading">
                <h2 class="panel-title">Text jobs</h2>
                <span id="text-job-count" class="badge unknown">loading</span>
              </div>
              <div id="text-job-result" class="preview-panel">
                <div class="message">Start or select a text job to inspect result refs.</div>
              </div>
              <div id="text-job-list" class="job-list">
                <div class="skeleton"></div>
                <div class="skeleton"></div>
              </div>
            </section>
            <div id="text-preview" class="preview-panel">
              <div class="message">Open a text source ref or job result ref to inspect a bounded preview.</div>
            </div>
          </article>
        </section>
      </section>

      <section id="outcomes-view" class="view hidden" data-view="outcomes">
        <section class="topbar" aria-labelledby="outcomes-title">
          <div>
            <p class="eyebrow">Outcome accountability</p>
            <h1 id="outcomes-title">Outcome tracking</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Outcome state</span>
              <span id="outcome-status" class="status-value">Loading</span>
            </div>
            <div class="status-line">
              <span class="status-label">Selected run</span>
              <span id="outcome-selected-run" class="status-value">none</span>
            </div>
          </div>
        </section>
        <section class="outcomes-layout">
          <article class="wide-panel" aria-labelledby="outcome-run-list-title">
            <div class="panel-heading">
              <h2 id="outcome-run-list-title" class="panel-title">Runs</h2>
              <span id="outcome-run-count" class="badge unknown">loading</span>
            </div>
            <div id="outcome-run-list" class="run-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="outcome-artifacts-title">
            <div class="panel-heading">
              <h2 id="outcome-artifacts-title" class="panel-title">Run outcome artifacts</h2>
              <span id="outcome-artifact-count" class="badge unknown">waiting</span>
            </div>
            <div id="outcome-artifact-list" class="store-grid">
              <div class="message">Select a run to inspect outcome targets and evaluations.</div>
            </div>
            <div id="outcome-artifact-detail" class="detail-sections">
              <div class="message">Open an outcome artifact summary to inspect status, counts, warnings, and refs.</div>
            </div>
            <div id="outcome-history-detail" class="detail-sections">
              <div class="message">Outcome history metadata is loading.</div>
            </div>
            <div id="outcome-preview" class="preview-panel">
              <div class="message">Open an outcome source ref to inspect a bounded preview.</div>
            </div>
          </article>
        </section>
      </section>

      <section id="commands-view" class="view hidden" data-view="commands">
        <section class="topbar" aria-labelledby="commands-title">
          <div>
            <p class="eyebrow">Allowlisted local commands</p>
            <h1 id="commands-title">Command center</h1>
          </div>
          <div class="status-panel" aria-live="polite">
            <div class="status-line">
              <span class="status-label">Command state</span>
              <span id="command-center-status" class="status-value">Idle</span>
            </div>
            <div class="status-line">
              <span class="status-label">Jobs</span>
              <span id="command-job-status" class="status-value">Loading</span>
            </div>
          </div>
        </section>
        <section class="command-center-layout">
          <article class="wide-panel" aria-labelledby="command-groups-title">
            <div class="panel-heading">
              <h2 id="command-groups-title" class="panel-title">Command groups</h2>
              <span class="badge partial">allowlisted</span>
            </div>
            <div class="detail-sections">
              <section class="section-block">
                <h3 class="subheading">
                  <span>Daily report schedule</span>
                  <span id="daily-schedule-badge" class="badge unknown">loading</span>
                </h3>
                <div id="daily-schedule-summary" class="run-detail-grid">
                  <div class="skeleton"></div>
                  <div class="skeleton"></div>
                </div>
                <div class="number-row">
                  <label>
                    <span class="status-label">Time of day</span>
                    <input id="daily-schedule-time" class="filter-control" type="time" value="08:00">
                  </label>
                  <label>
                    <span class="status-label">Timezone</span>
                    <input id="daily-schedule-timezone" class="filter-control" type="text" value="UTC">
                  </label>
                </div>
                <label>
                  <span class="status-label">Job intent</span>
                  <select id="daily-schedule-job-intent" class="filter-control">
                    <option value="run_no_codex">run_no_codex</option>
                    <option value="run">run</option>
                  </select>
                </label>
                <label class="checkbox-line">
                  <input id="daily-schedule-confirm-codex" type="checkbox">
                  <span>I explicitly confirm this manual daily report trigger may invoke Codex.</span>
                </label>
                <div class="command-grid">
                  <button class="command-button" type="button" data-schedule-action="update">
                    <span class="command-title">Update schedule</span>
                    <span class="command-meta">Persist time, timezone, and job intent without triggering a run.</span>
                  </button>
                  <button class="command-button" type="button" data-schedule-action="enable">
                    <span class="command-title">Enable schedule</span>
                    <span class="command-meta">Enable the local daily report schedule state.</span>
                  </button>
                  <button class="command-button" type="button" data-schedule-action="disable">
                    <span class="command-title">Disable schedule</span>
                    <span class="command-meta">Disable the local daily report schedule state.</span>
                  </button>
                  <button class="command-button" type="button" data-schedule-action="trigger">
                    <span class="command-title">Trigger now</span>
                    <span class="command-meta">Create a visible dashboard job from the selected schedule intent.</span>
                  </button>
                </div>
                <div id="daily-schedule-messages"></div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Product runs</span>
                  <span class="badge partial">Codex confirmation required</span>
                </h3>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="run_no_codex">
                    <span class="command-title">Run without Codex</span>
                    <span class="command-meta">Execute the product pipeline with report generation skipped.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="run">
                    <span class="command-title">Run with Codex</span>
                    <span class="command-meta">Requires the Codex confirmation checkbox below.</span>
                  </button>
                </div>
                <label class="checkbox-line">
                  <input id="command-run-confirm-codex" type="checkbox">
                  <span>I explicitly confirm this dashboard job may invoke Codex.</span>
                </label>
                <div class="command-inline">
                  <label>
                    <span class="status-label">Run until stage</span>
                    <input id="command-run-until-stage" class="filter-control" type="text" placeholder="build_research_context">
                  </label>
                  <button class="link-button" type="button" data-command-intent="run_until">Run until</button>
                </div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Validation and inspection</span>
                  <span class="badge available">read-only</span>
                </h3>
                <label>
                  <span class="status-label">Run dir for scoped commands</span>
                  <input id="command-run-dir" class="filter-control" type="text" placeholder="runs/&lt;run_id&gt;">
                </label>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="validate">
                    <span class="command-title">Validate</span>
                    <span class="command-meta">Run product validation for config or selected run dir.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="data_inspect">
                    <span class="command-title">Data inspect</span>
                    <span class="command-meta">Inspect local data stores and optional run context.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="outcomes_inspect">
                    <span class="command-title">Outcomes inspect</span>
                    <span class="command-meta">Inspect local outcome state and optional run context.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="monitor_inspect">
                    <span class="command-title">Monitor inspect</span>
                    <span class="command-meta">Inspect local monitor state without starting cycles.</span>
                  </button>
                </div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Workbench</span>
                  <span class="badge available">local delivery</span>
                </h3>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="workbench_build">
                    <span class="command-title">Build workbench</span>
                    <span class="command-meta">Build local workbench output, optionally scoped by run dir.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="workbench_inspect">
                    <span class="command-title">Inspect workbench</span>
                    <span class="command-meta">Inspect the latest local workbench summary.</span>
                  </button>
                </div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Strategy research</span>
                  <span class="badge partial">historical research</span>
                </h3>
                <div class="number-row">
                  <label>
                    <span class="status-label">Strategy</span>
                    <input id="command-backtest-strategy" class="filter-control" type="text" placeholder="tsmom_vol_scaled">
                  </label>
                  <label>
                    <span class="status-label">Symbol</span>
                    <input id="command-backtest-symbol" class="filter-control" type="text" placeholder="BTCUSDT">
                  </label>
                </div>
                <div class="number-row">
                  <label>
                    <span class="status-label">Timeframe</span>
                    <input id="command-backtest-timeframe" class="filter-control" type="text" placeholder="1d">
                  </label>
                  <label>
                    <span class="status-label">Output dir</span>
                    <input id="command-strategy-output-dir" class="filter-control" type="text" placeholder="runs/strategy_backtests">
                  </label>
                </div>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="backtest">
                    <span class="command-title">Run backtest</span>
                    <span class="command-meta">Start one configured standalone strategy backtest.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="experiment">
                    <span class="command-title">Run experiment</span>
                    <span class="command-meta">Use comma-separated strategy names from the strategy field.</span>
                  </button>
                </div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Text intelligence</span>
                  <span class="badge partial">bounded artifacts</span>
                </h3>
                <div class="number-row">
                  <label>
                    <span class="status-label">Input path</span>
                    <input id="command-text-input-path" class="filter-control" type="text" placeholder="runs/&lt;run_id&gt;/raw/text_events.json">
                  </label>
                  <label>
                    <span class="status-label">Output dir</span>
                    <input id="command-text-output-dir" class="filter-control" type="text" placeholder="runs/text_intel">
                  </label>
                </div>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="text_models_prepare">
                    <span class="command-title">Prepare text models</span>
                    <span class="command-meta">Prepare configured local text model artifacts.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="text_intel">
                    <span class="command-title">Run text intelligence</span>
                    <span class="command-meta">Process configured or selected text event input.</span>
                  </button>
                </div>
              </section>

              <section class="section-block">
                <h3 class="subheading">
                  <span>Monitor commands</span>
                  <span class="badge partial">bounded local jobs</span>
                </h3>
                <div class="command-grid">
                  <button class="command-button" type="button" data-command-intent="monitor_dry_run">
                    <span class="command-title">Monitor dry run</span>
                    <span class="command-meta">Validate monitor configuration without executing a cycle.</span>
                  </button>
                  <button class="command-button" type="button" data-command-intent="monitor_once">
                    <span class="command-title">Monitor one cycle</span>
                    <span class="command-meta">Start one bounded monitor cycle.</span>
                  </button>
                </div>
                <div class="number-row">
                  <label>
                    <span class="status-label">Max cycles</span>
                    <input id="command-monitor-loop-cycles" class="filter-control" type="number" min="1" value="1">
                  </label>
                  <label>
                    <span class="status-label">Interval seconds</span>
                    <input id="command-monitor-loop-interval" class="filter-control" type="number" min="1" value="300">
                  </label>
                </div>
                <button class="command-button" type="button" data-command-intent="monitor_loop">
                  <span class="command-title">Monitor finite loop</span>
                  <span class="command-meta">Run configured max cycles, then stop.</span>
                </button>
              </section>
            </div>
          </article>
          <article class="wide-panel" aria-labelledby="command-jobs-title">
            <div class="panel-heading">
              <h2 id="command-jobs-title" class="panel-title">Job history</h2>
              <span id="command-job-count" class="badge unknown">loading</span>
            </div>
            <div class="filter-bar">
              <input id="command-job-intent-filter" class="filter-control" type="search" placeholder="Filter intent">
              <select id="command-job-status-filter" class="filter-control" aria-label="Job status filter">
                <option value="all">All statuses</option>
                <option value="active">Active</option>
                <option value="terminal">Terminal</option>
                <option value="queued">Queued</option>
                <option value="running">Running</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
                <option value="blocked">Blocked</option>
                <option value="cancelled">Cancelled</option>
              </select>
              <input id="command-job-kind-filter" class="filter-control" type="search" placeholder="Filter kind">
            </div>
            <div id="command-result" class="preview-panel">
              <div class="message">Choose an allowlisted command or open a job to inspect details.</div>
            </div>
            <div id="command-job-preview" class="preview-panel">
              <div class="message">Open a job result ref, stdout, or stderr to inspect a bounded preview.</div>
            </div>
            <div id="command-job-list" class="job-list">
              <div class="skeleton"></div>
              <div class="skeleton"></div>
              <div class="skeleton"></div>
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
      workbench: app.dataset.workbenchEndpoint,
      decisionRisk: app.dataset.decisionRiskEndpoint,
      eventAlert: app.dataset.eventAlertEndpoint,
      outcomes: app.dataset.outcomesEndpoint,
      textIntelligence: app.dataset.textIntelligenceEndpoint,
      runs: app.dataset.runsEndpoint,
      stores: app.dataset.storesEndpoint,
      strategies: app.dataset.strategiesEndpoint,
      monitor: app.dataset.monitorEndpoint,
      jobs: app.dataset.jobsEndpoint,
      schedule: app.dataset.scheduleEndpoint,
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
      effective: "Effective",
      watchlisted: "Watchlisted",
      rejected: "Rejected",
      insufficient_evidence: "Insufficient evidence",
      active_candidate: "Active candidate",
      retired: "Retired",
      queued: "Queued",
      running: "Running",
      cancel_requested: "Cancel requested",
      cancelled: "Cancelled",
      blocked: "Blocked",
      unsupported: "Unsupported",
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
    let artifactsLoaded = false;
    let artifactRunsPayload = null;
    const artifactRunDetails = new Map();
    let selectedArtifactRunId = null;
    let selectedArtifactPath = null;
    let dataStoresLoaded = false;
    let dataStoresPayload = null;
    let selectedStoreName = null;
    let strategiesLoaded = false;
    let strategiesPayload = null;
    let selectedStrategyKey = null;
    let monitorLoaded = false;
    let monitorPayload = null;
    let monitorJobPoll = null;
    let workbenchLoaded = false;
    let workbenchPayload = null;
    let decisionRiskLoaded = false;
    let decisionRunsPayload = null;
    let decisionRiskPayload = null;
    let selectedDecisionRunId = null;
    let selectedDecisionArtifactKey = null;
    let eventAlertLoaded = false;
    let eventRunsPayload = null;
    let eventAlertPayload = null;
    let selectedEventRunId = null;
    let selectedEventArtifactKey = null;
    let textIntelligenceLoaded = false;
    let textRunsPayload = null;
    let textIntelligencePayload = null;
    let selectedTextRunId = null;
    let selectedTextArtifactKey = null;
    let textJobsPayload = null;
    let outcomesLoaded = false;
    let outcomeRunsPayload = null;
    let outcomesPayload = null;
    let selectedOutcomeRunId = null;
    let selectedOutcomeArtifactKey = null;
    let commandJobsLoaded = false;
    let commandJobPoll = null;
    let dailyScheduleLoaded = false;
    let commandJobsPayload = null;
    let selectedCommandJobId = null;
    const terminalJobStatuses = new Set(["succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started", "missing"]);

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
      if (["effective", "active_candidate"].includes(value)) {
        return "available";
      }
      if (["watchlisted", "insufficient_evidence"].includes(value)) {
        return "partial";
      }
      if (["queued", "running", "cancel_requested"].includes(value)) {
        return "partial";
      }
      if (["rejected", "retired"].includes(value)) {
        return "degraded";
      }
      if (["cancelled", "blocked", "unsupported"].includes(value)) {
        return "degraded";
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

    async function postJson(url, body) {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {})
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    }

    function viewFromHash() {
      if (window.location.hash === "#runs") {
        return "runs";
      }
      if (window.location.hash === "#artifacts") {
        return "artifacts";
      }
      if (window.location.hash === "#data") {
        return "data";
      }
      if (window.location.hash === "#strategies") {
        return "strategies";
      }
      if (window.location.hash === "#monitor") {
        return "monitor";
      }
      if (window.location.hash === "#workbench") {
        return "workbench";
      }
      if (window.location.hash === "#decision-risk") {
        return "decision-risk";
      }
      if (window.location.hash === "#event-alert") {
        return "event-alert";
      }
      if (window.location.hash === "#text-intelligence") {
        return "text-intelligence";
      }
      if (window.location.hash === "#outcomes") {
        return "outcomes";
      }
      if (window.location.hash === "#commands") {
        return "commands";
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
      if (view === "artifacts" && !artifactsLoaded) {
        loadArtifacts();
      }
      if (view === "data" && !dataStoresLoaded) {
        loadDataStores();
      }
      if (view === "strategies" && !strategiesLoaded) {
        loadStrategies();
      }
      if (view === "monitor" && !monitorLoaded) {
        loadMonitor();
      }
      if (view === "workbench" && !workbenchLoaded) {
        loadWorkbench();
      }
      if (view === "decision-risk" && !decisionRiskLoaded) {
        loadDecisionRisk();
      }
      if (view === "event-alert" && !eventAlertLoaded) {
        loadEventAlert();
      }
      if (view === "text-intelligence" && !textIntelligenceLoaded) {
        loadTextIntelligence();
      }
      if (view === "outcomes" && !outcomesLoaded) {
        loadOutcomes();
      }
      if (view === "commands" && !commandJobsLoaded) {
        loadCommandCenter();
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

    async function loadArtifacts() {
      artifactsLoaded = true;
      document.querySelector("#artifact-runs-status").textContent = "Loading";
      try {
        artifactRunsPayload = await fetchJson(endpoints.runs);
        renderArtifactRunList();
        const runs = Array.isArray(artifactRunsPayload.runs) ? artifactRunsPayload.runs : [];
        if (runs.length) {
          selectArtifactRun(runs[0].run_id);
        } else {
          renderArtifactExplorerEmpty(artifactRunsPayload);
        }
      } catch (error) {
        renderArtifactRunListFailure(error);
      }
    }

    function renderArtifactRunList() {
      const payload = artifactRunsPayload || { status: "unknown", runs: [] };
      const runs = Array.isArray(payload.runs) ? payload.runs : [];
      document.querySelector("#artifact-runs-status").textContent = label(payload.status);
      const count = document.querySelector("#artifact-run-count");
      count.className = `badge ${runs.length ? "available" : normalizeStatus(payload.status)}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      const list = document.querySelector("#artifact-run-list");
      if (!runs.length) {
        list.innerHTML = messages(payload) || `<div class="message warning">No runs are recorded in the local run index.</div>`;
        return;
      }
      list.innerHTML = runs.map((run) => `
        <button class="run-row ${run.run_id === selectedArtifactRunId ? "selected" : ""}" type="button" data-artifact-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Artifacts: ${escapeHtml(text(run.artifact_count))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      list.querySelectorAll("[data-artifact-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectArtifactRun(button.dataset.artifactRunId));
      });
    }

    function renderArtifactRunListFailure(error) {
      document.querySelector("#artifact-runs-status").textContent = "Failed";
      document.querySelector("#artifact-run-count").className = "badge failed";
      document.querySelector("#artifact-run-count").textContent = "failed";
      document.querySelector("#artifact-run-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      renderArtifactExplorerEmpty({ status: "failed", errors: [error.message], warnings: [] });
    }

    async function selectArtifactRun(runId) {
      if (!runId) {
        return;
      }
      selectedArtifactRunId = runId;
      selectedArtifactPath = null;
      document.querySelector("#selected-artifact-run-status").textContent = runId;
      document.querySelectorAll("[data-artifact-run-id]").forEach((button) => {
        button.classList.toggle("selected", button.dataset.artifactRunId === runId);
      });
      document.querySelector("#artifact-explorer-count").className = "badge unknown";
      document.querySelector("#artifact-explorer-count").textContent = "loading";
      document.querySelector("#artifact-explorer-list").innerHTML = `<div class="message">Loading artifact refs.</div>`;
      document.querySelector("#artifact-explorer-preview").innerHTML = `<div class="message">Open an artifact to inspect a bounded preview.</div>`;
      try {
        const detail = artifactRunDetails.get(runId) || await fetchJson(`${endpoints.runs}/${encodeURIComponent(runId)}`);
        artifactRunDetails.set(runId, detail);
        renderArtifactExplorer();
      } catch (error) {
        renderArtifactExplorerFailure(runId, error);
      }
    }

    function renderArtifactExplorerEmpty(payload) {
      document.querySelector("#selected-artifact-run-status").textContent = "none";
      document.querySelector("#artifact-explorer-count").className = `badge ${normalizeStatus(payload.status)}`;
      document.querySelector("#artifact-explorer-count").textContent = "0 refs";
      document.querySelector("#artifact-explorer-list").innerHTML = messages(payload) || `<div class="message warning">No artifact refs are available.</div>`;
      document.querySelector("#artifact-explorer-preview").innerHTML = `<div class="message">Open an artifact to inspect a bounded preview.</div>`;
    }

    function renderArtifactExplorerFailure(runId, error) {
      document.querySelector("#selected-artifact-run-status").textContent = runId;
      document.querySelector("#artifact-explorer-count").className = "badge failed";
      document.querySelector("#artifact-explorer-count").textContent = "failed";
      document.querySelector("#artifact-explorer-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
    }

    function renderArtifactExplorer() {
      const detail = artifactRunDetails.get(selectedArtifactRunId);
      if (!detail || detail.status !== "available") {
        renderArtifactExplorerEmpty(detail || { status: "missing", warnings: ["selected run detail is not available."], errors: [] });
        return;
      }
      const artifacts = filteredArtifactRefs(flattenArtifactRefs(detail));
      const count = document.querySelector("#artifact-explorer-count");
      count.className = `badge ${artifacts.length ? "available" : "missing"}`;
      count.textContent = `${artifacts.length} ref${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#artifact-explorer-list").innerHTML = `<div class="message warning">No artifact refs match the current filter.</div>`;
        return;
      }
      if (!artifacts.some((artifact) => artifact.previewPath === selectedArtifactPath)) {
        selectedArtifactPath = artifacts[0].previewPath;
      }
      document.querySelector("#artifact-explorer-list").innerHTML = artifacts.map((artifact) => `
        <button class="store-card ${artifact.previewPath === selectedArtifactPath ? "selected" : ""}" type="button" data-explorer-artifact-path="${escapeHtml(artifact.previewPath)}">
          <span class="store-title-line">
            <span class="store-title">${escapeHtml(artifact.key)}</span>
            ${badge(artifact.status)}
          </span>
          <span class="store-metrics">
            <span>Layer: ${escapeHtml(artifact.layer)}</span>
            <span>Kind: ${escapeHtml(artifact.kind)}</span>
            ${artifact.stage ? `<span>Stage: ${escapeHtml(artifact.stage)}</span>` : ""}
          </span>
          <span class="timeline-meta">${escapeHtml(artifact.previewPath)}</span>
        </button>`).join("");
      document.querySelectorAll("[data-explorer-artifact-path]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedArtifactPath = button.dataset.explorerArtifactPath;
          renderArtifactExplorer();
        });
      });
      if (selectedArtifactPath) {
        loadArtifactPreview(selectedArtifactPath, "#artifact-explorer-preview");
      }
    }

    function flattenArtifactRefs(detail) {
      const fields = detail.fields || {};
      const runDir = fields.run_dir || "";
      const rows = [];
      if (fields.manifest) {
        rows.push(artifactExplorerRecord({
          key: "run_manifest",
          path: fields.manifest,
          kind: "manifest",
          status: fields.manifest_status || detail.status,
          runDir
        }));
      }
      if (fields.report) {
        const reportPath = previewPath(runDir, fields.report);
        rows.push(artifactExplorerRecord({
          key: "report",
          path: reportPath,
          kind: "report",
          status: get("report.status", fields) || detail.status,
          runDir
        }));
      }
      (Array.isArray(detail.artifacts) ? detail.artifacts : []).forEach((artifact) => {
        rows.push(artifactExplorerRecord({ ...artifact, runDir }));
      });
      (Array.isArray(detail.stages) ? detail.stages : []).forEach((stage) => {
        (Array.isArray(stage.artifacts) ? stage.artifacts : []).forEach((artifact) => {
          rows.push(artifactExplorerRecord({
            ...artifact,
            key: artifact.key || stage.name || "stage_artifact",
            status: stage.status,
            stage: stage.name,
            runDir
          }));
        });
      });
      const seen = new Set();
      return rows.filter((artifact) => {
        if (!artifact.previewPath || seen.has(artifact.previewPath)) {
          return false;
        }
        seen.add(artifact.previewPath);
        return true;
      });
    }

    function artifactExplorerRecord(artifact) {
      const rawPath = text(artifact.path || artifact.artifact || artifact.preview_path || "");
      const preview = previewPath(artifact.runDir, rawPath);
      const layer = artifactLayer(preview, artifact.kind);
      return {
        key: text(artifact.key || artifact.name || artifact.kind || layer || "artifact"),
        path: rawPath,
        previewPath: preview,
        kind: text(artifact.kind || layer || "artifact"),
        layer,
        stage: String(artifact.stage || ""),
        status: text(artifact.status || "available")
      };
    }

    function artifactLayer(path, kind) {
      const value = String(path || "");
      const kindValue = String(kind || "");
      if (kindValue === "manifest" || value.endsWith("/run_manifest.json") || value === "run_manifest.json") {
        return "manifest";
      }
      if (value.includes("/raw/") || value.startsWith("raw/")) {
        return "raw";
      }
      if (value.includes("/analysis/") || value.startsWith("analysis/")) {
        return "analysis";
      }
      if (value.includes("/report/") || value.startsWith("report/")) {
        return "report";
      }
      if (value.includes("/codex_context/") || value.startsWith("codex_context/")) {
        return "codex_context";
      }
      if (value.startsWith("data/")) {
        return "data";
      }
      if (value.startsWith("runs/monitor/")) {
        return "monitor";
      }
      if (value.startsWith("runs/dashboard/")) {
        return "dashboard";
      }
      return "other";
    }

    function filteredArtifactRefs(artifacts) {
      const layer = document.querySelector("#artifact-layer-filter").value;
      const query = document.querySelector("#artifact-search-filter").value.trim().toLowerCase();
      return artifacts.filter((artifact) => {
        if (layer !== "all" && artifact.layer !== layer) {
          return false;
        }
        if (!query) {
          return true;
        }
        return [
          artifact.key,
          artifact.kind,
          artifact.layer,
          artifact.stage,
          artifact.status,
          artifact.path,
          artifact.previewPath
        ].join(" ").toLowerCase().includes(query);
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
        JSON.stringify(store.drilldown || {}),
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
      const drilldown = store.drilldown || {};
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
        ${renderDataStoreDrilldown(drilldown)}
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

    function renderDataStoreDrilldown(drilldown) {
      const summary = drilldown.summary || {};
      const dimensions = drilldown.dimensions || {};
      const ranges = drilldown.ranges || {};
      const groups = Array.isArray(drilldown.groups) ? drilldown.groups : [];
      const metadataRefs = Array.isArray(drilldown.metadata_refs) ? drilldown.metadata_refs : [];
      const warnings = Array.isArray(drilldown.warnings) ? drilldown.warnings : [];
      const omitted = drilldown.omitted || {};
      const tiles = [
        ["category", drilldown.category],
        ...Object.entries(summary),
        ...Object.entries(dimensions),
        ...Object.entries(ranges)
      ].slice(0, 16);
      return `
        <section class="section-block">
          <h3 class="subheading">
            <span>Store drilldown</span>
            <span class="badge ${groups.length ? "available" : "partial"}">${groups.length} group${groups.length === 1 ? "" : "s"}</span>
          </h3>
          <div class="run-detail-grid">
            ${tiles.map(([key, value]) => detailTile(key, value)).join("") || detailTile("category", drilldown.category)}
          </div>
          ${warnings.length ? `<ul class="message-list">${warnings.slice(0, 3).map((value) => `<li class="message warning">${escapeHtml(value)}</li>`).join("")}</ul>` : ""}
          <ul class="source-ref-list">
            ${groups.length ? groups.slice(0, 8).map((group) => `<li>${escapeHtml(formatPreview(group))}</li>`).join("") : `<li>No bounded groups recorded.</li>`}
          </ul>
          <div class="artifact-actions">
            ${metadataRefs.length ? metadataRefs.map((ref) => `<span class="badge available">${escapeHtml(ref)}</span>`).join("") : `<span class="badge missing">no metadata refs</span>`}
            ${omitted.group_records_omitted ? `<span class="badge partial">${escapeHtml(omitted.group_records_omitted)} omitted</span>` : ""}
          </div>
        </section>`;
    }

    async function loadStrategies() {
      strategiesLoaded = true;
      document.querySelector("#strategy-status").textContent = "Loading";
      try {
        strategiesPayload = await fetchJson(endpoints.strategies);
        renderStrategies();
      } catch (error) {
        renderStrategiesFailure(error);
      }
    }

    function renderStrategiesFailure(error) {
      document.querySelector("#strategy-status").textContent = "Failed";
      document.querySelector("#selected-strategy-status").textContent = "none";
      document.querySelector("#strategy-count").className = "badge failed";
      document.querySelector("#strategy-count").textContent = "failed";
      document.querySelector("#strategy-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#strategy-detail-badge").className = "badge failed";
      document.querySelector("#strategy-detail-badge").textContent = "failed";
      document.querySelector("#strategy-detail").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
    }

    function renderStrategies() {
      const payload = strategiesPayload || { status: "unknown" };
      const items = strategyItems(payload);
      const visible = items.filter(strategyMatchesFilters);
      document.querySelector("#strategy-status").textContent = label(payload.status);
      const count = document.querySelector("#strategy-count");
      count.className = `badge ${items.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;
      if (!visible.length) {
        document.querySelector("#strategy-list").innerHTML = `<div class="message warning">No strategy outputs match the current filter.</div>`;
        renderStrategyDetail(null);
        return;
      }
      if (!visible.some((item) => item.key === selectedStrategyKey)) {
        selectedStrategyKey = visible[0].key;
      }
      document.querySelector("#strategy-list").innerHTML = visible.map((item) => `
        <button class="store-card ${item.key === selectedStrategyKey ? "selected" : ""}" type="button" data-strategy-key="${escapeHtml(item.key)}">
          <span class="store-title-line">
            <span class="store-title">${escapeHtml(item.title)}</span>
            ${badge(item.status)}
          </span>
          <span class="store-metrics">
            <span>${escapeHtml(item.scopeLabel)}</span>
            <span>Warnings: ${escapeHtml(text(item.warnings.length))}</span>
            <span>Errors: ${escapeHtml(text(item.errors.length))}</span>
          </span>
          <span class="timeline-meta">${escapeHtml(item.subtitle)}</span>
        </button>`).join("");
      document.querySelectorAll("[data-strategy-key]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedStrategyKey = button.dataset.strategyKey;
          renderStrategies();
        });
      });
      renderStrategyDetail(visible.find((item) => item.key === selectedStrategyKey) || visible[0]);
    }

    function strategyItems(payload) {
      const pipeline = payload.pipeline || {};
      const standalone = payload.standalone || {};
      const selectedRun = payload.selected_run || {};
      const items = [];
      (Array.isArray(pipeline.artifacts) ? pipeline.artifacts : []).forEach((artifact) => {
        const kind = strategyKind(artifact.name);
        items.push({
          key: `pipeline:${artifact.name}`,
          group: "pipeline",
          kind,
          scopeLabel: "Pipeline",
          title: strategyTitle(artifact.name),
          subtitle: artifact.artifact || artifact.preview_path || selectedRun.run_id || "pipeline artifact",
          status: artifact.status || "unknown",
          fields: artifact.fields || {},
          records: artifact.records || {},
          sourceArtifacts: Array.isArray(artifact.source_artifacts) ? artifact.source_artifacts : [],
          previewPath: artifact.preview_path,
          warnings: Array.isArray(artifact.warnings) ? artifact.warnings : [],
          errors: Array.isArray(artifact.errors) ? artifact.errors : []
        });
      });
      (Array.isArray(standalone.backtests) ? standalone.backtests : []).forEach((item) => {
        items.push({
          key: `backtest:${item.output_dir}`,
          group: "backtests",
          kind: "backtest",
          scopeLabel: "Standalone backtest",
          title: `Backtest ${standaloneStrategyName(item)}`,
          subtitle: item.output_dir || "standalone backtest",
          status: item.status || "unknown",
          fields: item.fields || {},
          records: item.records || {},
          sourceArtifacts: Array.isArray(item.source_artifacts) ? item.source_artifacts : [],
          previewPath: firstPreviewableRef(item.source_artifacts),
          warnings: Array.isArray(item.warnings) ? item.warnings : [],
          errors: Array.isArray(item.errors) ? item.errors : []
        });
      });
      (Array.isArray(standalone.experiments) ? standalone.experiments : []).forEach((item) => {
        items.push({
          key: `experiment:${item.output_dir}`,
          group: "experiments",
          kind: "experiment",
          scopeLabel: "Standalone experiment",
          title: `Experiment ${standaloneStrategyName(item)}`,
          subtitle: item.output_dir || "standalone experiment",
          status: item.status || "unknown",
          fields: item.fields || {},
          records: item.records || {},
          sourceArtifacts: Array.isArray(item.source_artifacts) ? item.source_artifacts : [],
          previewPath: firstPreviewableRef(item.source_artifacts),
          warnings: Array.isArray(item.warnings) ? item.warnings : [],
          errors: Array.isArray(item.errors) ? item.errors : []
        });
      });
      return items;
    }

    function strategyKind(name) {
      if (name === "strategy_effectiveness_gates") {
        return "gates";
      }
      if (name === "strategy_lifecycle_state") {
        return "lifecycle";
      }
      if (name === "strategy_experiment") {
        return "experiment";
      }
      return "pipeline";
    }

    function strategyTitle(name) {
      const titles = {
        strategy_benchmark_suite: "Benchmark suite",
        quant_strategy_runs: "Quant strategy runs",
        strategy_evaluation_summary: "Strategy evaluation",
        strategy_experiment: "Pipeline experiment",
        strategy_effectiveness_gates: "Effectiveness gates",
        strategy_lifecycle_state: "Lifecycle state"
      };
      return titles[name] || name || "Strategy artifact";
    }

    function standaloneStrategyName(item) {
      const inputs = item.fields && item.fields.inputs ? item.fields.inputs : {};
      const value = inputs.strategy_name || inputs.strategy_names || item.output_dir;
      return Array.isArray(value) ? value.join(", ") : text(value);
    }

    function strategyMatchesFilters(item) {
      const scope = document.querySelector("#strategy-scope-filter").value;
      const query = document.querySelector("#strategy-search-filter").value.trim().toLowerCase();
      if (scope === "pipeline" && item.group !== "pipeline") {
        return false;
      }
      if (scope === "backtests" && item.group !== "backtests") {
        return false;
      }
      if (scope === "experiments" && item.group !== "experiments") {
        return false;
      }
      if (scope === "gates" && item.kind !== "gates") {
        return false;
      }
      if (scope === "lifecycle" && item.kind !== "lifecycle") {
        return false;
      }
      if (scope === "warnings" && !item.warnings.length && !item.errors.length && !["warning", "degraded", "failed"].includes(normalizeStatus(item.status))) {
        return false;
      }
      if (!query) {
        return true;
      }
      return strategySearchText(item).includes(query);
    }

    function strategySearchText(item) {
      return [
        item.key,
        item.group,
        item.kind,
        item.title,
        item.subtitle,
        item.status,
        JSON.stringify(item.fields || {}),
        JSON.stringify(item.records || {}),
        item.sourceArtifacts.join(" ")
      ].join(" ").toLowerCase();
    }

    function renderStrategyDetail(item) {
      if (!item) {
        document.querySelector("#selected-strategy-status").textContent = "none";
        document.querySelector("#strategy-detail-title").textContent = "Strategy detail";
        document.querySelector("#strategy-detail-badge").className = "badge missing";
        document.querySelector("#strategy-detail-badge").textContent = "missing";
        document.querySelector("#strategy-detail").innerHTML = `<div class="message warning">No strategy output is selected.</div>`;
        document.querySelector("#strategy-preview").innerHTML = `<div class="message warning">No strategy artifact preview is available.</div>`;
        return;
      }
      document.querySelector("#selected-strategy-status").textContent = item.title;
      document.querySelector("#strategy-detail-title").textContent = item.title;
      document.querySelector("#strategy-detail-badge").className = `badge ${normalizeStatus(item.status)}`;
      document.querySelector("#strategy-detail-badge").textContent = label(item.status);
      document.querySelector("#strategy-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>Summary</span>
            <span class="badge ${normalizeStatus(item.status)}">${label(item.status)}</span>
          </h3>
          <div class="run-detail-grid">
            ${strategyDetailTiles(item).join("")}
          </div>
          ${messages(item)}
        </section>
        <section class="section-block">
          <h3 class="subheading">
            <span>Bounded chart</span>
            <span class="badge ${strategyChartCounts(item).length ? "available" : "missing"}">${strategyChartCounts(item).length ? "available" : "missing"}</span>
          </h3>
          ${renderStrategyChart(item)}
        </section>
        ${renderStrategyRecords(item)}
        <section class="section-block">
          <h3 class="subheading">
            <span>Source refs</span>
            <span class="badge ${item.sourceArtifacts.length ? "available" : "missing"}">${item.sourceArtifacts.length} ref${item.sourceArtifacts.length === 1 ? "" : "s"}</span>
          </h3>
          <ul class="source-ref-list">
            ${strategySourceRefs(item).map((ref) => `<li>${sourceRefHtml(ref)}</li>`).join("") || `<li>No source refs recorded.</li>`}
          </ul>
        </section>
        <section class="section-block">
          <h3 class="subheading">
            <span>Limitations</span>
            <span class="badge partial">research only</span>
          </h3>
          <div class="message warning">Strategy output is historical research material, not trading advice.</div>
        </section>`;
      wireArtifactButtons();
      if (item.previewPath) {
        loadArtifactPreview(item.previewPath, "#strategy-preview");
      } else {
        document.querySelector("#strategy-preview").innerHTML = `<div class="message warning">No bounded strategy artifact preview path is available.</div>`;
      }
    }

    function strategyDetailTiles(item) {
      const fields = item.fields || {};
      const tiles = [
        detailTile("Scope", item.scopeLabel),
        detailTile("Status", item.status),
        detailTile("Artifact/output", item.previewPath || item.subtitle),
        detailTile("Warnings", item.warnings.length),
        detailTile("Errors", item.errors.length)
      ];
      if (fields.created_at) {
        tiles.push(detailTile("Created", fields.created_at));
      }
      if (fields.updated_at) {
        tiles.push(detailTile("Updated", fields.updated_at));
      }
      const counts = fields.counts || fields.coverage || fields.lifecycle_counts || fields.gate_coverage || fields.benchmark_coverage || {};
      Object.entries(counts).slice(0, 7).forEach(([key, value]) => {
        tiles.push(detailTile(key, value));
      });
      const metrics = fields.metrics || {};
      Object.entries(metrics).slice(0, 2).forEach(([key, value]) => {
        tiles.push(detailTile(key, compactObject(value)));
      });
      return tiles.slice(0, 12);
    }

    function renderStrategyRecords(item) {
      const sections = Object.entries(item.records || {})
        .filter(([, records]) => Array.isArray(records) && records.length)
        .map(([name, records]) => `
          <section class="section-block">
            <h3 class="subheading">
              <span>${escapeHtml(recordSectionTitle(name))}</span>
              <span class="badge available">${records.length} record${records.length === 1 ? "" : "s"}</span>
            </h3>
            <ul class="stage-list">
              ${records.slice(0, 8).map((record) => `
                <li class="stage-item">
                  <div class="stage-top">
                    <span class="stage-name">${escapeHtml(strategyRecordTitle(record))}</span>
                    ${badge(record.status || record.lifecycle_status || "available")}
                  </div>
                  <div class="run-meta">
                    ${recordMeta(record).map((entry) => `<span>${escapeHtml(entry)}</span>`).join("")}
                  </div>
                </li>`).join("")}
            </ul>
            ${records.length > 8 ? `<div class="message warning">${records.length - 8} record(s) omitted from this UI section.</div>` : ""}
          </section>`);
      return sections.join("");
    }

    function recordSectionTitle(name) {
      const titles = {
        runs: "Quant runs",
        records: "Evaluations",
        candidates: "Candidates",
        gates: "Gates",
        lifecycle: "Lifecycle records",
        benchmarks: "Benchmarks"
      };
      return titles[name] || name;
    }

    function strategyRecordTitle(record) {
      return record.strategy_name
        || record.gate_id
        || record.lifecycle_record_id
        || record.evaluation_id
        || record.benchmark_id
        || record.status
        || "record";
    }

    function recordMeta(record) {
      return Object.entries(record)
        .filter(([, value]) => value === null || ["string", "number", "boolean"].includes(typeof value))
        .filter(([key]) => !["gate_id", "lifecycle_record_id", "evaluation_id", "benchmark_id"].includes(key))
        .slice(0, 8)
        .map(([key, value]) => `${key}: ${text(value)}`);
    }

    function renderStrategyChart(item) {
      const counts = strategyChartCounts(item);
      if (!counts.length) {
        return `<div class="strategy-chart"><div class="message warning">No bounded chart data is available for this output.</div></div>`;
      }
      const max = Math.max(...counts.map((entry) => Math.abs(entry.value)), 1);
      const width = 520;
      const height = 132;
      const gap = 10;
      const barWidth = Math.max(20, (width - gap * (counts.length + 1)) / counts.length);
      const bars = counts.map((entry, index) => {
        const barHeight = Math.max(4, (Math.abs(entry.value) / max) * 82);
        const x = gap + index * (barWidth + gap);
        const y = 92 - barHeight;
        return `
          <g>
            <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="3" fill="${chartColor(entry.label)}"></rect>
            <text x="${x + barWidth / 2}" y="${y - 6}" text-anchor="middle" font-size="11" fill="#202124">${escapeHtml(text(entry.value))}</text>
            <text x="${x + barWidth / 2}" y="118" text-anchor="middle" font-size="10" fill="#68635a">${escapeHtml(shortLabel(entry.label))}</text>
          </g>`;
      }).join("");
      return `
        <div class="strategy-chart">
          <div class="chart-label">${escapeHtml(chartTitle(item))}</div>
          <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(chartTitle(item))}">
            <line x1="0" y1="92" x2="${width}" y2="92" stroke="#dedbd2"></line>
            ${bars}
          </svg>
        </div>`;
    }

    function strategyChartCounts(item) {
      if (item.records && Array.isArray(item.records.gates) && item.records.gates.length) {
        return countBy(item.records.gates, (record) => record.status || "unknown");
      }
      if (item.records && Array.isArray(item.records.lifecycle) && item.records.lifecycle.length) {
        return countBy(item.records.lifecycle, (record) => record.lifecycle_status || "unknown");
      }
      if (item.records && Array.isArray(item.records.candidates) && item.records.candidates.length) {
        return countBy(item.records.candidates, (record) => record.status || "unknown");
      }
      const fields = item.fields || {};
      const source = fields.gate_coverage || fields.lifecycle_counts || fields.coverage || fields.counts || fields.benchmark_coverage || {};
      return Object.entries(source)
        .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
        .slice(0, 8)
        .map(([labelText, value]) => ({ label: labelText, value }));
    }

    function countBy(records, keyFn) {
      const counts = {};
      records.forEach((record) => {
        const key = keyFn(record);
        counts[key] = (counts[key] || 0) + 1;
      });
      return Object.entries(counts).map(([labelText, value]) => ({ label: labelText, value }));
    }

    function chartTitle(item) {
      if (item.kind === "gates") {
        return "Gate count by status";
      }
      if (item.kind === "lifecycle") {
        return "Lifecycle count by status";
      }
      return "Bounded count summary";
    }

    function chartColor(labelText) {
      const value = String(labelText).toLowerCase();
      if (["available", "ok", "succeeded", "effective", "active_candidate"].some((item) => value.includes(item))) {
        return "#0f766e";
      }
      if (["failed", "degraded", "rejected", "retired"].some((item) => value.includes(item))) {
        return "#b42318";
      }
      return "#a16207";
    }

    function shortLabel(value) {
      const textValue = String(value || "n/a").replaceAll("_", " ");
      return textValue.length > 14 ? `${textValue.slice(0, 12)}..` : textValue;
    }

    function strategySourceRefs(item) {
      const refs = [item.previewPath, ...item.sourceArtifacts].filter(Boolean);
      return [...new Set(refs)].slice(0, 12);
    }

    function sourceRefHtml(ref) {
      if (isPreviewableRef(ref)) {
        return `<button class="link-button" type="button" data-artifact-path="${escapeHtml(ref)}" data-preview-target="#strategy-preview">${escapeHtml(ref)}</button>`;
      }
      return escapeHtml(ref);
    }

    function firstPreviewableRef(refs) {
      return (Array.isArray(refs) ? refs : []).find(isPreviewableRef) || "";
    }

    function isPreviewableRef(ref) {
      const value = String(ref || "");
      return value.startsWith("runs/") || value.startsWith("data/");
    }

    function compactObject(value) {
      if (value === null || value === undefined) {
        return "n/a";
      }
      if (typeof value !== "object") {
        return value;
      }
      return Object.entries(value)
        .slice(0, 4)
        .map(([key, item]) => `${key}: ${text(item)}`)
        .join(", ");
    }

    async function loadMonitor() {
      monitorLoaded = true;
      document.querySelector("#monitor-status").textContent = "Loading";
      try {
        monitorPayload = await fetchJson(endpoints.monitor);
        renderMonitor(monitorPayload);
      } catch (error) {
        renderMonitorFailure(error);
      }
      await refreshMonitorJobs();
    }

    function renderMonitor(payload) {
      const health = payload.health || {};
      const healthFields = health.fields || {};
      document.querySelector("#monitor-status").textContent = label(payload.status);
      const healthBadge = document.querySelector("#monitor-health-badge");
      healthBadge.className = `badge ${normalizeStatus(health.status || payload.status)}`;
      healthBadge.textContent = label(health.status || payload.status);
      document.querySelector("#monitor-summary-grid").innerHTML = [
        detailTile("Updated", healthFields.updated_at),
        detailTile("Latest cycle", healthFields.latest_cycle_id),
        detailTile("Latest status", healthFields.latest_cycle_status),
        detailTile("Cycle count", healthFields.cycle_count),
        detailTile("Failed cycles", healthFields.failed_cycle_count),
        detailTile("Latest run", healthFields.latest_run_id),
        detailTile("Cooldown records", healthFields.cooldown_records),
        detailTile("Monitor output", payload.monitor_output_dir)
      ].join("");
      renderMonitorAlertCounts(payload);
      renderMonitorCycles(payload);
      renderMonitorAlertSample(payload);
    }

    function renderMonitorFailure(error) {
      document.querySelector("#monitor-status").textContent = "Failed";
      document.querySelector("#monitor-health-badge").className = "badge failed";
      document.querySelector("#monitor-health-badge").textContent = "failed";
      document.querySelector("#monitor-summary-grid").innerHTML = detailTile("Error", error.message);
      document.querySelector("#monitor-alert-badge").className = "badge failed";
      document.querySelector("#monitor-alert-badge").textContent = "failed";
      document.querySelector("#monitor-alert-counts").innerHTML = "";
      document.querySelector("#monitor-cycle-count").className = "badge failed";
      document.querySelector("#monitor-cycle-count").textContent = "failed";
      document.querySelector("#monitor-cycle-badge").className = "badge failed";
      document.querySelector("#monitor-cycle-badge").textContent = "failed";
      document.querySelector("#monitor-cycle-list").innerHTML = `<li class="message error">${escapeHtml(error.message)}</li>`;
      document.querySelector("#monitor-alert-sample-badge").className = "badge failed";
      document.querySelector("#monitor-alert-sample-badge").textContent = "failed";
      document.querySelector("#monitor-alert-sample").innerHTML = "";
    }

    function renderMonitorAlertCounts(payload) {
      const healthCounts = get("health.fields.alert_counts", payload) || {};
      const archiveCounts = get("alert_archive.fields.counts", payload) || {};
      const counts = Object.keys(healthCounts).length ? healthCounts : archiveCounts;
      const order = ["records", "emitted", "suppressed_duplicate", "suppressed_cooldown", "suppressed_no_alert", "skipped"];
      const badgeNode = document.querySelector("#monitor-alert-badge");
      badgeNode.className = `badge ${Object.values(counts).some((value) => Number(value) > 0) ? "available" : normalizeStatus(get("alert_archive.status", payload))}`;
      badgeNode.textContent = `${text(counts.records || 0)} records`;
      document.querySelector("#monitor-alert-counts").innerHTML = order
        .map((key) => detailTile(key, counts[key] || 0))
        .join("");
    }

    function renderMonitorCycles(payload) {
      const cyclesPayload = payload.cycles || {};
      const cycles = Array.isArray(cyclesPayload.cycles) ? cyclesPayload.cycles : [];
      const total = Number(cyclesPayload.cycle_count || cycles.length);
      const count = document.querySelector("#monitor-cycle-count");
      count.className = `badge ${cycles.length ? normalizeStatus(cyclesPayload.status) : "missing"}`;
      count.textContent = `${total} cycle${total === 1 ? "" : "s"}`;
      const badgeNode = document.querySelector("#monitor-cycle-badge");
      badgeNode.className = `badge ${cycles.length ? normalizeStatus(cyclesPayload.status) : "missing"}`;
      badgeNode.textContent = `${cycles.length} shown`;
      if (!cycles.length) {
        document.querySelector("#monitor-cycle-list").innerHTML = messages(cyclesPayload) || `<li class="message warning">No monitor cycles are recorded.</li>`;
        return;
      }
      document.querySelector("#monitor-cycle-list").innerHTML = cycles.map((cycle) => {
        const counts = cycle.alert_archive && cycle.alert_archive.counts ? cycle.alert_archive.counts : {};
        return `
          <li class="stage-item">
            <div class="stage-top">
              <span class="stage-name">${escapeHtml(text(cycle.cycle_id))}</span>
              ${badge(cycle.status)}
            </div>
            <div class="run-meta">
              <span>Mode: ${escapeHtml(text(cycle.cycle_mode))}</span>
              <span>Started: ${escapeHtml(text(cycle.started_at))}</span>
              <span>Finished: ${escapeHtml(text(cycle.finished_at))}</span>
              <span>Run: ${escapeHtml(text(cycle.run_id))}</span>
              <span>Alerts: ${escapeHtml(text(counts.emitted || 0))}</span>
              <span>Warnings: ${escapeHtml(text(cycle.warning_count || 0))}</span>
              <span>Errors: ${escapeHtml(text(cycle.error_count || 0))}</span>
            </div>
            ${cycle.cycle_manifest ? `<div class="artifact-actions"><button class="link-button" type="button" data-artifact-path="${escapeHtml(cycle.cycle_manifest)}">Open cycle manifest</button></div>` : ""}
          </li>`;
      }).join("");
      wireArtifactButtons();
    }

    function renderMonitorAlertSample(payload) {
      const archive = payload.alert_archive || {};
      const fields = archive.fields || {};
      const records = Array.isArray(fields.sample_records) ? fields.sample_records : [];
      const badgeNode = document.querySelector("#monitor-alert-sample-badge");
      badgeNode.className = `badge ${records.length ? normalizeStatus(archive.status) : "missing"}`;
      badgeNode.textContent = `${records.length} sample${records.length === 1 ? "" : "s"}`;
      if (!records.length) {
        document.querySelector("#monitor-alert-sample").innerHTML = messages(archive) || `<li class="message warning">No alert archive sample is available.</li>`;
        return;
      }
      document.querySelector("#monitor-alert-sample").innerHTML = records.slice(0, 8).map((record) => `
        <li class="stage-item">
          <div class="stage-top">
            <span class="stage-name">${escapeHtml(text(record.record_id || record.decision_id || record.symbol || "alert"))}</span>
            ${badge(record.status)}
          </div>
          <div class="run-meta">
            <span>Created: ${escapeHtml(text(record.created_at))}</span>
            <span>Symbol: ${escapeHtml(text(record.symbol))}</span>
            <span>Timeframe: ${escapeHtml(text(record.timeframe))}</span>
            <span>Priority: ${escapeHtml(text(record.priority))}</span>
            <span>Attention: ${escapeHtml(text(record.attention_decision))}</span>
            <span>Source refs: ${escapeHtml(text(record.source_artifact_count))}</span>
          </div>
        </li>`).join("");
    }

    async function loadWorkbench() {
      workbenchLoaded = true;
      document.querySelector("#workbench-status").textContent = "Loading";
      try {
        workbenchPayload = await fetchJson(endpoints.workbench);
        renderWorkbench(workbenchPayload);
      } catch (error) {
        renderWorkbenchFailure(error);
      }
    }

    function renderWorkbench(payload) {
      document.querySelector("#workbench-status").textContent = label(payload.status);
      document.querySelector("#workbench-generated").textContent = text(payload.generated_at);
      const badgeNode = document.querySelector("#workbench-summary-badge");
      badgeNode.className = `badge ${normalizeStatus(payload.status)}`;
      badgeNode.textContent = label(payload.status);
      const selection = payload.source_selection || {};
      const indexOutputs = payload.index_outputs || {};
      document.querySelector("#workbench-summary-grid").innerHTML = [
        detailTile("Summary", payload.summary_ref),
        detailTile("Generated", payload.generated_at),
        detailTile("Run", selection.run_id),
        detailTile("Run dir", selection.run_dir),
        detailTile("Selection", selection.status || selection.mode),
        detailTile("Index markdown", indexOutputs.markdown),
        detailTile("Index html", indexOutputs.html),
        detailTile("Codex input", get("codex_boundary.codex_input_by_default", payload))
      ].join("");
      document.querySelector("#workbench-messages").innerHTML = messages(payload);
      renderWorkbenchSections(payload.sections || {});
      renderWorkbenchSources(payload);
    }

    function renderWorkbenchFailure(error) {
      document.querySelector("#workbench-status").textContent = "Failed";
      document.querySelector("#workbench-generated").textContent = "n/a";
      document.querySelector("#workbench-summary-badge").className = "badge failed";
      document.querySelector("#workbench-summary-badge").textContent = "failed";
      document.querySelector("#workbench-summary-grid").innerHTML = detailTile("Error", error.message);
      document.querySelector("#workbench-messages").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#workbench-section-count").className = "badge failed";
      document.querySelector("#workbench-section-count").textContent = "failed";
      document.querySelector("#workbench-section-list").innerHTML = "";
      document.querySelector("#workbench-source-count").className = "badge failed";
      document.querySelector("#workbench-source-count").textContent = "failed";
      document.querySelector("#workbench-source-list").innerHTML = "";
    }

    function renderWorkbenchSections(sections) {
      const entries = Object.entries(sections);
      const count = document.querySelector("#workbench-section-count");
      count.className = `badge ${entries.length ? "available" : "missing"}`;
      count.textContent = `${entries.length} section${entries.length === 1 ? "" : "s"}`;
      if (!entries.length) {
        document.querySelector("#workbench-section-list").innerHTML = `<div class="message warning">No workbench state sections are available.</div>`;
        return;
      }
      document.querySelector("#workbench-section-list").innerHTML = entries.map(([name, section]) => {
        const fields = section.fields || {};
        const sourceCount = Array.isArray(section.source_artifacts) ? section.source_artifacts.length : 0;
        const fieldRows = Object.entries(fields).slice(0, 8).map(([key, value]) => detailTile(key, value)).join("");
        return `
          <section class="section-block">
            <h3 class="subheading">
              <span>${escapeHtml(workbenchSectionTitle(name))}</span>
              ${badge(section.status)}
            </h3>
            <div class="run-detail-grid">${fieldRows || detailTile("Fields", "n/a")}</div>
            <div class="timeline-meta">Source refs: ${escapeHtml(text(sourceCount))}</div>
            ${messages(section)}
          </section>`;
      }).join("");
    }

    function renderWorkbenchSources(payload) {
      const refs = Array.isArray(payload.source_artifacts) ? payload.source_artifacts : [];
      const count = document.querySelector("#workbench-source-count");
      count.className = `badge ${refs.length ? "available" : "missing"}`;
      count.textContent = `${refs.length} ref${refs.length === 1 ? "" : "s"}`;
      if (!refs.length) {
        document.querySelector("#workbench-source-list").innerHTML = `<div class="message warning">No workbench source refs are available.</div>`;
        return;
      }
      document.querySelector("#workbench-source-list").innerHTML = refs.slice(0, 30).map((ref) => {
        if (isPreviewableRef(ref)) {
          return `<button class="link-button" type="button" data-workbench-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`;
        }
        return `<span class="badge missing">${escapeHtml(ref)}</span>`;
      }).join("");
      document.querySelectorAll("[data-workbench-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.workbenchPreviewPath, "#workbench-preview"));
      });
    }

    function workbenchSectionTitle(name) {
      const titles = {
        latest_run: "Latest run",
        decision_state: "Decision and watch",
        alert_state: "Alerts",
        monitor_state: "Monitor",
        outcome_state: "Outcomes",
        strategy_state: "Strategy",
        product_validation_state: "Product validation",
        data_quality_state: "Data quality"
      };
      return titles[name] || name;
    }

    async function loadDecisionRisk() {
      decisionRiskLoaded = true;
      document.querySelector("#decision-risk-status").textContent = "Loading";
      try {
        decisionRunsPayload = await fetchJson(endpoints.runs);
        renderDecisionRunList();
        const runs = Array.isArray(decisionRunsPayload.runs) ? decisionRunsPayload.runs : [];
        if (runs.length) {
          await selectDecisionRun(runs[0].run_id);
        } else {
          const payload = await fetchJson(endpoints.decisionRisk);
          renderDecisionRisk(payload);
        }
      } catch (error) {
        renderDecisionRiskFailure(error);
      }
    }

    function renderDecisionRunList() {
      const runs = Array.isArray(decisionRunsPayload && decisionRunsPayload.runs) ? decisionRunsPayload.runs : [];
      const count = document.querySelector("#decision-run-count");
      count.className = `badge ${runs.length ? "available" : "missing"}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      if (!runs.length) {
        document.querySelector("#decision-run-list").innerHTML = messages(decisionRunsPayload || {}) || `<div class="message warning">No runs are recorded in the local run index.</div>`;
        return;
      }
      document.querySelector("#decision-run-list").innerHTML = runs.map((run) => `
        <button class="run-row ${run.run_id === selectedDecisionRunId ? "selected" : ""}" type="button" data-decision-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      document.querySelectorAll("[data-decision-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectDecisionRun(button.dataset.decisionRunId));
      });
    }

    async function selectDecisionRun(runId) {
      if (!runId) {
        return;
      }
      selectedDecisionRunId = runId;
      selectedDecisionArtifactKey = null;
      document.querySelector("#decision-risk-selected-run").textContent = runId;
      document.querySelector("#decision-risk-status").textContent = "Loading";
      renderDecisionRunList();
      try {
        decisionRiskPayload = await fetchJson(`${endpoints.decisionRisk}?run_id=${encodeURIComponent(runId)}`);
        renderDecisionRisk(decisionRiskPayload);
      } catch (error) {
        renderDecisionRiskFailure(error);
      }
    }

    function renderDecisionRisk(payload) {
      const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
      const selectedRun = payload.selected_run || {};
      const selectedFields = selectedRun.fields || {};
      document.querySelector("#decision-risk-status").textContent = label(payload.status);
      document.querySelector("#decision-risk-selected-run").textContent = text(selectedFields.run_id || selectedDecisionRunId);
      const count = document.querySelector("#decision-artifact-count");
      count.className = `badge ${artifacts.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#decision-artifact-list").innerHTML = messages(payload) || `<div class="message warning">No decision or risk artifacts are available for the selected run.</div>`;
        document.querySelector("#decision-artifact-detail").innerHTML = "";
        return;
      }
      if (!selectedDecisionArtifactKey || !artifacts.some((artifact) => artifact.name === selectedDecisionArtifactKey)) {
        selectedDecisionArtifactKey = artifacts[0].name;
      }
      document.querySelector("#decision-artifact-list").innerHTML = artifacts.map((artifact) => {
        const fields = artifact.fields || {};
        return `
          <button class="store-card ${artifact.name === selectedDecisionArtifactKey ? "selected" : ""}" type="button" data-decision-artifact-key="${escapeHtml(artifact.name)}">
            <span class="store-title-line">
              <span class="store-title">${escapeHtml(text(fields.title || artifact.name))}</span>
              ${badge(artifact.status)}
            </span>
            <span class="store-metrics">
              <span>Records: ${escapeHtml(text(fields.record_count))}</span>
              <span>Warnings: ${escapeHtml(text(fields.warning_count))}</span>
              <span>Errors: ${escapeHtml(text(fields.error_count))}</span>
            </span>
            <span class="timeline-meta">${escapeHtml(text(fields.preview_path || fields.artifact))}</span>
          </button>`;
      }).join("");
      document.querySelectorAll("[data-decision-artifact-key]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedDecisionArtifactKey = button.dataset.decisionArtifactKey;
          renderDecisionRisk(payload);
        });
      });
      renderDecisionArtifactDetail(artifacts.find((artifact) => artifact.name === selectedDecisionArtifactKey));
    }

    function renderDecisionArtifactDetail(artifact) {
      if (!artifact) {
        document.querySelector("#decision-artifact-detail").innerHTML = `<div class="message warning">Decision artifact detail is not available.</div>`;
        return;
      }
      const fields = artifact.fields || {};
      const refs = Array.isArray(artifact.source_artifacts) ? artifact.source_artifacts : [];
      document.querySelector("#decision-artifact-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>${escapeHtml(text(fields.title || artifact.name))}</span>
            ${badge(artifact.status)}
          </h3>
          <div class="run-detail-grid">
            ${detailTile("Artifact", fields.artifact)}
            ${detailTile("Type", fields.artifact_type)}
            ${detailTile("Artifact status", fields.artifact_status)}
            ${detailTile("Records", fields.record_count)}
            ${detailTile("Warnings", fields.warning_count)}
            ${detailTile("Errors", fields.error_count)}
          </div>
          ${messages(artifact)}
          <div class="artifact-actions">
            ${refs.filter(isPreviewableRef).map((ref) => `<button class="link-button" type="button" data-decision-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("") || `<span class="badge missing">no previewable refs</span>`}
          </div>
        </section>`;
      document.querySelectorAll("[data-decision-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.decisionPreviewPath, "#decision-preview"));
      });
      if (isPreviewableRef(fields.preview_path)) {
        loadArtifactPreview(fields.preview_path, "#decision-preview");
      }
    }

    function renderDecisionRiskFailure(error) {
      document.querySelector("#decision-risk-status").textContent = "Failed";
      document.querySelector("#decision-artifact-count").className = "badge failed";
      document.querySelector("#decision-artifact-count").textContent = "failed";
      document.querySelector("#decision-artifact-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#decision-artifact-detail").innerHTML = "";
    }

    async function loadEventAlert() {
      eventAlertLoaded = true;
      document.querySelector("#event-alert-status").textContent = "Loading";
      try {
        eventRunsPayload = await fetchJson(endpoints.runs);
        renderEventRunList();
        const runs = Array.isArray(eventRunsPayload.runs) ? eventRunsPayload.runs : [];
        if (runs.length) {
          await selectEventRun(runs[0].run_id);
        } else {
          const payload = await fetchJson(endpoints.eventAlert);
          renderEventAlert(payload);
        }
      } catch (error) {
        renderEventAlertFailure(error);
      }
    }

    function renderEventRunList() {
      const runs = Array.isArray(eventRunsPayload && eventRunsPayload.runs) ? eventRunsPayload.runs : [];
      const count = document.querySelector("#event-run-count");
      count.className = `badge ${runs.length ? "available" : "missing"}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      if (!runs.length) {
        document.querySelector("#event-run-list").innerHTML = messages(eventRunsPayload || {}) || `<div class="message warning">No runs are recorded in the local run index.</div>`;
        return;
      }
      document.querySelector("#event-run-list").innerHTML = runs.map((run) => `
        <button class="run-row ${run.run_id === selectedEventRunId ? "selected" : ""}" type="button" data-event-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      document.querySelectorAll("[data-event-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectEventRun(button.dataset.eventRunId));
      });
    }

    async function selectEventRun(runId) {
      if (!runId) {
        return;
      }
      selectedEventRunId = runId;
      selectedEventArtifactKey = null;
      document.querySelector("#event-alert-selected-run").textContent = runId;
      document.querySelector("#event-alert-status").textContent = "Loading";
      renderEventRunList();
      try {
        eventAlertPayload = await fetchJson(`${endpoints.eventAlert}?run_id=${encodeURIComponent(runId)}`);
        renderEventAlert(eventAlertPayload);
      } catch (error) {
        renderEventAlertFailure(error);
      }
    }

    function renderEventAlert(payload) {
      const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
      const selectedRun = payload.selected_run || {};
      const selectedFields = selectedRun.fields || {};
      document.querySelector("#event-alert-status").textContent = label(payload.status);
      document.querySelector("#event-alert-selected-run").textContent = text(selectedFields.run_id || selectedEventRunId);
      const count = document.querySelector("#event-artifact-count");
      count.className = `badge ${artifacts.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#event-artifact-list").innerHTML = messages(payload) || `<div class="message warning">No event or alert artifacts are available for the selected run.</div>`;
        document.querySelector("#event-artifact-detail").innerHTML = "";
        return;
      }
      if (!selectedEventArtifactKey || !artifacts.some((artifact) => artifact.name === selectedEventArtifactKey)) {
        selectedEventArtifactKey = artifacts[0].name;
      }
      document.querySelector("#event-artifact-list").innerHTML = artifacts.map((artifact) => {
        const fields = artifact.fields || {};
        return `
          <button class="store-card ${artifact.name === selectedEventArtifactKey ? "selected" : ""}" type="button" data-event-artifact-key="${escapeHtml(artifact.name)}">
            <span class="store-title-line">
              <span class="store-title">${escapeHtml(text(fields.title || artifact.name))}</span>
              ${badge(artifact.status)}
            </span>
            <span class="store-metrics">
              <span>Records: ${escapeHtml(text(fields.record_count))}</span>
              <span>Warnings: ${escapeHtml(text(fields.warning_count))}</span>
              <span>Errors: ${escapeHtml(text(fields.error_count))}</span>
            </span>
            <span class="timeline-meta">${escapeHtml(text(fields.preview_path || fields.artifact))}</span>
          </button>`;
      }).join("");
      document.querySelectorAll("[data-event-artifact-key]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedEventArtifactKey = button.dataset.eventArtifactKey;
          renderEventAlert(payload);
        });
      });
      renderEventArtifactDetail(artifacts.find((artifact) => artifact.name === selectedEventArtifactKey));
    }

    function renderEventArtifactDetail(artifact) {
      if (!artifact) {
        document.querySelector("#event-artifact-detail").innerHTML = `<div class="message warning">Event artifact detail is not available.</div>`;
        return;
      }
      const fields = artifact.fields || {};
      const refs = Array.isArray(artifact.source_artifacts) ? artifact.source_artifacts : [];
      document.querySelector("#event-artifact-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>${escapeHtml(text(fields.title || artifact.name))}</span>
            ${badge(artifact.status)}
          </h3>
          <div class="run-detail-grid">
            ${detailTile("Artifact", fields.artifact)}
            ${detailTile("Type", fields.artifact_type)}
            ${detailTile("Artifact status", fields.artifact_status)}
            ${detailTile("Records", fields.record_count)}
            ${detailTile("Warnings", fields.warning_count)}
            ${detailTile("Errors", fields.error_count)}
          </div>
          ${messages(artifact)}
          <div class="artifact-actions">
            ${refs.filter(isPreviewableRef).map((ref) => `<button class="link-button" type="button" data-event-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("") || `<span class="badge missing">no previewable refs</span>`}
          </div>
        </section>`;
      document.querySelectorAll("[data-event-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.eventPreviewPath, "#event-preview"));
      });
      if (isPreviewableRef(fields.preview_path)) {
        loadArtifactPreview(fields.preview_path, "#event-preview");
      }
    }

    function renderEventAlertFailure(error) {
      document.querySelector("#event-alert-status").textContent = "Failed";
      document.querySelector("#event-artifact-count").className = "badge failed";
      document.querySelector("#event-artifact-count").textContent = "failed";
      document.querySelector("#event-artifact-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#event-artifact-detail").innerHTML = "";
    }

    async function loadTextIntelligence() {
      textIntelligenceLoaded = true;
      document.querySelector("#text-intelligence-status").textContent = "Loading";
      try {
        textRunsPayload = await fetchJson(endpoints.runs);
        renderTextRunList();
        const runs = Array.isArray(textRunsPayload.runs) ? textRunsPayload.runs : [];
        if (runs.length) {
          await selectTextRun(runs[0].run_id);
        } else {
          const payload = await fetchJson(endpoints.textIntelligence);
          renderTextIntelligence(payload);
        }
        await refreshTextJobs();
      } catch (error) {
        renderTextIntelligenceFailure(error);
      }
    }

    function renderTextRunList() {
      const runs = Array.isArray(textRunsPayload && textRunsPayload.runs) ? textRunsPayload.runs : [];
      const count = document.querySelector("#text-run-count");
      count.className = `badge ${runs.length ? "available" : "missing"}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      if (!runs.length) {
        document.querySelector("#text-run-list").innerHTML = messages(textRunsPayload || {}) || `<div class="message warning">No runs are recorded in the local run index.</div>`;
        return;
      }
      document.querySelector("#text-run-list").innerHTML = runs.map((run) => `
        <button class="run-row ${run.run_id === selectedTextRunId ? "selected" : ""}" type="button" data-text-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      document.querySelectorAll("[data-text-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectTextRun(button.dataset.textRunId));
      });
    }

    async function selectTextRun(runId) {
      if (!runId) {
        return;
      }
      selectedTextRunId = runId;
      selectedTextArtifactKey = null;
      document.querySelector("#text-intelligence-selected-run").textContent = runId;
      document.querySelector("#text-intelligence-status").textContent = "Loading";
      renderTextRunList();
      try {
        textIntelligencePayload = await fetchJson(`${endpoints.textIntelligence}?run_id=${encodeURIComponent(runId)}`);
        renderTextIntelligence(textIntelligencePayload);
      } catch (error) {
        renderTextIntelligenceFailure(error);
      }
    }

    function renderTextIntelligence(payload) {
      const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
      const selectedRun = payload.selected_run || {};
      const selectedFields = selectedRun.fields || {};
      document.querySelector("#text-intelligence-status").textContent = label(payload.status);
      document.querySelector("#text-intelligence-selected-run").textContent = text(selectedFields.run_id || selectedTextRunId);
      const count = document.querySelector("#text-artifact-count");
      count.className = `badge ${artifacts.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#text-artifact-list").innerHTML = messages(payload) || `<div class="message warning">No text intelligence artifacts are available for the selected run.</div>`;
        document.querySelector("#text-artifact-detail").innerHTML = "";
        return;
      }
      if (!selectedTextArtifactKey || !artifacts.some((artifact) => artifact.name === selectedTextArtifactKey)) {
        selectedTextArtifactKey = artifacts[0].name;
      }
      document.querySelector("#text-artifact-list").innerHTML = artifacts.map((artifact) => {
        const fields = artifact.fields || {};
        return `
          <button class="store-card ${artifact.name === selectedTextArtifactKey ? "selected" : ""}" type="button" data-text-artifact-key="${escapeHtml(artifact.name)}">
            <span class="store-title-line">
              <span class="store-title">${escapeHtml(text(fields.title || artifact.name))}</span>
              ${badge(artifact.status)}
            </span>
            <span class="store-metrics">
              <span>Records: ${escapeHtml(text(fields.record_count))}</span>
              <span>Warnings: ${escapeHtml(text(fields.warning_count))}</span>
              <span>Errors: ${escapeHtml(text(fields.error_count))}</span>
            </span>
            <span class="timeline-meta">${escapeHtml(text(fields.preview_path || fields.artifact))}</span>
          </button>`;
      }).join("");
      document.querySelectorAll("[data-text-artifact-key]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedTextArtifactKey = button.dataset.textArtifactKey;
          renderTextIntelligence(payload);
        });
      });
      renderTextArtifactDetail(artifacts.find((artifact) => artifact.name === selectedTextArtifactKey));
    }

    function renderTextArtifactDetail(artifact) {
      if (!artifact) {
        document.querySelector("#text-artifact-detail").innerHTML = `<div class="message warning">Text artifact detail is not available.</div>`;
        return;
      }
      const fields = artifact.fields || {};
      const refs = Array.isArray(artifact.source_artifacts) ? artifact.source_artifacts : [];
      document.querySelector("#text-artifact-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>${escapeHtml(text(fields.title || artifact.name))}</span>
            ${badge(artifact.status)}
          </h3>
          <div class="run-detail-grid">
            ${detailTile("Artifact", fields.artifact)}
            ${detailTile("Type", fields.artifact_type)}
            ${detailTile("Artifact status", fields.artifact_status)}
            ${detailTile("Records", fields.record_count)}
            ${detailTile("Warnings", fields.warning_count)}
            ${detailTile("Errors", fields.error_count)}
          </div>
          ${messages(artifact)}
          <div class="artifact-actions">
            ${refs.filter(isPreviewableRef).map((ref) => `<button class="link-button" type="button" data-text-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("") || `<span class="badge missing">no previewable refs</span>`}
          </div>
        </section>`;
      document.querySelectorAll("[data-text-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.textPreviewPath, "#text-preview"));
      });
      if (isPreviewableRef(fields.preview_path)) {
        loadArtifactPreview(fields.preview_path, "#text-preview");
      }
    }

    async function refreshTextJobs() {
      try {
        textJobsPayload = await fetchJson(endpoints.jobs);
        renderTextJobs(textJobsPayload);
      } catch (error) {
        document.querySelector("#text-job-count").className = "badge failed";
        document.querySelector("#text-job-count").textContent = "failed";
        document.querySelector("#text-job-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    function renderTextJobs(payload) {
      const jobs = (Array.isArray(payload.jobs) ? payload.jobs : [])
        .filter((job) => ["text_models_prepare", "text_intel"].includes(String(job.intent || "")));
      const count = document.querySelector("#text-job-count");
      count.className = `badge ${jobs.length ? "available" : "missing"}`;
      count.textContent = `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;
      if (!jobs.length) {
        document.querySelector("#text-job-list").innerHTML = `<div class="message">No text intelligence jobs are recorded yet.</div>`;
        return;
      }
      document.querySelector("#text-job-list").innerHTML = jobs.map((job) => `
        <button class="job-row" type="button" data-text-job-id="${escapeHtml(job.job_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(jobTitle(job.intent))}</span>
            ${badge(job.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(job.created_at))}</span>
            <span>Exit: ${escapeHtml(text(job.exit_code))}</span>
          </span>
        </button>`).join("");
      document.querySelectorAll("[data-text-job-id]").forEach((button) => {
        button.addEventListener("click", () => selectTextJob(button.dataset.textJobId));
      });
      if (!document.querySelector("#text-job-result .preview-heading")) {
        renderTextJobResult(jobs[0]);
      }
    }

    async function selectTextJob(jobId) {
      if (!jobId) {
        return;
      }
      document.querySelector("#text-command-status").className = "badge partial";
      document.querySelector("#text-command-status").textContent = "loading";
      try {
        const job = await fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
        document.querySelector("#text-command-status").className = `badge ${normalizeStatus(job.status)}`;
        document.querySelector("#text-command-status").textContent = label(job.status);
        renderTextJobResult(job);
      } catch (error) {
        renderTextCommandMessage("failed", error.message);
      }
    }

    async function startTextJob(intent) {
      const request = textCommandJobRequest(intent);
      if (!request) {
        return;
      }
      document.querySelector("#text-command-status").className = "badge partial";
      document.querySelector("#text-command-status").textContent = "starting";
      try {
        const job = await postJson(endpoints.jobs, request);
        document.querySelector("#text-command-status").className = `badge ${normalizeStatus(job.status)}`;
        document.querySelector("#text-command-status").textContent = label(job.status);
        renderTextJobResult(job);
        await refreshTextJobs();
      } catch (error) {
        renderTextCommandMessage("failed", error.message);
      }
    }

    function textCommandJobRequest(intent) {
      const params = {};
      if (intent === "text_models_prepare") {
        const outputDir = optionalInputValue("#text-output-dir");
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      if (intent === "text_intel") {
        const inputPath = optionalInputValue("#text-input-path");
        const outputDir = optionalInputValue("#text-output-dir");
        if (inputPath) {
          params.input_path = inputPath;
        }
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      renderTextCommandMessage("unsupported", `unsupported text job intent: ${intent || "missing"}`);
      return null;
    }

    function renderTextJobResult(job) {
      const refs = commandPreviewRefs(job);
      document.querySelector("#text-job-result").innerHTML = `
        <div class="preview-heading">
          <div class="preview-path">${escapeHtml(jobTitle(job.intent))}</div>
          ${badge(job.status)}
        </div>
        <div class="run-detail-grid">
          ${detailTile("Job", job.job_id)}
          ${detailTile("Intent", job.intent)}
          ${detailTile("Kind", job.kind)}
          ${detailTile("Created", job.created_at)}
          ${detailTile("Finished", job.finished_at)}
          ${detailTile("Exit", job.exit_code)}
        </div>
        ${messages(job)}
        <div class="artifact-actions">
          ${refs.length ? refs.map((item) => `<button class="link-button" type="button" data-text-preview-path="${escapeHtml(item.path)}">${escapeHtml(item.label)}</button>`).join("") : `<span class="badge missing">no result refs</span>`}
        </div>`;
      document.querySelectorAll("#text-job-result [data-text-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.textPreviewPath, "#text-preview"));
      });
    }

    function renderTextCommandMessage(status, message) {
      document.querySelector("#text-command-status").className = `badge ${normalizeStatus(status)}`;
      document.querySelector("#text-command-status").textContent = label(status);
      document.querySelector("#text-job-result").innerHTML = `<div class="message ${normalizeStatus(status) === "failed" ? "error" : "warning"}">${escapeHtml(message)}</div>`;
    }

    function renderTextIntelligenceFailure(error) {
      document.querySelector("#text-intelligence-status").textContent = "Failed";
      document.querySelector("#text-artifact-count").className = "badge failed";
      document.querySelector("#text-artifact-count").textContent = "failed";
      document.querySelector("#text-artifact-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#text-artifact-detail").innerHTML = "";
    }

    async function loadOutcomes() {
      outcomesLoaded = true;
      document.querySelector("#outcome-status").textContent = "Loading";
      try {
        outcomeRunsPayload = await fetchJson(endpoints.runs);
        renderOutcomeRunList();
        const runs = Array.isArray(outcomeRunsPayload.runs) ? outcomeRunsPayload.runs : [];
        if (runs.length) {
          await selectOutcomeRun(runs[0].run_id);
        } else {
          const payload = await fetchJson(endpoints.outcomes);
          renderOutcomes(payload);
        }
      } catch (error) {
        renderOutcomesFailure(error);
      }
    }

    function renderOutcomeRunList() {
      const runs = Array.isArray(outcomeRunsPayload && outcomeRunsPayload.runs) ? outcomeRunsPayload.runs : [];
      const count = document.querySelector("#outcome-run-count");
      count.className = `badge ${runs.length ? "available" : "missing"}`;
      count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
      if (!runs.length) {
        document.querySelector("#outcome-run-list").innerHTML = messages(outcomeRunsPayload || {}) || `<div class="message warning">No runs are recorded in the local run index.</div>`;
        return;
      }
      document.querySelector("#outcome-run-list").innerHTML = runs.map((run) => `
        <button class="run-row ${run.run_id === selectedOutcomeRunId ? "selected" : ""}" type="button" data-outcome-run-id="${escapeHtml(run.run_id)}">
          <span class="run-row-main">
            <span class="run-id">${escapeHtml(run.run_id)}</span>
            ${badge(run.status)}
          </span>
          <span class="run-meta">
            <span>${escapeHtml(text(run.started_at))}</span>
            <span>Warnings: ${escapeHtml(text(run.warning_count))}</span>
            <span>Errors: ${escapeHtml(text(run.error_count))}</span>
          </span>
        </button>`).join("");
      document.querySelectorAll("[data-outcome-run-id]").forEach((button) => {
        button.addEventListener("click", () => selectOutcomeRun(button.dataset.outcomeRunId));
      });
    }

    async function selectOutcomeRun(runId) {
      if (!runId) {
        return;
      }
      selectedOutcomeRunId = runId;
      selectedOutcomeArtifactKey = null;
      document.querySelector("#outcome-selected-run").textContent = runId;
      document.querySelector("#outcome-status").textContent = "Loading";
      renderOutcomeRunList();
      try {
        outcomesPayload = await fetchJson(`${endpoints.outcomes}?run_id=${encodeURIComponent(runId)}`);
        renderOutcomes(outcomesPayload);
      } catch (error) {
        renderOutcomesFailure(error);
      }
    }

    function renderOutcomes(payload) {
      const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts : [];
      const selectedRun = payload.selected_run || {};
      const selectedFields = selectedRun.fields || {};
      document.querySelector("#outcome-status").textContent = label(payload.status);
      document.querySelector("#outcome-selected-run").textContent = text(selectedFields.run_id || selectedOutcomeRunId);
      const count = document.querySelector("#outcome-artifact-count");
      count.className = `badge ${artifacts.length ? normalizeStatus(payload.status) : "missing"}`;
      count.textContent = `${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}`;
      if (!artifacts.length) {
        document.querySelector("#outcome-artifact-list").innerHTML = messages(payload) || `<div class="message warning">No outcome artifacts are available for the selected run.</div>`;
        document.querySelector("#outcome-artifact-detail").innerHTML = "";
        renderOutcomeHistory(payload.history || {});
        return;
      }
      if (!selectedOutcomeArtifactKey || !artifacts.some((artifact) => artifact.name === selectedOutcomeArtifactKey)) {
        selectedOutcomeArtifactKey = artifacts[0].name;
      }
      document.querySelector("#outcome-artifact-list").innerHTML = artifacts.map((artifact) => {
        const fields = artifact.fields || {};
        return `
          <button class="store-card ${artifact.name === selectedOutcomeArtifactKey ? "selected" : ""}" type="button" data-outcome-artifact-key="${escapeHtml(artifact.name)}">
            <span class="store-title-line">
              <span class="store-title">${escapeHtml(text(fields.title || artifact.name))}</span>
              ${badge(artifact.status)}
            </span>
            <span class="store-metrics">
              <span>Records: ${escapeHtml(text(fields.record_count))}</span>
              <span>Warnings: ${escapeHtml(text(fields.warning_count))}</span>
              <span>Errors: ${escapeHtml(text(fields.error_count))}</span>
            </span>
            <span class="timeline-meta">${escapeHtml(text(fields.preview_path || fields.artifact))}</span>
          </button>`;
      }).join("");
      document.querySelectorAll("[data-outcome-artifact-key]").forEach((button) => {
        button.addEventListener("click", () => {
          selectedOutcomeArtifactKey = button.dataset.outcomeArtifactKey;
          renderOutcomes(payload);
        });
      });
      renderOutcomeArtifactDetail(artifacts.find((artifact) => artifact.name === selectedOutcomeArtifactKey));
      renderOutcomeHistory(payload.history || {});
    }

    function renderOutcomeArtifactDetail(artifact) {
      if (!artifact) {
        document.querySelector("#outcome-artifact-detail").innerHTML = `<div class="message warning">Outcome artifact detail is not available.</div>`;
        return;
      }
      const fields = artifact.fields || {};
      const refs = Array.isArray(artifact.source_artifacts) ? artifact.source_artifacts : [];
      document.querySelector("#outcome-artifact-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>${escapeHtml(text(fields.title || artifact.name))}</span>
            ${badge(artifact.status)}
          </h3>
          <div class="run-detail-grid">
            ${detailTile("Artifact", fields.artifact)}
            ${detailTile("Type", fields.artifact_type)}
            ${detailTile("Artifact status", fields.artifact_status)}
            ${detailTile("Records", fields.record_count)}
            ${detailTile("Warnings", fields.warning_count)}
            ${detailTile("Errors", fields.error_count)}
          </div>
          ${messages(artifact)}
          <div class="artifact-actions">
            ${refs.filter(isPreviewableRef).map((ref) => `<button class="link-button" type="button" data-outcome-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("") || `<span class="badge missing">no previewable refs</span>`}
          </div>
        </section>`;
      document.querySelectorAll("[data-outcome-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.outcomePreviewPath, "#outcome-preview"));
      });
      if (isPreviewableRef(fields.preview_path)) {
        loadArtifactPreview(fields.preview_path, "#outcome-preview");
      }
    }

    function renderOutcomeHistory(history) {
      const fields = history.fields || {};
      const refs = Array.isArray(history.source_artifacts) ? history.source_artifacts : [];
      document.querySelector("#outcome-history-detail").innerHTML = `
        <section class="section-block">
          <h3 class="subheading">
            <span>Shared outcome history metadata</span>
            ${badge(history.status)}
          </h3>
          <div class="run-detail-grid">
            ${detailTile("Records", fields.records)}
            ${detailTile("Incoming", fields.incoming_records)}
            ${detailTile("Duplicates", fields.duplicate_records)}
            ${detailTile("Conflicts", fields.conflicting_duplicates)}
            ${detailTile("Updated", fields.updated_at)}
            ${detailTile("History", fields.history)}
          </div>
          ${messages(history)}
          <div class="artifact-actions">
            ${refs.filter(isPreviewableRef).map((ref) => `<button class="link-button" type="button" data-outcome-preview-path="${escapeHtml(ref)}">${escapeHtml(ref)}</button>`).join("") || `<span class="badge missing">no previewable refs</span>`}
          </div>
        </section>`;
      document.querySelectorAll("#outcome-history-detail [data-outcome-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.outcomePreviewPath, "#outcome-preview"));
      });
    }

    function renderOutcomesFailure(error) {
      document.querySelector("#outcome-status").textContent = "Failed";
      document.querySelector("#outcome-artifact-count").className = "badge failed";
      document.querySelector("#outcome-artifact-count").textContent = "failed";
      document.querySelector("#outcome-artifact-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      document.querySelector("#outcome-artifact-detail").innerHTML = "";
      document.querySelector("#outcome-history-detail").innerHTML = "";
    }

    async function refreshMonitorJobs() {
      try {
        const payload = await fetchJson(endpoints.jobs);
        renderMonitorJobs(payload);
      } catch (error) {
        renderMonitorJobsFailure(error);
      }
    }

    function renderMonitorJobs(payload) {
      const allJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      const jobs = allJobs.filter((job) => String(job.intent || "").startsWith("monitor_"));
      const active = jobs.filter((job) => !terminalJobStatuses.has(String(job.status || "")));
      document.querySelector("#monitor-job-status").textContent = active.length
        ? `${active.length} active`
        : jobs.length
          ? "Idle"
          : "No monitor jobs";
      const count = document.querySelector("#monitor-job-count");
      count.className = `badge ${jobs.length ? "available" : "missing"}`;
      count.textContent = `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;
      if (!jobs.length) {
        document.querySelector("#monitor-job-list").innerHTML = `<div class="message warning">No monitor jobs are recorded in the dashboard job history.</div>`;
        scheduleMonitorJobPolling(false);
        return;
      }
      document.querySelector("#monitor-job-list").innerHTML = jobs.slice(0, 10).map((job) => {
        const running = !terminalJobStatuses.has(String(job.status || ""));
        const refs = Object.entries(job.result_refs || {}).map(([key, value]) => `${key}: ${text(value)}`).join("; ");
        return `
          <div class="job-row">
            <div class="stage-top">
              <span class="stage-name">${escapeHtml(jobTitle(job.intent))}</span>
              ${badge(job.status)}
            </div>
            <div class="run-meta">
              <span>Created: ${escapeHtml(text(job.created_at))}</span>
              <span>Started: ${escapeHtml(text(job.started_at))}</span>
              <span>Finished: ${escapeHtml(text(job.finished_at))}</span>
              <span>Exit: ${escapeHtml(text(job.exit_code))}</span>
            </div>
            <div class="timeline-meta">${escapeHtml(refs || (job.command || []).join(" "))}</div>
            ${messages(job)}
            <div class="job-actions">
              ${running && job.cancellable !== false ? `<button class="link-button" type="button" data-cancel-job-id="${escapeHtml(job.job_id)}">Cancel job</button>` : ""}
              ${running && job.cancellable === false ? `<span class="badge partial">cancellation unsupported</span>` : ""}
            </div>
          </div>`;
      }).join("");
      document.querySelectorAll("[data-cancel-job-id]").forEach((button) => {
        button.addEventListener("click", () => cancelMonitorJob(button.dataset.cancelJobId));
      });
      scheduleMonitorJobPolling(active.length > 0);
    }

    function renderMonitorJobsFailure(error) {
      document.querySelector("#monitor-job-status").textContent = "Failed";
      document.querySelector("#monitor-job-count").className = "badge failed";
      document.querySelector("#monitor-job-count").textContent = "failed";
      document.querySelector("#monitor-job-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      scheduleMonitorJobPolling(false);
    }

    function scheduleMonitorJobPolling(active) {
      if (active && !monitorJobPoll) {
        monitorJobPoll = window.setInterval(refreshMonitorJobs, 2000);
        return;
      }
      if (!active && monitorJobPoll) {
        window.clearInterval(monitorJobPoll);
        monitorJobPoll = null;
      }
    }

    function jobTitle(intent) {
      const titles = {
        run: "Product run with Codex",
        run_no_codex: "Product run without Codex",
        run_until: "Product run until stage",
        stage_rerun: "Stage rerun",
        validate: "Product validation",
        data_inspect: "Data inspect",
        outcomes_inspect: "Outcomes inspect",
        workbench_build: "Workbench build",
        workbench_inspect: "Workbench inspect",
        backtest: "Strategy backtest",
        experiment: "Strategy experiment",
        text_models_prepare: "Text models prepare",
        text_intel: "Text intelligence",
        monitor_dry_run: "Monitor dry run",
        monitor_once: "Monitor one cycle",
        monitor_loop: "Monitor finite loop",
        monitor_inspect: "Monitor inspect"
      };
      return titles[intent] || intent || "Monitor job";
    }

    async function startMonitorJob(action) {
      let request;
      if (action === "dry-run") {
        request = { intent: "monitor_dry_run", params: {} };
      } else if (action === "once") {
        request = { intent: "monitor_once", params: {} };
      } else if (action === "loop") {
        const maxCycles = positiveInputValue("#monitor-loop-cycles");
        const intervalSeconds = positiveInputValue("#monitor-loop-interval");
        if (!maxCycles || !intervalSeconds) {
          document.querySelector("#monitor-job-status").textContent = "Invalid loop input";
          document.querySelector("#monitor-job-list").innerHTML = `<div class="message error">Max cycles and interval seconds must be positive integers.</div>`;
          return;
        }
        request = {
          intent: "monitor_loop",
          params: { max_cycles: maxCycles, interval_seconds: intervalSeconds }
        };
      } else {
        return;
      }
      document.querySelector("#monitor-job-status").textContent = "Starting";
      try {
        const job = await postJson(endpoints.jobs, request);
        document.querySelector("#monitor-job-status").textContent = `${jobTitle(job.intent)} ${label(job.status)}`;
        await refreshMonitorJobs();
      } catch (error) {
        renderMonitorJobsFailure(error);
      }
    }

    function positiveInputValue(selector) {
      const value = Number.parseInt(document.querySelector(selector).value, 10);
      return Number.isInteger(value) && value > 0 ? value : null;
    }

    async function cancelMonitorJob(jobId) {
      if (!jobId) {
        return;
      }
      document.querySelector("#monitor-job-status").textContent = "Cancelling";
      try {
        await postJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}/cancel`, {});
        await refreshMonitorJobs();
      } catch (error) {
        renderMonitorJobsFailure(error);
      }
    }

    async function loadCommandCenter() {
      commandJobsLoaded = true;
      if (!dailyScheduleLoaded) {
        await refreshDailySchedule();
      }
      await refreshCommandJobs();
    }

    async function refreshDailySchedule() {
      dailyScheduleLoaded = true;
      document.querySelector("#daily-schedule-badge").className = "badge unknown";
      document.querySelector("#daily-schedule-badge").textContent = "loading";
      try {
        const payload = await fetchJson(endpoints.schedule);
        renderDailySchedule(payload);
      } catch (error) {
        renderDailyScheduleFailure(error);
      }
    }

    function renderDailySchedule(schedule) {
      const settings = schedule.settings || {};
      const boundary = schedule.runtime_boundary || {};
      const badgeNode = document.querySelector("#daily-schedule-badge");
      badgeNode.className = `badge ${schedule.enabled === true ? "available" : normalizeStatus(schedule.status)}`;
      badgeNode.textContent = schedule.enabled === true ? "enabled" : label(schedule.status);
      document.querySelector("#daily-schedule-time").value = text(settings.time_of_day) === "n/a" ? "08:00" : text(settings.time_of_day);
      document.querySelector("#daily-schedule-timezone").value = text(settings.timezone) === "n/a" ? "UTC" : text(settings.timezone);
      document.querySelector("#daily-schedule-job-intent").value = text(settings.job_intent) === "run" ? "run" : "run_no_codex";
      document.querySelector("#daily-schedule-summary").innerHTML = [
        detailTile("Enabled", schedule.enabled === true ? "true" : "false"),
        detailTile("Persisted", schedule.persisted === true ? "true" : "false"),
        detailTile("Next run", schedule.next_run_at),
        detailTile("Last run", schedule.last_run_at),
        detailTile("Last job", schedule.last_job_id),
        detailTile("Linked jobs", Array.isArray(schedule.linked_job_ids) ? schedule.linked_job_ids.length : 0),
        detailTile("Runs while dashboard active", boundary.runs_only_while_dashboard_active),
        detailTile("Automatic dispatch", boundary.automatic_dispatch)
      ].join("");
      document.querySelector("#daily-schedule-messages").innerHTML = messages(schedule);
      document.querySelector("#command-center-status").textContent = schedule.enabled === true ? "Schedule enabled" : "Schedule idle";
    }

    function renderDailyScheduleFailure(error) {
      document.querySelector("#daily-schedule-badge").className = "badge failed";
      document.querySelector("#daily-schedule-badge").textContent = "failed";
      document.querySelector("#daily-schedule-summary").innerHTML = detailTile("Error", error.message);
      document.querySelector("#daily-schedule-messages").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
    }

    async function runDailyScheduleAction(action) {
      const request = dailyScheduleRequest(action);
      if (!request) {
        return;
      }
      document.querySelector("#command-center-status").textContent = "Updating schedule";
      try {
        const payload = await postJson(request.url, request.body);
        if (payload.schedule) {
          renderDailySchedule(payload.schedule);
          if (payload.job) {
            document.querySelector("#command-center-status").textContent = `${jobTitle(payload.job.intent)} ${label(payload.job.status)}`;
            renderCommandResult(payload.job);
          } else {
            renderScheduleActionResult(payload);
          }
        } else {
          renderDailySchedule(payload);
          renderCommandMessage(payload.status, `Daily report schedule ${action} ${label(payload.status)}.`);
        }
        await refreshCommandJobs();
      } catch (error) {
        renderCommandMessage("failed", error.message);
      }
    }

    function dailyScheduleRequest(action) {
      if (action === "disable") {
        return { url: `${endpoints.schedule}/disable`, body: {} };
      }
      const body = {
        time_of_day: optionalInputValue("#daily-schedule-time"),
        timezone: optionalInputValue("#daily-schedule-timezone"),
        job_intent: document.querySelector("#daily-schedule-job-intent").value
      };
      if (!body.time_of_day || !body.timezone) {
        renderCommandMessage("blocked", "time_of_day and timezone are required for daily report schedule changes.");
        return null;
      }
      if (action === "update") {
        return { url: endpoints.schedule, body };
      }
      if (action === "enable") {
        return { url: `${endpoints.schedule}/enable`, body };
      }
      if (action === "trigger") {
        const triggerBody = { job_intent: body.job_intent };
        if (body.job_intent === "run") {
          if (document.querySelector("#daily-schedule-confirm-codex").checked !== true) {
            renderCommandMessage("blocked", "Codex confirmation is required before triggering a Codex-capable daily report job.");
            return null;
          }
          triggerBody.confirm_codex = true;
        }
        return { url: `${endpoints.schedule}/trigger`, body: triggerBody };
      }
      renderCommandMessage("unsupported", `unsupported daily report schedule action: ${action || "missing"}`);
      return null;
    }

    function renderScheduleActionResult(payload) {
      const schedule = payload.schedule || {};
      document.querySelector("#command-center-status").textContent = `Schedule ${label(payload.status)}`;
      document.querySelector("#command-result").innerHTML = `
        <div class="preview-heading">
          <div class="preview-path">Daily report schedule</div>
          ${badge(payload.status)}
        </div>
        <div class="run-detail-grid">
          ${detailTile("Enabled", schedule.enabled === true ? "true" : "false")}
          ${detailTile("Next run", schedule.next_run_at)}
          ${detailTile("Last job", schedule.last_job_id)}
          ${detailTile("Job", payload.job ? payload.job.job_id : "n/a")}
        </div>
        ${messages(payload)}`;
    }

    async function refreshCommandJobs() {
      try {
        const payload = await fetchJson(endpoints.jobs);
        commandJobsPayload = payload;
        renderCommandJobs(payload);
      } catch (error) {
        renderCommandJobsFailure(error);
      }
    }

    function renderCommandJobs(payload) {
      const allJobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      const jobs = filteredCommandJobs(allJobs);
      const active = allJobs.filter((job) => !terminalJobStatuses.has(String(job.status || "")));
      document.querySelector("#command-job-status").textContent = active.length
        ? `${active.length} active`
        : allJobs.length
          ? "Idle"
          : "No jobs";
      const count = document.querySelector("#command-job-count");
      count.className = `badge ${allJobs.length ? "available" : "missing"}`;
      count.textContent = `${jobs.length} of ${allJobs.length} job${allJobs.length === 1 ? "" : "s"}`;
      if (!allJobs.length) {
        document.querySelector("#command-result").innerHTML = `<div class="message">Choose an allowlisted command to create a bounded local dashboard job.</div>`;
        document.querySelector("#command-job-preview").innerHTML = `<div class="message">Open a job result ref, stdout, or stderr to inspect a bounded preview.</div>`;
        document.querySelector("#command-job-list").innerHTML = messages(payload) || `<div class="message warning">No dashboard jobs are recorded.</div>`;
        scheduleCommandJobPolling(false);
        return;
      }
      if (!selectedCommandJobId || !allJobs.some((job) => job.job_id === selectedCommandJobId)) {
        selectedCommandJobId = allJobs[0].job_id;
      }
      const selectedJob = allJobs.find((job) => job.job_id === selectedCommandJobId);
      if (selectedJob) {
        renderCommandResult(selectedJob);
      }
      if (!jobs.length) {
        document.querySelector("#command-job-list").innerHTML = `<div class="message warning">No dashboard jobs match the current filters.</div>`;
        scheduleCommandJobPolling(active.length > 0);
        return;
      }
      document.querySelector("#command-job-list").innerHTML = jobs.slice(0, 20).map((job) => {
        const running = !terminalJobStatuses.has(String(job.status || ""));
        const refs = Object.entries(job.result_refs || {}).map(([key, value]) => `${key}: ${text(value)}`).join("; ");
        return `
          <div class="job-row ${job.job_id === selectedCommandJobId ? "selected" : ""}">
            <div class="stage-top">
              <span class="stage-name">${escapeHtml(jobTitle(job.intent))}</span>
              ${badge(job.status)}
            </div>
            <div class="run-meta">
              <span>Job: ${escapeHtml(text(job.job_id))}</span>
              <span>Created: ${escapeHtml(text(job.created_at))}</span>
              <span>Started: ${escapeHtml(text(job.started_at))}</span>
              <span>Finished: ${escapeHtml(text(job.finished_at))}</span>
              <span>Exit: ${escapeHtml(text(job.exit_code))}</span>
            </div>
            <div class="timeline-meta">${escapeHtml(refs || (job.command || []).join(" "))}</div>
            ${messages(job)}
            <div class="job-actions">
              <button class="link-button" type="button" data-command-job-id="${escapeHtml(job.job_id)}">Open details</button>
              ${running && job.cancellable !== false ? `<button class="link-button" type="button" data-command-cancel-job-id="${escapeHtml(job.job_id)}">Cancel job</button>` : ""}
              ${running && job.cancellable === false ? `<span class="badge partial">cancellation unsupported</span>` : ""}
            </div>
          </div>`;
      }).join("");
      document.querySelectorAll("[data-command-job-id]").forEach((button) => {
        button.addEventListener("click", () => selectCommandJob(button.dataset.commandJobId));
      });
      document.querySelectorAll("[data-command-cancel-job-id]").forEach((button) => {
        button.addEventListener("click", () => cancelCommandJob(button.dataset.commandCancelJobId));
      });
      scheduleCommandJobPolling(active.length > 0);
    }

    function filteredCommandJobs(jobs) {
      const intentQuery = document.querySelector("#command-job-intent-filter").value.trim().toLowerCase();
      const statusFilter = document.querySelector("#command-job-status-filter").value;
      const kindQuery = document.querySelector("#command-job-kind-filter").value.trim().toLowerCase();
      return jobs.filter((job) => {
        const status = String(job.status || "");
        if (statusFilter === "active" && terminalJobStatuses.has(status)) {
          return false;
        }
        if (statusFilter === "terminal" && !terminalJobStatuses.has(status)) {
          return false;
        }
        if (!["all", "active", "terminal"].includes(statusFilter) && status !== statusFilter) {
          return false;
        }
        if (intentQuery && !String(job.intent || "").toLowerCase().includes(intentQuery)) {
          return false;
        }
        if (kindQuery && !String(job.kind || "").toLowerCase().includes(kindQuery)) {
          return false;
        }
        return true;
      });
    }

    async function selectCommandJob(jobId) {
      if (!jobId) {
        return;
      }
      selectedCommandJobId = jobId;
      document.querySelector("#command-center-status").textContent = "Loading job";
      try {
        const job = await fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
        document.querySelector("#command-center-status").textContent = `${jobTitle(job.intent)} ${label(job.status)}`;
        if (commandJobsPayload) {
          commandJobsPayload.jobs = (commandJobsPayload.jobs || []).map((item) => item.job_id === job.job_id ? job : item);
          renderCommandJobs(commandJobsPayload);
        } else {
          renderCommandResult(job);
        }
      } catch (error) {
        renderCommandMessage("failed", error.message);
      }
    }

    function renderCommandJobsFailure(error) {
      document.querySelector("#command-job-status").textContent = "Failed";
      document.querySelector("#command-job-count").className = "badge failed";
      document.querySelector("#command-job-count").textContent = "failed";
      document.querySelector("#command-job-list").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      scheduleCommandJobPolling(false);
    }

    function scheduleCommandJobPolling(active) {
      if (active && !commandJobPoll) {
        commandJobPoll = window.setInterval(refreshCommandJobs, 2000);
        return;
      }
      if (!active && commandJobPoll) {
        window.clearInterval(commandJobPoll);
        commandJobPoll = null;
      }
    }

    async function startCommandJob(intent) {
      const request = commandJobRequest(intent);
      if (!request) {
        return;
      }
      document.querySelector("#command-center-status").textContent = "Starting";
      try {
        const job = await postJson(endpoints.jobs, request);
        document.querySelector("#command-center-status").textContent = `${jobTitle(job.intent)} ${label(job.status)}`;
        renderCommandResult(job);
        await refreshCommandJobs();
      } catch (error) {
        renderCommandMessage("failed", error.message);
      }
    }

    function commandJobRequest(intent) {
      const params = {};
      if (intent === "run_no_codex") {
        return { intent, params };
      }
      if (intent === "run") {
        if (!codexConfirmed()) {
          renderCommandMessage("blocked", "Codex confirmation is required before creating this job.");
          return null;
        }
        params.confirm_codex = true;
        return { intent, params };
      }
      if (intent === "run_until") {
        const stageName = requiredInputValue("#command-run-until-stage", "stage_name is required for run_until.");
        if (!stageName) {
          return null;
        }
        if (stageReachesCodex(stageName) && !codexConfirmed()) {
          renderCommandMessage("blocked", "Codex confirmation is required for a stage that reaches Codex report generation.");
          return null;
        }
        params.stage_name = stageName;
        if (codexConfirmed()) {
          params.confirm_codex = true;
        }
        return { intent, params };
      }
      if (["validate", "data_inspect", "outcomes_inspect", "workbench_build"].includes(intent)) {
        const runDir = optionalInputValue("#command-run-dir");
        if (runDir) {
          params.run_dir = runDir;
        }
        return { intent, params };
      }
      if (["workbench_inspect", "monitor_inspect", "monitor_dry_run", "monitor_once"].includes(intent)) {
        return { intent, params };
      }
      if (intent === "monitor_loop") {
        const maxCycles = positiveInputValue("#command-monitor-loop-cycles");
        const intervalSeconds = positiveInputValue("#command-monitor-loop-interval");
        if (!maxCycles || !intervalSeconds) {
          renderCommandMessage("blocked", "max_cycles and interval_seconds must be positive integers.");
          return null;
        }
        params.max_cycles = maxCycles;
        params.interval_seconds = intervalSeconds;
        return { intent, params };
      }
      if (intent === "backtest") {
        const strategyName = requiredInputValue("#command-backtest-strategy", "strategy_name is required for backtest.");
        const symbol = requiredInputValue("#command-backtest-symbol", "symbol is required for backtest.");
        const timeframe = requiredInputValue("#command-backtest-timeframe", "timeframe is required for backtest.");
        if (!strategyName || !symbol || !timeframe) {
          return null;
        }
        params.strategy_name = strategyName;
        params.symbol = symbol;
        params.timeframe = timeframe;
        const outputDir = optionalInputValue("#command-strategy-output-dir");
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      if (intent === "experiment") {
        const strategyNames = commaListInputValue("#command-backtest-strategy");
        if (!strategyNames.length) {
          renderCommandMessage("blocked", "strategy_names must include at least one configured strategy.");
          return null;
        }
        params.strategy_names = strategyNames;
        const outputDir = optionalInputValue("#command-strategy-output-dir");
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      if (intent === "text_models_prepare") {
        const outputDir = optionalInputValue("#command-text-output-dir");
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      if (intent === "text_intel") {
        const inputPath = optionalInputValue("#command-text-input-path");
        const outputDir = optionalInputValue("#command-text-output-dir");
        if (inputPath) {
          params.input_path = inputPath;
        }
        if (outputDir) {
          params.output_dir = outputDir;
        }
        return { intent, params };
      }
      renderCommandMessage("unsupported", `unsupported dashboard job intent: ${intent || "missing"}`);
      return null;
    }

    function codexConfirmed() {
      return document.querySelector("#command-run-confirm-codex").checked === true;
    }

    function stageReachesCodex(stageName) {
      const stages = "collect_market_data collect_derivatives_market_data sync_derivatives_market_history build_derivatives_market_views build_derivatives_market_context collect_macro_calendar_data sync_macro_calendar_history build_macro_calendar_views build_macro_calendar_context build_macro_calendar_material collect_onchain_flow_data sync_onchain_flow_history build_onchain_flow_views build_onchain_flow_context build_onchain_flow_material collect_text_events build_text_event_records build_text_entity_evidence build_text_event_classification_evidence build_text_event_topics build_text_event_signals sync_ohlcv build_market_data_views build_strategy_benchmark_suite evaluate_quant_strategies evaluate_strategy_evaluation build_strategy_experiment_material evaluate_market_strategy_signals build_market_signals build_market_signal_material build_market_regime_assessment build_risk_assessment build_decision_recommendations build_watch_triggers build_event_market_confluence build_event_intelligence_assessment build_alert_decisions build_alert_decision_material build_event_intelligence_material build_decision_intelligence_delta build_decision_intelligence_material build_data_quality_summary build_outcome_targets evaluate_outcomes build_strategy_lifecycle_state build_strategy_lifecycle_material build_feature_snapshots build_factor_states build_multi_source_signals build_intelligence_fusion integrate_intelligence_fusion build_user_state_context build_personalized_risk_constraints integrate_personalized_risk_constraints build_personalized_risk_material build_analysis_materials build_research_context build_codex_context run_codex_report validate_product_contracts".split(" ");
      const stageIndex = stages.indexOf(stageName);
      const codexIndex = stages.indexOf("run_codex_report");
      return stageIndex >= codexIndex && codexIndex >= 0;
    }

    function optionalInputValue(selector) {
      return document.querySelector(selector).value.trim();
    }

    function requiredInputValue(selector, message) {
      const value = optionalInputValue(selector);
      if (!value) {
        renderCommandMessage("blocked", message);
        return "";
      }
      return value;
    }

    function commaListInputValue(selector) {
      return optionalInputValue(selector)
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item);
    }

    function renderCommandResult(job) {
      if (job.job_id) {
        selectedCommandJobId = job.job_id;
      }
      const refs = commandPreviewRefs(job);
      const running = !terminalJobStatuses.has(String(job.status || ""));
      const commandPreview = (job.command || []).join(" ");
      document.querySelector("#command-result").innerHTML = `
        <div class="preview-heading">
          <div class="preview-path">${escapeHtml(jobTitle(job.intent))}</div>
          ${badge(job.status)}
        </div>
        <div class="run-detail-grid">
          ${detailTile("Job", job.job_id)}
          ${detailTile("Intent", job.intent)}
          ${detailTile("Kind", job.kind)}
          ${detailTile("Config", job.config_ref)}
          ${detailTile("Created", job.created_at)}
          ${detailTile("Started", job.started_at)}
          ${detailTile("Finished", job.finished_at)}
          ${detailTile("Exit", job.exit_code)}
        </div>
        <div class="timeline-meta">${escapeHtml(commandPreview)}</div>
        ${messages(job)}
        <div class="artifact-actions">
          ${refs.length ? refs.map((item) => `<button class="link-button" type="button" data-command-preview-path="${escapeHtml(item.path)}">${escapeHtml(item.label)}</button>`).join("") : `<span class="badge missing">no preview refs</span>`}
          ${running && job.cancellable !== false ? `<button class="link-button" type="button" data-command-cancel-job-id="${escapeHtml(job.job_id)}">Cancel job</button>` : ""}
        </div>`;
      wireCommandPreviewButtons();
      document.querySelectorAll("#command-result [data-command-cancel-job-id]").forEach((button) => {
        button.addEventListener("click", () => cancelCommandJob(button.dataset.commandCancelJobId));
      });
    }

    function commandPreviewRefs(job) {
      const refs = [];
      Object.entries(job.result_refs || {}).forEach(([key, value]) => {
        if (isPreviewableRef(value)) {
          refs.push({ label: `Result: ${key}`, path: String(value) });
        }
      });
      const logs = job.logs || {};
      if (isPreviewableRef(logs.stdout_ref)) {
        refs.push({ label: "stdout.log", path: String(logs.stdout_ref) });
      }
      if (isPreviewableRef(logs.stderr_ref)) {
        refs.push({ label: "stderr.log", path: String(logs.stderr_ref) });
      }
      return refs;
    }

    function isPreviewableRef(value) {
      const ref = String(value || "");
      return (ref.startsWith("runs/") || ref.startsWith("data/"))
        && /\\.(json|jsonl|md|markdown|txt|log|csv|yaml|yml)$/i.test(ref);
    }

    function wireCommandPreviewButtons() {
      document.querySelectorAll("[data-command-preview-path]").forEach((button) => {
        button.addEventListener("click", () => loadArtifactPreview(button.dataset.commandPreviewPath, "#command-job-preview"));
      });
    }

    function renderCommandMessage(status, message) {
      document.querySelector("#command-center-status").textContent = label(status);
      document.querySelector("#command-result").innerHTML = `<div class="message ${normalizeStatus(status) === "failed" ? "error" : "warning"}">${escapeHtml(message)}</div>`;
    }

    async function cancelCommandJob(jobId) {
      if (!jobId) {
        return;
      }
      document.querySelector("#command-center-status").textContent = "Cancelling";
      try {
        const job = await postJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}/cancel`, {});
        renderCommandResult(job);
        await refreshCommandJobs();
      } catch (error) {
        renderCommandMessage("failed", error.message);
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
    document.querySelector("#artifact-layer-filter").addEventListener("change", renderArtifactExplorer);
    document.querySelector("#artifact-search-filter").addEventListener("input", renderArtifactExplorer);
    document.querySelector("#data-group-filter").addEventListener("change", renderDataStores);
    document.querySelector("#data-search-filter").addEventListener("input", renderDataStores);
    document.querySelector("#strategy-scope-filter").addEventListener("change", renderStrategies);
    document.querySelector("#strategy-search-filter").addEventListener("input", renderStrategies);
    document.querySelectorAll("[data-monitor-action]").forEach((button) => {
      button.addEventListener("click", () => startMonitorJob(button.dataset.monitorAction));
    });
    document.querySelectorAll("[data-command-intent]").forEach((button) => {
      button.addEventListener("click", () => startCommandJob(button.dataset.commandIntent));
    });
    document.querySelectorAll("[data-text-command-intent]").forEach((button) => {
      button.addEventListener("click", () => startTextJob(button.dataset.textCommandIntent));
    });
    document.querySelectorAll("[data-schedule-action]").forEach((button) => {
      button.addEventListener("click", () => runDailyScheduleAction(button.dataset.scheduleAction));
    });
    document.querySelector("#command-job-intent-filter").addEventListener("input", () => {
      if (commandJobsPayload) {
        renderCommandJobs(commandJobsPayload);
      }
    });
    document.querySelector("#command-job-status-filter").addEventListener("change", () => {
      if (commandJobsPayload) {
        renderCommandJobs(commandJobsPayload);
      }
    });
    document.querySelector("#command-job-kind-filter").addEventListener("input", () => {
      if (commandJobsPayload) {
        renderCommandJobs(commandJobsPayload);
      }
    });
    window.addEventListener("hashchange", () => setView(viewFromHash()));

    fetchJson(endpoints.overview).then(renderOverview).catch(renderOverviewFailure);
    setView(viewFromHash());
  </script>
</body>
</html>
"""
