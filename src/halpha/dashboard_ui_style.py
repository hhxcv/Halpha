from __future__ import annotations


def dashboard_css() -> str:
    return """    :root {
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --panel-soft: #fbfcfd;
      --sidebar: #0d1b2a;
      --sidebar-2: #10263b;
      --border: #dce2ea;
      --border-strong: #bdc8d6;
      --text: #111827;
      --muted: #5d6675;
      --muted-2: #8a94a5;
      --teal: #008575;
      --teal-dark: #006f62;
      --teal-soft: #e5f7f4;
      --amber: #c46a00;
      --amber-soft: #fff4dc;
      --red: #dc2626;
      --red-soft: #fdecec;
      --blue: #2563eb;
      --blue-soft: #eef4ff;
      --shadow: 0 1px 2px rgba(15, 23, 42, 0.06), 0 8px 24px rgba(15, 23, 42, 0.04);
      --radius: 8px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
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

    button,
    input,
    select {
      font: inherit;
    }

    button {
      cursor: pointer;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    .app-shell {
      display: grid;
      grid-template-columns: 224px minmax(0, 1fr);
      min-height: 100vh;
    }

    .sidebar {
      display: flex;
      flex-direction: column;
      gap: 24px;
      min-width: 0;
      padding: 20px 12px;
      background: linear-gradient(180deg, var(--sidebar), #081320);
      color: #f8fafc;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 2px 6px 14px;
    }

    .brand-mark {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 7px;
      background: #0f766e;
      color: #d9fffa;
      font-weight: 800;
    }

    .brand-name {
      font-size: 22px;
      line-height: 1;
      font-weight: 780;
    }

    .brand-subtitle {
      margin-top: 4px;
      color: #a9b5c4;
      font-size: 12px;
    }

    .nav {
      display: grid;
      gap: 8px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      min-height: 44px;
      padding: 10px 12px;
      border-radius: var(--radius);
      color: #d7dee8;
      font-weight: 650;
    }

    .nav-item:hover {
      background: rgba(255, 255, 255, 0.07);
    }

    .nav-item.active {
      background: linear-gradient(135deg, #007c72, #005f71);
      color: #ffffff;
      box-shadow: 0 8px 18px rgba(0, 90, 100, 0.28);
    }

    .nav-icon {
      width: 18px;
      height: 18px;
      color: currentColor;
      flex: 0 0 auto;
    }

    .sidebar-bottom {
      display: grid;
      gap: 12px;
      margin-top: auto;
    }

    .sidebar-card {
      padding: 13px;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: var(--radius);
      background: rgba(255, 255, 255, 0.045);
    }

    .health-dot {
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--teal);
      margin-right: 7px;
    }

    .sidebar-card-title {
      font-size: 12px;
      font-weight: 760;
    }

    .sidebar-card-detail {
      margin-top: 7px;
      color: #b7c2d0;
      font-size: 12px;
      line-height: 1.4;
    }

    .sidebar-disclaimer {
      padding-top: 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.12);
      color: #a9b5c4;
      font-size: 12px;
      line-height: 1.45;
    }

    .main-shell {
      min-width: 0;
      background: var(--bg);
    }

    .global-topbar {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 14px;
      height: 54px;
      padding: 0 24px;
      border-bottom: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.86);
      backdrop-filter: blur(8px);
    }

    .top-status-item {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--text);
      font-size: 13px;
      white-space: nowrap;
    }

    .icon-button,
    .ghost-button,
    .primary-button,
    .danger-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 38px;
      padding: 8px 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel);
      color: var(--text);
      font-weight: 700;
      white-space: nowrap;
    }

    .icon-button {
      width: 38px;
      padding: 0;
    }

    .primary-button {
      border-color: var(--teal-dark);
      background: linear-gradient(180deg, var(--teal), var(--teal-dark));
      color: #ffffff;
      box-shadow: 0 8px 18px rgba(0, 117, 104, 0.18);
    }

    .danger-button {
      border-color: #ef8585;
      background: #fff;
      color: var(--red);
    }

    .ghost-button:hover,
    .icon-button:hover {
      border-color: var(--border-strong);
      background: #f4f7fa;
    }

    .primary-button:disabled,
    .ghost-button:disabled,
    .danger-button:disabled {
      cursor: not-allowed;
      opacity: 0.55;
    }

    .view {
      display: block;
      padding: 20px 24px 24px;
    }

    .view.hidden {
      display: none;
    }

    .page-title-row {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      margin-bottom: 14px;
    }

    .page-title h1 {
      margin: 0;
      font-size: 28px;
      line-height: 1.12;
      font-weight: 800;
    }

    .page-title p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .panel {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .panel-pad {
      padding: 16px;
    }

    .panel-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 14px;
      font-size: 16px;
      line-height: 1.2;
      font-weight: 780;
    }

    .status-pill {
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
      font-weight: 760;
      white-space: nowrap;
    }

    .status-pill::before {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      background: currentColor;
      content: "";
    }

    .status-pill.ok,
    .status-pill.available,
    .status-pill.succeeded,
    .status-pill.success,
    .status-pill.completed,
    .status-pill.running {
      border-color: #a9ded7;
      background: var(--teal-soft);
      color: var(--teal);
    }

    .status-pill.warning,
    .status-pill.partial,
    .status-pill.missing,
    .status-pill.skipped,
    .status-pill.unknown,
    .status-pill.pending {
      border-color: #f2cf83;
      background: var(--amber-soft);
      color: var(--amber);
    }

    .status-pill.failed,
    .status-pill.error,
    .status-pill.degraded,
    .status-pill.blocked {
      border-color: #f4b4b4;
      background: var(--red-soft);
      color: var(--red);
    }

    .summary-strip {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .summary-cell {
      min-width: 0;
      padding: 16px 18px;
      border-right: 1px solid var(--border);
    }

    .summary-cell:last-child {
      border-right: 0;
    }

    .summary-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .summary-value {
      margin-top: 8px;
      font-size: 20px;
      line-height: 1.1;
      font-weight: 800;
      overflow-wrap: anywhere;
    }

    .detail-rail .summary-value {
      font-size: 16px;
      overflow-wrap: normal;
      word-break: keep-all;
    }

    .summary-note {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }

    .overview-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 14px;
    }

    .overview-main {
      display: grid;
      gap: 14px;
      min-width: 0;
    }

    .overview-grid-2 {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }

    .report-ops-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 260px;
      gap: 18px;
      align-items: stretch;
    }

    .report-metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      margin-bottom: 16px;
    }

    .report-metric {
      padding: 13px;
      border-right: 1px solid var(--border);
      background: var(--panel-soft);
    }

    .report-metric:last-child {
      border-right: 0;
    }

    .metric-big {
      margin-top: 6px;
      font-size: 22px;
      font-weight: 820;
    }

    .detail-row {
      display: grid;
      grid-template-columns: 150px minmax(0, 1fr);
      gap: 12px;
      align-items: baseline;
      padding: 8px 0;
      border-bottom: 1px solid #edf1f5;
    }

    .detail-row:last-child {
      border-bottom: 0;
    }

    .detail-key {
      color: var(--muted);
      font-size: 12px;
    }

    .detail-value {
      min-width: 0;
      font-weight: 760;
      overflow-wrap: break-word;
      word-break: normal;
    }

    #overview-latest-report {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 0 18px;
    }

    #overview-latest-report .detail-row {
      display: block;
      padding: 7px 0;
    }

    #overview-latest-report .detail-value {
      margin-top: 3px;
      font-size: 13px;
    }

    .meter {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }

    .meter-track {
      height: 8px;
      border-radius: 999px;
      background: #e7ecf2;
      overflow: hidden;
    }

    .meter-fill {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--teal);
    }

    .chart-mini {
      width: 100%;
      height: 118px;
    }

    .data-cards {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }

    .data-card {
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel-soft);
    }

    .data-card-title {
      font-size: 12px;
      font-weight: 760;
    }

    .data-card-value {
      margin-top: 6px;
      font-size: 16px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }

    .sparkline {
      width: 100%;
      height: 34px;
      margin-top: 8px;
    }

    .attention-list,
    .action-list,
    .compact-list {
      display: grid;
      gap: 10px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .attention-item,
    .compact-row {
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--panel-soft);
    }

    .compact-row > span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .attention-title,
    .compact-title {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-weight: 760;
    }

    .attention-copy,
    .compact-copy {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }

    .reports-layout {
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr) 250px;
      gap: 14px;
      min-height: calc(100vh - 96px);
    }

    .report-library {
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: 0;
    }

    .search-input,
    .select-input,
    .text-input,
    .readonly-value {
      width: 100%;
      min-height: 38px;
      padding: 8px 11px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fff;
      color: var(--text);
      outline: 0;
    }

    .readonly-value {
      display: flex;
      align-items: center;
      background: var(--panel-soft);
      color: var(--muted);
      font-weight: 700;
    }

    .search-input:focus,
    .select-input:focus,
    .text-input:focus {
      border-color: #7dc8be;
      box-shadow: 0 0 0 3px rgba(0, 133, 117, 0.14);
    }

    .library-groups {
      display: grid;
      gap: 14px;
      align-content: start;
      min-height: 0;
      overflow: auto;
      padding: 0 14px 14px;
    }

    .library-header {
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 14px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
    }

    .group-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 0 0 8px;
      font-size: 14px;
      font-weight: 780;
    }

    .report-row {
      display: block;
      width: 100%;
      padding: 11px;
      border: 1px solid transparent;
      border-radius: var(--radius);
      background: transparent;
      text-align: left;
    }

    .report-row:hover,
    .report-row.active {
      border-color: #87d3cb;
      background: linear-gradient(90deg, #e6f7f5, #fff);
    }

    .report-row-title {
      display: flex;
      gap: 8px;
      align-items: center;
      font-weight: 780;
    }

    .report-row-meta {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
    }

    .report-workspace {
      display: grid;
      grid-template-rows: auto 1fr;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
    }

    .report-toolbar {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      padding: 12px;
      border-bottom: 1px solid var(--border);
      min-width: 0;
    }

    #selected-report-kicker {
      flex: 1 1 150px;
      min-width: 0;
    }

    .toolbar-actions {
      display: flex;
      gap: 10px;
      align-items: center;
      min-width: 0;
    }

    .report-toolbar .toolbar-actions {
      flex: 1 1 420px;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px;
    }

    .report-toolbar .primary-button,
    .report-toolbar .danger-button,
    .report-toolbar .ghost-button {
      min-height: 36px;
      padding: 8px 12px;
      white-space: nowrap;
    }

    .report-toolbar .search-input {
      width: 150px !important;
      min-width: 120px;
    }

    .report-reader {
      width: 100%;
      max-width: 100%;
      min-width: 0;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 28px 34px;
      background: #fff;
    }

    .markdown-reader {
      max-width: 100%;
      min-width: 0;
      color: #172033;
      font-size: 15px;
      line-height: 1.62;
      overflow-wrap: break-word;
      word-break: normal;
      white-space: normal;
    }

    .markdown-reader h1 {
      margin: 0 0 18px;
      font-size: 32px;
      line-height: 1.15;
      overflow-wrap: anywhere;
      word-break: normal;
    }

    .markdown-reader h2 {
      margin: 28px 0 10px;
      font-size: 21px;
    }

    .markdown-reader h3 {
      margin: 20px 0 8px;
      font-size: 17px;
    }

    .markdown-reader p {
      margin: 8px 0;
    }

    .markdown-reader ul {
      padding-left: 20px;
    }

    .markdown-table-wrap {
      max-width: 100%;
      overflow-x: auto;
      margin: 14px 0 20px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }

    .markdown-reader table {
      display: table;
      width: max-content;
      min-width: 720px;
      border-collapse: collapse;
      margin: 0;
      font-size: 13px;
    }

    .markdown-reader th,
    .markdown-reader td {
      padding: 9px 10px;
      border: 1px solid var(--border);
      text-align: left;
      overflow-wrap: anywhere;
      word-break: normal;
    }

    .markdown-reader th {
      background: #f5f7fa;
      color: var(--muted);
      font-weight: 750;
    }

    .detail-rail {
      display: grid;
      align-content: start;
      gap: 14px;
      min-width: 0;
    }

    .detail-rail .detail-row {
      grid-template-columns: 82px minmax(0, 1fr);
      gap: 8px;
    }

    #intel-detail .summary-value {
      font-size: 18px;
      overflow-wrap: normal;
      word-break: keep-all;
      hyphens: none;
    }

    .outline-list {
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .outline-list a {
      display: block;
      color: var(--muted);
      font-weight: 650;
      line-height: 1.35;
    }

    .outline-list a.active,
    .outline-list a:hover {
      color: var(--teal);
    }

    .strategy-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 250px;
      grid-template-rows: auto auto minmax(0, 1fr) auto;
      gap: 12px;
      min-height: calc(100vh - 96px);
    }

    .strategy-controls {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 160px 140px 210px minmax(220px, 1fr) auto auto;
      gap: 10px;
      align-items: end;
      padding: 12px;
    }

    .field label {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .metric-strip {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      overflow: hidden;
    }

    .kline-panel {
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      background: #0d1b2a;
      color: #dbe7f3;
    }

    .chart-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      background: #0b1726;
    }

    .chart-title {
      font-weight: 760;
    }

    .chart-meta {
      color: #9fb2c7;
      font-size: 12px;
    }

    .chart-wrap {
      position: relative;
      min-height: 470px;
      height: 52vh;
      padding: 0;
      background:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px),
        #0d1b2a;
      background-size: 60px 48px;
    }

    .chart-wrap svg {
      display: block;
      width: 100%;
      height: 100%;
    }

    .chart-tools {
      position: absolute;
      top: 14px;
      left: 12px;
      display: grid;
      gap: 8px;
      z-index: 2;
    }

    .tool-dot {
      display: grid;
      place-items: center;
      width: 34px;
      height: 28px;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 6px;
      background: rgba(9, 18, 31, 0.82);
      color: #dbe7f3;
      font-size: 11px;
      font-weight: 800;
    }

    .tool-dot.active {
      border-color: rgba(20, 184, 166, 0.62);
      background: rgba(0, 133, 117, 0.9);
      color: #ffffff;
    }

    .chart-footer {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.08);
      background: #0b1726;
      color: #b5c4d6;
      font-size: 12px;
    }

    .strategy-side {
      display: grid;
      gap: 12px;
      align-content: start;
      min-width: 0;
    }

    .kv-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 12px;
    }

    .kv-table td {
      padding: 7px 0;
      border-bottom: 1px solid #edf1f5;
      vertical-align: top;
    }

    .kv-table td:first-child {
      width: 58%;
      padding-right: 8px;
    }

    .kv-table td:last-child {
      text-align: right;
      font-weight: 740;
      overflow-wrap: break-word;
      word-break: normal;
    }

    .trade-list {
      display: grid;
      gap: 8px;
    }

    .trade-row {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 4px 8px;
      align-items: center;
      padding: 8px 0;
      border-bottom: 1px solid #edf1f5;
    }

    .trade-row:last-child {
      border-bottom: 0;
    }

    .trade-row strong {
      text-align: right;
      font-size: 12px;
      overflow-wrap: break-word;
    }

    .trade-row small {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 11px;
    }

    .tabs {
      display: flex;
      gap: 22px;
      border-bottom: 1px solid var(--border);
    }

    .tab-button {
      min-height: 42px;
      border: 0;
      border-bottom: 2px solid transparent;
      background: transparent;
      color: var(--muted);
      font-weight: 760;
    }

    .tab-button.active {
      border-color: var(--teal);
      color: var(--teal);
    }

    .strategy-tabs {
      grid-column: 1 / -1;
      padding: 0 16px 16px;
    }

    .table-wrap {
      overflow: auto;
    }

    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }

    table.data-table th,
    table.data-table td {
      padding: 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      white-space: nowrap;
    }

    table.data-table th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 760;
    }

    .monitor-layout {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 14px;
    }

    .monitor-hero {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 1.3fr repeat(4, minmax(0, 1fr));
      overflow: hidden;
    }

    .monitor-timeline {
      display: grid;
      gap: 0;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .timeline-row {
      display: grid;
      grid-template-columns: 76px 42px minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      min-height: 74px;
      border-bottom: 1px solid var(--border);
    }

    .timeline-row:last-child {
      border-bottom: 0;
    }

    .timeline-time {
      color: var(--muted);
      font-weight: 650;
    }

    .timeline-node {
      display: grid;
      place-items: center;
      width: 28px;
      height: 28px;
      border-radius: 999px;
      background: var(--teal);
      color: #fff;
      font-size: 13px;
      font-weight: 900;
    }

    .timeline-node.warning {
      background: var(--amber);
    }

    .timeline-node.failed {
      background: var(--red);
    }

    .timeline-body {
      min-width: 0;
    }

    .timeline-body strong {
      display: block;
      overflow-wrap: anywhere;
    }

    .timeline-body span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
    }

    .control-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .intelligence-layout {
      display: grid;
      gap: 14px;
    }

    .filter-grid {
      display: grid;
      grid-template-columns: 240px 280px 240px 240px auto;
      gap: 12px;
      align-items: end;
    }

    .intel-grid {
      display: grid;
      grid-template-columns: 330px minmax(0, 1fr) 360px;
      gap: 14px;
      min-height: 560px;
    }

    .event-list {
      min-height: 0;
      max-height: 560px;
      overflow: auto;
      border-top: 1px solid var(--border);
    }

    .event-row {
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr) auto;
      gap: 10px;
      width: 100%;
      padding: 13px 12px;
      border: 0;
      border-bottom: 1px solid var(--border);
      background: #fff;
      text-align: left;
    }

    .event-row.active,
    .event-row:hover {
      background: #effaf8;
    }

    .event-title {
      font-weight: 780;
      line-height: 1.35;
    }

    .tag-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 7px;
    }

    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: #f6f8fb;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .intel-charts {
      display: grid;
      grid-template-rows: 1fr 1fr;
      gap: 14px;
      min-width: 0;
    }

    .chart-card svg {
      width: 100%;
      height: 240px;
    }

    .settings-layout {
      display: grid;
      gap: 14px;
    }

    .settings-top {
      display: flex;
      flex-wrap: nowrap;
      gap: 12px;
      align-items: center;
      padding: 14px;
    }

    .settings-top .field {
      flex: 0 0 280px;
    }

    .settings-top .muted {
      flex: 1 1 auto;
      min-width: 160px;
    }

    .settings-main {
      display: grid;
      grid-template-columns: 230px minmax(0, 1fr) 320px;
      gap: 14px;
      align-items: start;
    }

    .settings-nav {
      display: grid;
      padding: 10px 0;
    }

    .settings-nav button {
      display: flex;
      justify-content: space-between;
      min-height: 44px;
      padding: 10px 16px;
      border: 0;
      border-left: 3px solid transparent;
      background: transparent;
      color: var(--muted);
      text-align: left;
      font-weight: 700;
    }

    .settings-nav button.active {
      border-left-color: var(--teal);
      background: #effaf8;
      color: var(--teal-dark);
    }

    .form-grid {
      display: grid;
      gap: 16px;
    }

    .form-row {
      display: grid;
      grid-template-columns: 160px minmax(0, 1fr);
      gap: 16px;
      align-items: center;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--border);
    }

    .form-row small {
      display: block;
      margin-top: 4px;
      line-height: 1.35;
    }

    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 30px;
      padding: 5px 9px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: #f4f7fa;
      font-weight: 650;
    }

    .toggle {
      position: relative;
      width: 44px;
      height: 24px;
      border-radius: 999px;
      background: #cbd5e1;
      border: 0;
    }

    .toggle.on {
      background: var(--teal);
    }

    .toggle::after {
      position: absolute;
      top: 3px;
      left: 3px;
      width: 18px;
      height: 18px;
      border-radius: 999px;
      background: #fff;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.22);
      content: "";
      transition: transform 0.16s ease;
    }

    .toggle.on::after {
      transform: translateX(20px);
    }

    .storage-maintenance {
      display: grid;
      gap: 12px;
      align-items: center;
      padding: 16px 18px;
    }

    .storage-maintenance-header {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: end;
    }

    .cleanup-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .cleanup-panel {
      display: grid;
      gap: 10px;
      min-width: 0;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fbfcfd;
    }

    .cleanup-panel-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }

    .cleanup-list {
      display: grid;
      gap: 8px;
      max-height: 248px;
      overflow: auto;
    }

    .cleanup-option {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      padding: 9px 10px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fff;
    }

    .cleanup-option strong,
    .cleanup-option small {
      display: block;
      overflow-wrap: anywhere;
    }

    .cleanup-option small {
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
    }

    .empty-state {
      display: grid;
      gap: 8px;
      padding: 16px;
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius);
      background: #fbfcfd;
      color: var(--muted);
    }

    .message {
      padding: 10px 12px;
      border-radius: var(--radius);
      background: #f1f5f9;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }

    .message.warning {
      background: var(--amber-soft);
      color: var(--amber);
    }

    .message.error {
      background: var(--red-soft);
      color: var(--red);
    }

    .job-status {
      margin-top: 12px;
    }

    .job-status strong {
      color: var(--text);
    }

    .toast {
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 30;
      display: none;
      max-width: 360px;
      padding: 12px 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #fff;
      box-shadow: 0 18px 38px rgba(15, 23, 42, 0.18);
      color: var(--text);
      font-weight: 700;
    }

    .toast.visible {
      display: block;
    }

    .positive {
      color: var(--teal);
    }

    .negative {
      color: var(--red);
    }

    .muted {
      color: var(--muted);
    }

    @media (max-width: 1180px) {
      .app-shell {
        grid-template-columns: 80px minmax(0, 1fr);
      }

      .brand-copy,
      .nav-label,
      .sidebar-card,
      .sidebar-disclaimer {
        display: none;
      }

      .nav-item {
        justify-content: center;
      }

      .overview-layout,
      .reports-layout,
      .strategy-layout,
      .monitor-layout,
      .intel-grid,
      .settings-main,
      .cleanup-grid {
        grid-template-columns: 1fr;
      }

      .detail-rail,
      .strategy-side {
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      }

      .strategy-controls,
      .filter-grid,
      .settings-top {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 760px) {
      .app-shell {
        display: block;
      }

      .sidebar {
        position: static;
      }

      .nav {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .global-topbar {
        justify-content: flex-start;
        overflow-x: auto;
      }

      .view {
        padding: 16px;
      }

      .summary-strip,
      .report-metrics,
      .metric-strip,
      .data-cards,
      .overview-grid-2,
      .monitor-hero,
      .storage-maintenance {
        grid-template-columns: 1fr;
      }

      .summary-cell,
      .report-metric {
        border-right: 0;
        border-bottom: 1px solid var(--border);
      }

      .strategy-controls,
      .filter-grid,
      .settings-top,
      .form-row {
        grid-template-columns: 1fr;
      }

      .settings-top {
        flex-wrap: wrap;
      }

      .settings-top .field {
        flex-basis: 100%;
      }
    }
"""
