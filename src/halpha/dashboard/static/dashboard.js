    const app = document.querySelector("#halpha-dashboard-app");
    const displayTimezone = app.dataset.displayTimezone || "Asia/Shanghai";
    const endpoints = {
      overview: app.dataset.overviewEndpoint,
      health: app.dataset.healthEndpoint,
      runs: app.dataset.runsEndpoint,
      preview: app.dataset.previewEndpoint,
      stores: app.dataset.storesEndpoint,
      deletion: app.dataset.deleteEndpoint,
      dataViewerSummary: app.dataset.dataViewerSummaryEndpoint,
      dataViewerTimeline: app.dataset.dataViewerTimelineEndpoint,
      dataViewerPreview: app.dataset.dataViewerPreviewEndpoint,
      dataViewerExport: app.dataset.dataViewerExportEndpoint,
      dataViewerCollectPlan: app.dataset.dataViewerCollectPlanEndpoint,
      dataViewerCollectJobs: app.dataset.dataViewerCollectJobsEndpoint,
      strategies: app.dataset.strategiesEndpoint,
      monitor: app.dataset.monitorEndpoint,
      monitorCycles: app.dataset.monitorCyclesEndpoint,
      monitorAlerts: app.dataset.monitorAlertsEndpoint,
      jobs: app.dataset.jobsEndpoint,
      schedule: app.dataset.scheduleEndpoint,
      services: app.dataset.servicesEndpoint,
      settings: app.dataset.settingsEndpoint,
      configSelect: app.dataset.configSelectEndpoint,
      textIntel: app.dataset.textIntelligenceEndpoint,
    };
    const shared = window.HalphaDashboardShared;
    if (!shared) {
      throw new Error("Halpha dashboard shared helpers did not load.");
    }
    const strategyChart = window.HalphaDashboardStrategyChart;
    if (!strategyChart) {
      throw new Error("Halpha dashboard strategy chart helpers did not load.");
    }
    const dialogs = window.HalphaDashboardDialogs;
    if (!dialogs) {
      throw new Error("Halpha dashboard dialog helpers did not load.");
    }
    const reportsWorkflow = window.HalphaDashboardReports;
    if (!reportsWorkflow) {
      throw new Error("Halpha dashboard report helpers did not load.");
    }
    const monitorWorkflowModule = window.HalphaDashboardMonitor;
    if (!monitorWorkflowModule) {
      throw new Error("Halpha dashboard monitor helpers did not load.");
    }
    const dataViewerWorkflowModule = window.HalphaDashboardDataViewer;
    if (!dataViewerWorkflowModule) {
      throw new Error("Halpha dashboard data viewer helpers did not load.");
    }
    const {
      escapeHtml,
      text,
      statusClass,
      formatNumber,
      joinPath,
      markdownToHtml,
    } = shared;
    const reportHelpers = reportsWorkflow.createReportHelpers({joinPath, unique});
    const {isAvailableReport, reportPath, reportSourceRefs} = reportHelpers;

    const state = {
      view: "overview",
      overview: null,
      health: null,
      runs: [],
      selectedReport: null,
      selectedReportDetail: null,
      selectedReportPreview: null,
      reportJob: null,
      generatedReportRunId: null,
      reportSearchTerm: "",
      stores: [],
      deletionPlan: null,
      strategies: null,
      selectedStrategyOutput: null,
      strategyDataVisualization: null,
      strategyOperationTab: "backtest",
      strategyWindow: "all",
      strategyChartPreviewTimer: null,
      strategyChartPreviewRequest: 0,
      strategyCollectTargets: [],
      strategyCollectTimelineTimer: null,
      strategyCollectTimelineRequest: 0,
      strategyBacktestLogs: [],
      strategyCollectLogs: [],
      strategyExportLogs: [],
      monitor: null,
      monitorCycles: [],
      monitorAlerts: null,
      schedule: null,
      services: null,
      jobs: [],
      intelligence: null,
      dataViewerSummary: null,
      dataViewerStrategyTimeline: null,
      dataViewerStrategyPreview: null,
      dataViewerStrategyPlan: null,
      dataViewerStrategyJob: null,
      dataViewerStrategyExport: null,
      dataViewerIntelTimeline: null,
      dataViewerIntelPreview: null,
      dataViewerIntelPlan: null,
      dataViewerIntelJob: null,
      dataViewerIntelExport: null,
      selectedIntelTab: "overview",
      selectedIntelItem: null,
      selectedIntelPreviewIndex: 0,
      intelPreviewDisplayLimit: 30,
      intelPreviewFetchLimit: 100,
      intelPreviewLoadingMore: false,
      intelPreviewKeyword: "",
      intelPreviewCategory: "",
      intelPreviewFilterTimer: null,
      intelDatePickerOpen: false,
      intelCalendarMonth: null,
      dateRangePickerGlobalWired: false,
      intelligenceViewerTimer: null,
      settingsProfile: null,
      settingsSection: "Market data",
      settingsChanges: {},
      selectedRunArtifacts: [],
      selectedSharedStores: [],
      validationJob: null,
    };
    const monitorWorkflow = monitorWorkflowModule.createMonitorWorkflow({
      state,
      endpoints,
      loadMonitorPayload,
      postJson,
      postJob,
      showToast,
      escapeHtml,
      text,
      statusClass,
      formatTimestamp,
      label,
      metricCell,
      detailRow,
      table,
      durationBetween,
      terminalJobStatus,
    });
    const dataViewerWorkflow = dataViewerWorkflowModule.createDataViewerWorkflow({
      state,
      endpoints,
      fetchJson,
      postJson,
      showToast,
      escapeHtml,
      text,
      statusClass,
      formatNumber,
      formatTimestamp,
      label,
      metricCell,
      table,
      terminalJobStatus,
      renderStrategyOhlcvPreview,
      syncDateRangePicker: syncDateRangePickerByInputs,
    });

    function label(value) {
      return text(value, "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function statusPill(status, labelText) {
      return `<span class="status-pill ${statusClass(status)}">${escapeHtml(labelText || label(status))}</span>`;
    }

    function setPill(selector, status, labelText) {
      const node = document.querySelector(selector);
      if (!node) {
        return;
      }
      node.className = `status-pill ${statusClass(status)}`;
      node.textContent = labelText || label(status);
    }

    function metricCell(labelText, value, note = "") {
      return `<div class="summary-cell"><div class="summary-label">${escapeHtml(labelText)}</div><div class="summary-value">${escapeHtml(value)}</div>${note ? `<div class="summary-note">${escapeHtml(note)}</div>` : ""}</div>`;
    }

    function detailRow(key, value) {
      return `<div class="detail-row"><div class="detail-key">${escapeHtml(key)}</div><div class="detail-value">${escapeHtml(text(value))}</div></div>`;
    }

    function pct(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "n/a";
      }
      return `${value.toFixed(1)}%`;
    }

    function formatBytes(bytes) {
      const number = Number(bytes);
      if (!Number.isFinite(number) || number <= 0) {
        return "n/a";
      }
      const units = ["B", "KB", "MB", "GB", "TB"];
      let value = number;
      let index = 0;
      while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
      }
      return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[index]}`;
    }

    function looksLikeIsoTimestamp(value) {
      return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value);
    }

    function formatTimestamp(value) {
      return shared.formatTimestamp(value, displayTimezone);
    }

    function durationBetween(start, end) {
      const s = start ? new Date(start).getTime() : NaN;
      const e = end ? new Date(end).getTime() : NaN;
      if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) {
        return "n/a";
      }
      return formatDurationMs(e - s);
    }

    function formatDurationMs(ms) {
      const totalSeconds = Math.round(ms / 1000);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      const hours = Math.floor(minutes / 60);
      if (hours > 0) {
        return `${hours}h ${minutes % 60}m`;
      }
      if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
      }
      return `${seconds}s`;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: {
          "Accept": "application/json",
          ...(options.body ? {"Content-Type": "application/json"} : {}),
          ...(options.headers || {}),
        },
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    }

    async function postJson(url, body) {
      return fetchJson(url, {method: "POST", body: JSON.stringify(body || {})});
    }

    function showToast(message) {
      const toast = document.querySelector("#toast");
      toast.textContent = message;
      toast.classList.add("visible");
      window.setTimeout(() => toast.classList.remove("visible"), 3600);
    }

    function viewFromHash() {
      const raw = (window.location.hash || "#overview").slice(1) || "overview";
      return raw;
    }

    function setView(view) {
      const valid = ["overview", "reports", "strategies", "monitor", "intelligence", "settings"];
      state.view = valid.includes(view) ? view : "overview";
      document.querySelectorAll(".view").forEach((node) => node.classList.toggle("hidden", node.dataset.view !== state.view));
      document.querySelectorAll("[data-view-target]").forEach((node) => {
        const active = node.dataset.viewTarget === state.view;
        node.classList.toggle("active", active);
        if (active) {
          node.setAttribute("aria-current", "page");
        } else {
          node.removeAttribute("aria-current");
        }
      });
      refreshCurrentView();
    }

    async function refreshCurrentView() {
      if (state.view === "overview") return refreshOverview();
      if (state.view === "reports") return refreshReports();
      if (state.view === "strategies") return refreshStrategies();
      if (state.view === "monitor") return monitorWorkflow.refreshMonitor();
      if (state.view === "intelligence") return refreshIntelligence();
      if (state.view === "settings") return refreshSettings();
    }

    async function loadHealth() {
      try {
        state.health = await fetchJson(endpoints.health);
        const loaded = state.health?.config?.loaded !== false;
        const ref = loaded ? (state.health?.config?.ref || "Current config") : "not configured";
        document.querySelector("#config-ref").textContent = ref;
        document.querySelector("#sidebar-health-text").textContent = loaded
          ? (state.health?.status === "ok" ? "All local systems operational." : "Dashboard status needs attention.")
          : "Open Settings and load a config file.";
        if (!loaded && state.view !== "settings") {
          setHashView("settings");
        }
      } catch (error) {
        document.querySelector("#config-ref").textContent = "unavailable";
        document.querySelector("#sidebar-health-text").textContent = error.message;
      }
    }

    async function refreshOverview() {
      await Promise.allSettled([loadHealth(), loadRuns(), loadStores(), loadMonitorPayload()]);
      try {
        state.overview = await fetchJson(endpoints.overview);
      } catch (error) {
        state.overview = {status: "failed", sections: {}, warnings: [error.message], errors: [error.message]};
      }
      renderOverview();
    }

    async function loadRuns() {
      const payload = await fetchJson(endpoints.runs);
      state.runs = Array.isArray(payload.runs) ? payload.runs : [];
      return payload;
    }

    async function loadStores() {
      const payload = await fetchJson(endpoints.stores);
      state.stores = Array.isArray(payload.stores) ? payload.stores : [];
      return payload;
    }

    async function loadJobs() {
      const payload = await fetchJson(endpoints.jobs);
      state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      return payload;
    }

    async function loadDeletionPlan() {
      state.deletionPlan = await fetchJson(endpoints.deletion);
      return state.deletionPlan;
    }

    async function loadMonitorPayload() {
      const [monitor, cycles, alerts, jobs, schedule, services] = await Promise.allSettled([
        fetchJson(endpoints.monitor),
        fetchJson(endpoints.monitorCycles),
        fetchJson(endpoints.monitorAlerts),
        loadJobs(),
        fetchJson(endpoints.schedule),
        fetchJson(endpoints.services),
      ]);
      state.monitor = monitor.status === "fulfilled" ? monitor.value : null;
      state.monitorCycles = cycles.status === "fulfilled" && Array.isArray(cycles.value.cycles) ? cycles.value.cycles : [];
      state.monitorAlerts = alerts.status === "fulfilled" ? alerts.value : null;
      state.jobs = jobs.status === "fulfilled" && Array.isArray(jobs.value.jobs) ? jobs.value.jobs : [];
      state.schedule = schedule.status === "fulfilled" ? schedule.value : null;
      state.services = services.status === "fulfilled" ? services.value : null;
    }

    function renderOverview() {
      const sections = state.overview?.sections || {};
      const latest = sections.latest_run?.fields || {};
      const reportRuns = reportRecords();
      const totalReports = reportRuns.length;
      const successful = reportRuns.filter((item) => ["succeeded", "success", "available"].includes(String(item.status || "").toLowerCase())).length;
      const successRate = totalReports ? (successful / totalReports) * 100 : 0;
      const durations = reportRuns.map((item) => durationMs(item.started_at, item.finished_at)).filter(Number.isFinite);
      const averageDuration = durations.length ? formatDurationMs(durations.reduce((a, b) => a + b, 0) / durations.length) : "n/a";
      const latestReport = reportRuns[0] || {};

      setPill("#overview-report-status", latestReport.status || "missing", latestReport.status || "No report");
      document.querySelector("#overview-report-metrics").innerHTML = [
        reportMetric("Total reports", totalReports, "All time"),
        reportMetric("Daily reports", reportRuns.filter((item) => item.type === "Daily").length, "All time"),
        reportMetric("Monitor-triggered", reportRuns.filter((item) => item.type === "Monitor-triggered").length, "All time"),
        reportMetric("Manual reports", reportRuns.filter((item) => item.type === "Manual").length, "All time"),
      ].join("");
      document.querySelector("#overview-latest-report").innerHTML = [
        detailRow("Latest report", latestReport.title || "No generated report"),
        detailRow("Status", latestReport.status || "n/a"),
        detailRow("Generated", formatTimestamp(latestReport.finished_at)),
        detailRow("Duration", durationBetween(latestReport.started_at, latestReport.finished_at)),
        detailRow("Average duration", averageDuration),
        detailRow("Success rate", totalReports ? pct(successRate) : "n/a"),
      ].join("");
      renderReportTrend("#overview-report-chart", reportRuns);
      document.querySelector("#open-latest-report").onclick = () => {
        setHashView("reports");
        if (latestReport.run_id) {
          selectReport(latestReport.run_id);
        }
      };
      if (!state.reportJob) {
        state.reportJob = latestReportJob();
      }
      renderReportJob(state.reportJob);

      renderRuntime(sections);
      renderOverviewMonitor();
      renderOverviewData();
      renderAttention();
    }

    function reportMetric(title, value, note) {
      return `<div class="report-metric"><div class="summary-label">${escapeHtml(title)}</div><div class="metric-big">${escapeHtml(formatNumber(value))}</div><div class="summary-note">${escapeHtml(note)}</div></div>`;
    }

    function durationMs(start, end) {
      const s = start ? new Date(start).getTime() : NaN;
      const e = end ? new Date(end).getTime() : NaN;
      return Number.isFinite(s) && Number.isFinite(e) && e >= s ? e - s : NaN;
    }

    function renderRuntime(sections) {
      const latest = sections.latest_run?.fields || {};
      const selection = latest.selection || {};
      const now = Date.now();
      const started = latest.started_at || latest.finished_at;
      const startedTime = started ? new Date(started).getTime() : NaN;
      const uptime = Number.isFinite(startedTime) ? formatDurationMs(now - startedTime) : "n/a";
      const storeRecords = state.stores.reduce((sum, store) => sum + numericRecordCount(store), 0);
      const dataSizeLabel = storeRecords ? `${formatNumber(storeRecords)} records` : "n/a";
      document.querySelector("#overview-runtime").innerHTML = [
        detailRow("Overview run source", label(selection.label || "n/a")),
        detailRow("Overview run", latest.run_id || "n/a"),
        detailRow("Latest run", selection.latest_run_id || "n/a"),
        detailRow("Latest successful run", selection.latest_successful_run_id || "n/a"),
        detailRow("Service start time", formatTimestamp(started)),
        detailRow("Historical runtime", state.runs.length ? `${state.runs.length} runs recorded` : "No run history"),
        detailRow("Current uptime", uptime),
        detailRow("Data size", dataSizeLabel),
        detailRow("Memory usage", "not collected"),
        detailRow("Storage usage", storeRecords ? "tracked by record count" : "not collected"),
      ].join("");
    }

    function renderOverviewMonitor() {
      const health = state.monitor?.health?.fields || {};
      const latest = state.monitor?.latest_cycle || {};
      const services = state.services?.services || {};
      const monitorService = services.monitor || {};
      const scheduleService = services.schedule || {};
      const status = monitorService.status || latest.status || health.latest_cycle_status || state.monitor?.status || "partial";
      const schedule = state.schedule || {};
      const scheduleLabel = schedule.enabled
        ? formatTimestamp(schedule.next_run_at)
        : "No daily report scheduled";
      setPill("#overview-monitor-pill", status, status);
      document.querySelector("#overview-monitor").innerHTML = [
        detailRow("Monitor service", label(monitorService.lifecycle_status || status)),
        detailRow("Monitor heartbeat", formatTimestamp(monitorService.heartbeat_at)),
        detailRow("Latest cycle", label(latest.status || health.latest_cycle_status || "n/a")),
        detailRow("Cycle count", health.cycle_count ?? state.monitorCycles.length),
        detailRow("Last trigger time", formatTimestamp(latest.finished_at || latest.started_at)),
        detailRow("Schedule service", label(scheduleService.lifecycle_status || "n/a")),
        detailRow("Next scheduled report", scheduleLabel),
        detailRow("Recent alerts", monitorWorkflow.alertCount(state.monitorAlerts)),
      ].join("");
    }

    function renderOverviewData() {
      const stores = state.stores;
      const categories = [
        ["OHLCV", "ohlcv_history"],
        ["Text", "text_event_history"],
        ["Derivatives", "derivatives_market_history"],
        ["On-chain", "onchain_flow_history"],
        ["Macro", "macro_calendar_history"],
        ["Outcomes", "outcome_history"],
      ];
      document.querySelector("#overview-data-cards").innerHTML = categories.map(([labelText, name]) => {
        const store = stores.find((item) => item.name === name) || {};
        const records = numericRecordCount(store);
        return `<div class="data-card"><div class="data-card-title">${escapeHtml(labelText)}</div><div class="data-card-value">${records ? formatNumber(records) : "n/a"}</div>${statusPill(store.status || "missing", store.status || "missing")}</div>`;
      }).join("");
      const warnings = stores.flatMap((store) => store.warnings || []);
      const errors = stores.flatMap((store) => store.errors || []);
      setPill("#overview-data-pill", errors.length ? "failed" : warnings.length ? "warning" : "available", errors.length ? "Issues" : warnings.length ? "Warnings" : "Good");
      document.querySelector("#overview-quality").innerHTML = `
        <div class="summary-strip" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
          ${metricCell("Validation pass", Math.max(0, stores.length - warnings.length - errors.length), "stores")}
          ${metricCell("Warnings", warnings.length, "latest state")}
          ${metricCell("Errors", errors.length, "latest state")}
        </div>`;
    }

    function numericRecordCount(store) {
      const fields = store?.fields || {};
      const candidates = [fields.records, fields.record_count, fields.inserted_records, fields.incoming_records];
      const value = candidates.find((item) => Number.isFinite(Number(item)));
      return value === undefined ? 0 : Number(value);
    }

    function renderAttention() {
      const items = [];
      state.stores.forEach((store) => {
        (store.warnings || []).slice(0, 1).forEach((warning) => items.push({severity: "warning", title: `${store.title || store.name}`, copy: warning, action: "Review data issues", view: "intelligence"}));
        (store.errors || []).slice(0, 1).forEach((error) => items.push({severity: "failed", title: `${store.title || store.name}`, copy: error, action: "Review data issues", view: "intelligence"}));
      });
      (state.monitor?.warnings || []).slice(0, 1).forEach((warning) => items.push({severity: "warning", title: "Monitor warning", copy: warning, action: "Check monitor run", view: "monitor"}));
      if (!items.length) {
        items.push({severity: "available", title: "No urgent issues", copy: "Dashboard has no current high-priority attention item.", action: "Open reports", view: "reports"});
      }
      const visible = items.slice(0, 3);
      setPill("#attention-count", visible.length > 1 ? "warning" : "available", `${visible.length}`);
      document.querySelector("#attention-list").innerHTML = visible.map((item) => `
        <li class="attention-item">
          <div class="attention-title"><span>${escapeHtml(item.title)}</span>${statusPill(item.severity, item.severity)}</div>
          <div class="attention-copy">${escapeHtml(item.copy)}</div>
          <button class="ghost-button" type="button" data-view-shortcut="${escapeHtml(item.view)}" style="width:100%; margin-top:10px;">${escapeHtml(item.action)}</button>
        </li>`).join("");
      wireShortcutButtons();
    }

    async function refreshReports() {
      await Promise.allSettled([loadRuns(), loadJobs()]);
      if (!state.reportJob) {
        state.reportJob = latestReportJob();
      }
      renderReportJob(state.reportJob);
      renderReportLibrary();
      const reports = reportRecords();
      if (!reports.length) {
        state.selectedReport = null;
        document.querySelector("#selected-report-kicker").textContent = "No report selected";
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">No generated reports are available yet. Use Generate report to create a new report.</div>`;
        document.querySelector("#report-details").innerHTML = "";
        document.querySelector("#report-outline").innerHTML = "";
        document.querySelector("#report-sources").innerHTML = "";
      } else if (!state.selectedReport || !reports.some((item) => item.run_id === state.selectedReport.run_id)) {
        await selectReport(reports[0].run_id);
      } else {
        await selectReport(state.selectedReport.run_id);
      }
    }

    function reportRecords() {
      return reportHelpers.reportRecords(state.runs);
    }

    function renderReportLibrary() {
      const query = document.querySelector("#report-search").value.trim().toLowerCase();
      const records = reportRecords().filter((item) => !query || `${item.title} ${item.run_id}`.toLowerCase().includes(query));
      const groups = ["Daily", "Monitor-triggered", "Manual"];
      document.querySelector("#report-library-groups").innerHTML = groups.map((group) => {
        const items = records.filter((item) => item.type === group);
        return `<section><h3 class="group-title"><span>${escapeHtml(group)}</span><span class="tag">${items.length}</span></h3>${items.slice(0, 12).map((item) => {
          const generated = item.run_id === state.generatedReportRunId;
          return `
          <button class="report-row ${state.selectedReport?.run_id === item.run_id ? "active" : ""}" type="button" data-report-run-id="${escapeHtml(item.run_id)}">
            <span class="report-row-title"><span class="health-dot"></span>${escapeHtml(item.title)}${generated ? ` <span class="tag">new</span>` : ""}</span>
            <span class="report-row-meta">${escapeHtml(formatTimestamp(item.finished_at || item.started_at))}</span>
          </button>`;
        }).join("") || `<div class="message">No ${escapeHtml(group.toLowerCase())} reports.</div>`}</section>`;
      }).join("");
      document.querySelectorAll("[data-report-run-id]").forEach((button) => button.addEventListener("click", () => selectReport(button.dataset.reportRunId)));
    }

    async function selectReport(runId) {
      const run = reportRecords().find((item) => item.run_id === runId) || {run_id: runId};
      state.selectedReport = run;
      state.selectedReportDetail = null;
      renderReportLibrary();
      document.querySelector("#selected-report-kicker").textContent = `${run.type || "Report"} - ${formatTimestamp(run.finished_at || run.started_at)}`;
      document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Loading rendered report.</div>`;
      try {
        state.selectedReportDetail = await fetchJson(`${endpoints.runs}/${encodeURIComponent(runId)}`);
      } catch (_error) {
        state.selectedReportDetail = null;
      }
      renderReportDetails(run, state.selectedReportDetail);
      const path = run.report_path || reportPath(run);
      try {
        const preview = await fetchJson(`${endpoints.preview}?path=${encodeURIComponent(path)}`);
        state.selectedReportPreview = preview;
        renderReportPreview(preview, run);
      } catch (error) {
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Report preview is unavailable. ${escapeHtml(error.message)}</div>`;
      }
    }

    function renderReportDetails(run, detail) {
      const refs = reportSourceRefs(run, detail);
      document.querySelector("#report-details").innerHTML = [
        detailRow("Type", run.type),
        detailRow("Run", run.run_id),
        detailRow("Run role", runRole(run)),
        detailRow("Status", run.status),
        detailRow("Duration", durationBetween(run.started_at, run.finished_at)),
        detailRow("Generated", formatTimestamp(run.finished_at || run.started_at)),
        detailRow("Origin", run.codex_status === "skipped" ? "Local pipeline" : "Codex report"),
      ].join("");
      document.querySelector("#report-sources").innerHTML = refs.length
        ? refs.slice(0, 12).map((source) => `<li class="compact-row">${escapeHtml(source)}</li>`).join("")
        : `<li class="message">No source refs recorded for this report.</li>`;
    }

    function runRole(run) {
      const latest = run?.latest_state || {};
      if (latest.is_latest_run && latest.is_latest_successful_run) return "Latest run and latest successful run";
      if (latest.is_latest_run) return "Latest run";
      if (latest.is_latest_successful_run) return "Latest successful run";
      return "Historical run";
    }

    function renderReportPreview(preview, run) {
      const content = typeof preview.preview === "string" ? preview.preview : "";
      if (!content) {
        const messages = [...(preview.warnings || []), ...(preview.errors || [])];
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">${escapeHtml(messages.join(" ") || "No readable report content is recorded for this run.")}</div>`;
        renderOutline("");
        return;
      }
      const markdown = typeof content === "string" ? content : JSON.stringify(content, null, 2);
      document.querySelector("#report-reader").innerHTML = `<article class="markdown-reader">${markdownToHtml(markdown, state.reportSearchTerm)}</article>`;
      renderOutline(markdown);
    }

    function renderOutline(markdown) {
      const headings = markdown.split(/\r?\n/).filter((line) => /^#{1,3}\s+/.test(line)).slice(0, 12);
      document.querySelector("#report-outline").innerHTML = headings.length ? headings.map((line, index) => {
        const title = line.replace(/^#{1,3}\s+/, "");
        return `<li><a href="#" data-outline-index="${index}">${escapeHtml(title)}</a></li>`;
      }).join("") : `<li class="message">No outline extracted.</li>`;
    }

    async function deleteSelectedReport() {
      if (!state.selectedReport?.run_id) {
        showToast("Select a report first.");
        return;
      }
      const ok = await dialogs.confirmAction({
        title: "Delete report artifacts",
        message: "Delete this report's single-run artifacts? Shared data is not deleted.",
        confirmLabel: "Delete report",
        danger: true,
      });
      if (!ok) return;
      try {
        const result = await postJson(endpoints.deletion, {
          kind: "run_artifacts",
          run_ids: [state.selectedReport.run_id],
          confirm: "DELETE RUN DATA",
        });
        showToast(`Deletion ${result.status || "submitted"}.`);
        state.selectedReport = null;
        await refreshReports();
      } catch (error) {
        showToast(`Delete failed: ${error.message}`);
      }
    }

    function downloadSelectedReport() {
      const preview = state.selectedReportPreview;
      if (!preview || typeof preview.preview !== "string") {
        showToast("No report text is available to download.");
        return;
      }
      const blob = new Blob([preview.preview], {type: "text/markdown"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${state.selectedReport?.run_id || "report"}.md`;
      link.click();
      URL.revokeObjectURL(url);
    }

    async function refreshStrategies() {
      try {
        const [strategies] = await Promise.all([
          fetchJson(endpoints.strategies),
          dataViewerWorkflow.loadDataViewerSummary(),
        ]);
        state.strategies = strategies;
      } catch (error) {
        state.strategies = {status: "failed", errors: [error.message], standalone: {backtests: [], experiments: []}, commands: {options: {}}};
        await dataViewerWorkflow.loadDataViewerSummary();
      }
      renderStrategyControls();
      renderStrategies();
      dataViewerWorkflow.renderStrategyViewer();
    }

    function strategyOutputs() {
      const standalone = state.strategies?.standalone || {};
      const backtests = Array.isArray(standalone.backtests) ? standalone.backtests : [];
      const pipeline = state.strategies?.pipeline?.artifacts || [];
      return [...backtests, ...pipeline].filter(Boolean);
    }

    function renderStrategyControls() {
      const options = state.strategies?.commands?.options || {};
      const sources = options.sources || ["binance"];
      const symbols = options.symbols || [];
      const timeframes = options.timeframes || [];
      fillDatalist("#strategy-ohlcv-source-options", sources);
      fillSelect("#strategy-symbol", symbols);
      fillSelect("#strategy-timeframe", timeframes);
      fillSelect("#strategy-name", ["", ...(options.strategy_names || [])], {"": "OHLCV only"});
      fillSelect("#strategy-chart-symbol", symbols);
      fillSelect("#strategy-chart-timeframe", timeframes);
      fillSelect("#strategy-collect-symbol", symbols);
      fillSelect("#strategy-collect-timeframe", timeframes);
      fillSelect("#strategy-export-symbol", symbols);
      fillSelect("#strategy-export-timeframe", timeframes);
      ensureStrategyCollectTargets(symbols, timeframes);
      renderStrategyCollectTargets();
      syncStrategyOperationTabs();
      syncStrategyDataInputs(false);
      syncStrategyRangePresets(false);
      ["#strategy-symbol", "#strategy-timeframe", "#strategy-name"].forEach((selector) => {
        document.querySelector(selector).onchange = () => {
          state.selectedStrategyOutput = null;
          if (selector !== "#strategy-name") {
            state.strategyDataVisualization = null;
            syncStrategyDataInputs(true);
            dataViewerWorkflow.ensureStrategyDefaultRange?.(true);
            dataViewerWorkflow.renderStrategyViewer();
            queueStrategyChartRefresh();
            if (!state.strategyCollectTargets.length) {
              ensureStrategyCollectTargets(symbols, timeframes);
              renderStrategyCollectTargets();
            }
          }
          strategyChart.resetCandlestickView("#backtest-chart");
          renderStrategies();
        };
      });
      document.querySelector("#strategy-range").value = state.strategyWindow;
      document.querySelector("#strategy-range").onchange = () => setStrategyWindow(document.querySelector("#strategy-range").value);
      queueStrategyChartRefresh();
    }

    function syncStrategyDataInputs(force = false) {
      const symbol = document.querySelector("#strategy-symbol")?.value || "";
      const timeframe = document.querySelector("#strategy-timeframe")?.value || "";
      const source = defaultStrategySource();
      setInputValue("#strategy-chart-source", source, false);
      setInputValue("#strategy-chart-symbol", symbol, force);
      setInputValue("#strategy-chart-timeframe", timeframe, force);
      setInputValue("#strategy-export-symbol", symbol, force);
      setInputValue("#strategy-export-timeframe", timeframe, force);
      setInputValue("#strategy-collect-source", source, false);
      setInputValue("#strategy-export-source", source, false);
    }

    function setInputValue(selector, value, force) {
      const node = document.querySelector(selector);
      if (!node || !value) return;
      if (force || !node.value) node.value = value;
    }

    function fillSelect(selector, values, labels = {}) {
      const node = document.querySelector(selector);
      if (!node) return;
      const current = node.value;
      node.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(labels[value] || value)}</option>`).join("");
      if (values.includes(current)) node.value = current;
    }

    function fillDatalist(selector, values) {
      const node = document.querySelector(selector);
      if (!node) return;
      node.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("");
    }

    function defaultStrategySource() {
      const sources = state.strategies?.commands?.options?.sources || [];
      return sources[0] || "binance";
    }

    function ensureStrategyCollectTargets(symbols, timeframes) {
      if (state.strategyCollectTargets.length) return;
      const symbol = document.querySelector("#strategy-symbol")?.value || symbols[0] || "";
      const timeframe = document.querySelector("#strategy-timeframe")?.value || timeframes[0] || "";
      if (!symbol || !timeframe) return;
      state.strategyCollectTargets = [{id: nextCollectTargetId(), symbol, timeframe}];
    }

    function nextCollectTargetId() {
      return `target-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    }

    function renderStrategyCollectTargets() {
      const target = document.querySelector("#strategy-collect-targets");
      if (!target) return;
      target.innerHTML = state.strategyCollectTargets.length
        ? state.strategyCollectTargets.map((item) => `
          <div class="collect-target-row" data-collect-target-id="${escapeHtml(item.id)}">
            <span class="collect-target-symbol">${escapeHtml(item.symbol)}</span>
            <span class="collect-target-timeframe">${escapeHtml(item.timeframe)}</span>
            <button class="icon-button" type="button" data-collect-target-remove="${escapeHtml(item.id)}" title="Remove target" aria-label="Remove ${escapeHtml(item.symbol)} ${escapeHtml(item.timeframe)}">x</button>
          </div>`).join("")
        : `<div class="message">Add at least one symbol and timeframe to collect OHLCV data.</div>`;
      document.querySelectorAll("[data-collect-target-remove]").forEach((button) => {
        button.onclick = () => {
          const id = button.dataset.collectTargetRemove;
          state.strategyCollectTargets = state.strategyCollectTargets.filter((item) => item.id !== id);
          renderStrategyCollectTargets();
          queueStrategyCollectTimelineRefresh();
        };
      });
      queueStrategyCollectTimelineRefresh();
    }

    function addStrategyCollectTarget() {
      const symbol = document.querySelector("#strategy-collect-symbol")?.value || "";
      const timeframe = document.querySelector("#strategy-collect-timeframe")?.value || "";
      if (!symbol || !timeframe) {
        showToast("Select a symbol and timeframe first.");
        return;
      }
      const duplicate = state.strategyCollectTargets.some((item) => item.symbol === symbol && item.timeframe === timeframe);
      if (duplicate) {
        showToast(`${symbol} ${timeframe} is already selected.`);
        return;
      }
      state.strategyCollectTargets.push({id: nextCollectTargetId(), symbol, timeframe});
      renderStrategyCollectTargets();
    }

    function strategyOhlcvCoverage() {
      const stores = Array.isArray(state.dataViewerSummary?.stores) ? state.dataViewerSummary.stores : [];
      return stores.find((store) => store.data_type === "ohlcv")?.coverage || {};
    }

    function syncStrategyRangePresets(force = false) {
      applyRangePreset("#strategy-collect-range", "#strategy-collect-start", "#strategy-collect-end", force);
      applyRangePreset("#strategy-export-range", "#strategy-export-start", "#strategy-export-end", force);
    }

    function presetDateRange(value) {
      const coverage = strategyOhlcvCoverage();
      const anchor = parseIsoDate(coverage.range_end) || new Date();
      if (value === "custom") return null;
      if (value === "all") {
        if (coverage.range_start && coverage.range_end) {
          return {start: coverage.range_start, end: coverage.range_end};
        }
        return {
          start: toIsoSecond(new Date(anchor.getTime() - 7 * 24 * 3600 * 1000)),
          end: toIsoSecond(anchor),
        };
      }
      const days = value === "1d" ? 1 : value === "7d" ? 7 : value === "30d" ? 30 : value === "180d" ? 180 : 7;
      return {
        start: toIsoSecond(new Date(anchor.getTime() - days * 24 * 3600 * 1000)),
        end: toIsoSecond(anchor),
      };
    }

    function applyRangePreset(rangeSelector, startSelector, endSelector, force = false) {
      const range = document.querySelector(rangeSelector);
      const start = document.querySelector(startSelector);
      const end = document.querySelector(endSelector);
      if (!range || !start || !end) return;
      if (!force && start.value && end.value) {
        syncDateRangePickerByInputs(startSelector, endSelector);
        return;
      }
      const value = range.value || "all";
      const nextRange = presetDateRange(value);
      if (!nextRange) {
        syncDateRangePickerByInputs(startSelector, endSelector);
        return;
      }
      start.value = nextRange.start;
      end.value = nextRange.end;
      syncDateRangePickerByInputs(startSelector, endSelector);
    }

    function wireDateRangePickers() {
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        if (field.dataset.rangePickerWired === "true") {
          syncDateRangePickerLabel(field);
          return;
        }
        field.dataset.rangePickerWired = "true";
        const controls = dateRangePickerControls(field);
        controls.trigger?.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const isOpening = controls.popover?.classList.contains("hidden");
          closeDateRangePickers();
          if (isOpening) {
            initializeDateRangePickerState(field);
            renderDateRangePicker(field);
            controls.popover?.classList.remove("hidden");
            controls.trigger?.setAttribute("aria-expanded", "true");
          }
        });
        controls.popover?.addEventListener("click", (event) => {
          event.stopPropagation();
          handleDateRangePickerClick(event, field);
        });
        controls.popover?.addEventListener("input", (event) => handleDateRangePickerInput(event, field));
        syncDateRangePickerLabel(field);
      });
      if (!state.dateRangePickerGlobalWired) {
        state.dateRangePickerGlobalWired = true;
        document.addEventListener("click", (event) => {
          if (!event.target.closest("[data-date-range-picker]")) {
            closeDateRangePickers();
          }
        });
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape") closeDateRangePickers();
        });
      }
    }

    function dateRangePickerControls(field) {
      return {
        start: document.getElementById(field.dataset.startInput || ""),
        end: document.getElementById(field.dataset.endInput || ""),
        preset: document.getElementById(field.dataset.presetInput || ""),
        trigger: field.querySelector(".range-picker-trigger"),
        label: field.querySelector("[data-range-picker-label]"),
        popover: field.querySelector(".range-picker-popover"),
      };
    }

    function syncDateRangePickerByInputs(startSelector, endSelector) {
      const startId = selectorToId(startSelector);
      const endId = selectorToId(endSelector);
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        if (field.dataset.startInput === startId && field.dataset.endInput === endId) {
          syncDateRangePickerLabel(field);
          if (!field.querySelector(".range-picker-popover")?.classList.contains("hidden")) {
            renderDateRangePicker(field);
          }
        }
      });
    }

    function selectorToId(selector) {
      return String(selector || "").replace(/^#/, "");
    }

    function syncDateRangePickerLabel(field) {
      const controls = dateRangePickerControls(field);
      if (!controls.label) return;
      const startLabel = compactUtcDateTime(controls.start?.value);
      const endLabel = compactUtcDateTime(controls.end?.value);
      controls.label.textContent = startLabel && endLabel ? `${startLabel} -> ${endLabel}` : "Choose range";
      if (controls.trigger) {
        controls.trigger.title = startLabel && endLabel ? `${startLabel} UTC to ${endLabel} UTC` : "Choose start and end time";
        controls.trigger.setAttribute("aria-expanded", controls.popover?.classList.contains("hidden") ? "false" : "true");
      }
    }

    function initializeDateRangePickerState(field) {
      const controls = dateRangePickerControls(field);
      const startDate = parseIsoDate(controls.start?.value);
      const endDate = parseIsoDate(controls.end?.value);
      field.dataset.pendingStart = startDate ? utcDateKey(startDate) : "";
      field.dataset.pendingEnd = endDate ? utcDateKey(endDate) : "";
      field.dataset.pendingStartTime = startDate ? utcTimeKey(startDate) : "00:00:00";
      field.dataset.pendingEndTime = endDate ? utcTimeKey(endDate) : "23:59:59";
      field.dataset.pendingPreset = "";
      const monthKey = (field.dataset.pendingStart || field.dataset.pendingEnd || utcDateKey(new Date())).slice(0, 7);
      field.dataset.visibleMonth = monthKey;
    }

    function renderDateRangePicker(field) {
      const controls = dateRangePickerControls(field);
      const popover = controls.popover;
      if (!popover) return;
      const monthKey = field.dataset.visibleMonth || utcDateKey(new Date()).slice(0, 7);
      const [year, month] = monthKey.split("-").map((part) => Number(part));
      const firstDay = new Date(Date.UTC(year, month - 1, 1));
      const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
      const leading = firstDay.getUTCDay();
      const cells = [];
      for (let index = 0; index < leading; index += 1) {
        cells.push(`<span class="range-picker-day empty"></span>`);
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        const dateKey = `${monthKey}-${String(day).padStart(2, "0")}`;
        const classes = ["range-picker-day", dateRangeDayClass(field, dateKey)].filter(Boolean).join(" ");
        cells.push(`<button class="${classes}" type="button" data-range-day="${escapeHtml(dateKey)}">${day}</button>`);
      }
      popover.innerHTML = `
        <div class="range-picker-head">
          <button class="ghost-button compact-button" type="button" data-range-month-shift="-1">Prev</button>
          <strong>${escapeHtml(monthLabel(monthKey))}</strong>
          <button class="ghost-button compact-button" type="button" data-range-month-shift="1">Next</button>
        </div>
        <div class="range-picker-presets">
          ${rangeQuickButtons()}
        </div>
        <div class="range-picker-weekdays">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => `<span>${day}</span>`).join("")}</div>
        <div class="range-picker-grid">${cells.join("")}</div>
        <div class="range-picker-times">
          <label>Start time<input class="text-input" type="time" step="1" data-range-start-time value="${escapeHtml(normalizeTime(field.dataset.pendingStartTime, "00:00:00"))}"></label>
          <label>End time<input class="text-input" type="time" step="1" data-range-end-time value="${escapeHtml(normalizeTime(field.dataset.pendingEndTime, "23:59:59"))}"></label>
        </div>
        <div class="range-picker-actions">
          <span class="range-picker-hint">Click two dates to set one UTC range.</span>
          <button class="ghost-button compact-button" type="button" data-range-cancel>Cancel</button>
          <button class="primary-button compact-button" type="button" data-range-apply>Apply</button>
        </div>
      `;
    }

    function rangeQuickButtons() {
      return [
        ["1d", "1D"],
        ["7d", "7D"],
        ["30d", "30D"],
        ["180d", "180D"],
      ].map(([value, labelText]) => `<button class="ghost-button compact-button" type="button" data-range-quick="${value}">${labelText}</button>`).join("");
    }

    function dateRangeDayClass(field, dateKey) {
      const start = field.dataset.pendingStart || "";
      const end = field.dataset.pendingEnd || "";
      if (!start && !end) return "";
      const normalizedEnd = end || start;
      const classes = [];
      if (dateKey === start) classes.push("range-start");
      if (dateKey === normalizedEnd) classes.push("range-end");
      if (dateKey > start && dateKey < normalizedEnd) classes.push("in-range");
      if (dateKey === start || dateKey === normalizedEnd || (dateKey > start && dateKey < normalizedEnd)) {
        classes.push("selected");
      }
      return classes.join(" ");
    }

    function handleDateRangePickerClick(event, field) {
      const monthButton = event.target.closest("[data-range-month-shift]");
      if (monthButton) {
        field.dataset.visibleMonth = shiftMonthKey(field.dataset.visibleMonth, Number(monthButton.dataset.rangeMonthShift) || 0);
        renderDateRangePicker(field);
        return;
      }
      const quickButton = event.target.closest("[data-range-quick]");
      if (quickButton) {
        applyDateRangeQuick(field, quickButton.dataset.rangeQuick);
        renderDateRangePicker(field);
        return;
      }
      const dayButton = event.target.closest("[data-range-day]");
      if (dayButton) {
        applyDateRangeDay(field, dayButton.dataset.rangeDay);
        renderDateRangePicker(field);
        return;
      }
      if (event.target.closest("[data-range-cancel]")) {
        closeDateRangePickers();
        return;
      }
      if (event.target.closest("[data-range-apply]")) {
        applyDateRangePickerSelection(field);
      }
    }

    function handleDateRangePickerInput(event, field) {
      if (event.target.matches("[data-range-start-time]")) {
        field.dataset.pendingStartTime = normalizeTime(event.target.value, "00:00:00");
      }
      if (event.target.matches("[data-range-end-time]")) {
        field.dataset.pendingEndTime = normalizeTime(event.target.value, "23:59:59");
      }
    }

    function applyDateRangeDay(field, dateKey) {
      field.dataset.pendingPreset = "custom";
      const start = field.dataset.pendingStart || "";
      const end = field.dataset.pendingEnd || "";
      if (!start || end) {
        field.dataset.pendingStart = dateKey;
        field.dataset.pendingEnd = "";
        return;
      }
      if (dateKey < start) {
        field.dataset.pendingStart = dateKey;
        field.dataset.pendingEnd = start;
        return;
      }
      field.dataset.pendingEnd = dateKey;
    }

    function applyDateRangeQuick(field, value) {
      const days = value === "1d" ? 1 : value === "7d" ? 7 : value === "30d" ? 30 : value === "180d" ? 180 : 7;
      const controls = dateRangePickerControls(field);
      const anchor = parseIsoDate(controls.end?.value) || new Date();
      const start = new Date(anchor.getTime() - days * 24 * 3600 * 1000);
      field.dataset.pendingStart = utcDateKey(start);
      field.dataset.pendingEnd = utcDateKey(anchor);
      field.dataset.pendingStartTime = utcTimeKey(start);
      field.dataset.pendingEndTime = utcTimeKey(anchor);
      field.dataset.visibleMonth = field.dataset.pendingStart.slice(0, 7);
      field.dataset.pendingPreset = value;
    }

    function applyDateRangePickerSelection(field) {
      const controls = dateRangePickerControls(field);
      if (!controls.start || !controls.end) return;
      const startDate = field.dataset.pendingStart || field.dataset.pendingEnd;
      const endDate = field.dataset.pendingEnd || field.dataset.pendingStart;
      if (!startDate || !endDate) {
        showToast("Choose at least one date for the time window.");
        return;
      }
      const startValue = `${startDate}T${normalizeTime(field.dataset.pendingStartTime, "00:00:00")}Z`;
      const endValue = `${endDate}T${normalizeTime(field.dataset.pendingEndTime, "23:59:59")}Z`;
      if (Date.parse(startValue) > Date.parse(endValue)) {
        showToast("Start time must be before end time.");
        return;
      }
      controls.start.value = startValue;
      controls.end.value = endValue;
      if (controls.preset) {
        controls.preset.value = field.dataset.pendingPreset && field.dataset.pendingPreset !== "custom"
          ? field.dataset.pendingPreset
          : "custom";
      }
      syncDateRangePickerLabel(field);
      closeDateRangePickers();
      dispatchInputChange(controls.start);
      dispatchInputChange(controls.end);
    }

    function dispatchInputChange(input) {
      input.dispatchEvent(new Event("change", {bubbles: true}));
    }

    function closeDateRangePickers() {
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        const controls = dateRangePickerControls(field);
        controls.popover?.classList.add("hidden");
        controls.trigger?.setAttribute("aria-expanded", "false");
      });
    }

    function utcDateKey(date) {
      return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
    }

    function utcTimeKey(date) {
      return `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}:${String(date.getUTCSeconds()).padStart(2, "0")}`;
    }

    function compactUtcDateTime(value) {
      const date = parseIsoDate(value);
      if (!date) return value ? String(value) : "";
      return `${utcDateKey(date)} ${utcTimeKey(date)}`;
    }

    function normalizeTime(value, fallback) {
      const raw = String(value || "").trim();
      if (/^\d{2}:\d{2}:\d{2}$/.test(raw)) return raw;
      if (/^\d{2}:\d{2}$/.test(raw)) return `${raw}:00`;
      return fallback;
    }

    function monthLabel(monthKey) {
      const [year, month] = String(monthKey || "").split("-").map((part) => Number(part));
      if (!year || !month) return "Select range";
      const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
      return `${monthNames[month - 1]} ${year}`;
    }

    function shiftMonthKey(monthKey, delta) {
      const [year, month] = String(monthKey || utcDateKey(new Date()).slice(0, 7)).split("-").map((part) => Number(part));
      const shifted = new Date(Date.UTC(year || new Date().getUTCFullYear(), (month || 1) - 1 + delta, 1));
      return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
    }

    function parseIsoDate(value) {
      const time = value ? new Date(value) : null;
      return time && Number.isFinite(time.getTime()) ? time : null;
    }

    function toIsoSecond(date) {
      return date.toISOString().replace(/\.\d{3}Z$/, "Z");
    }

    function renderStrategies() {
      const outputs = strategyOutputs();
      const selected = state.strategyOperationTab === "backtest" ? selectedStrategyOutput(outputs) : null;
      if (state.strategyOperationTab === "backtest") {
        state.selectedStrategyOutput = selected;
      }
      syncStrategyControls(selected);
      syncStrategyDataInputs(false);
      const metrics = strategyMetrics(selected);
      document.querySelector("#strategy-metrics").innerHTML = [
        metricCell("Total return", metrics.totalReturn, "strategy"),
        metricCell("Max drawdown", metrics.drawdown, "risk"),
        metricCell("Sharpe", metrics.sharpe, "risk adjusted"),
        metricCell("Win rate", metrics.winRate, "trades"),
        metricCell("Profit factor", metrics.profitFactor, "gross"),
        metricCell("Trades", metrics.trades, "count"),
      ].join("");
      const vis = visibleStrategyVisualization(selected);
      const identityLabel = [vis.symbol, vis.timeframe].filter(Boolean).join(" - ");
      document.querySelector("#strategy-chart-title").textContent = identityLabel ? `${identityLabel} - Halpha` : "OHLCV data viewer";
      document.querySelector("#strategy-chart-meta").textContent = strategyChartMeta(selected, vis);
      document.querySelector("#strategy-quote-label").textContent = strategyChart.quoteAsset(vis.symbol);
      document.querySelector("#strategy-window-label").textContent = strategyChart.strategyWindowLabel(
        vis,
        displayTimezone,
      );
      document.querySelector("#strategy-chart-clock").textContent = displayTimezone;
      syncStrategyWindowControls();
      strategyChart.renderCandlestickSvg("#backtest-chart", vis, {displayTimezone});
      renderStrategyParams(selected, vis);
      renderRecentTrades(vis);
      renderBacktestRuns(outputs);
      renderStrategyTab("trades");
    }

    function strategyChartMeta(selected, vis) {
      if (state.strategyOperationTab === "backtest" && selected && vis.strategy_name) {
        return `${vis.strategy_name} - ${vis.status || selected?.status || "partial"}`;
      }
      const bars = Array.isArray(vis.bars) ? vis.bars.length : 0;
      if (bars) {
        const source = vis.source || document.querySelector("#strategy-chart-source")?.value || "shared store";
        return `OHLCV only - ${formatNumber(bars)} candles from ${source}.`;
      }
      if (state.strategyOperationTab === "backtest") {
        return "OHLCV-only chart. Select a backtest run to overlay operations.";
      }
      return "OHLCV-only chart. Collection and export settings do not select a backtest.";
    }

    function setStrategyOperationTab(tab) {
      state.strategyOperationTab = ["backtest", "collect", "export"].includes(tab) ? tab : "backtest";
      syncStrategyOperationTabs();
      if (state.strategyOperationTab === "collect") {
        syncStrategyRangePresets(false);
        queueStrategyCollectTimelineRefresh();
      } else if (state.strategyOperationTab === "export") {
        syncStrategyRangePresets(false);
      }
      renderStrategies();
    }

    function syncStrategyOperationTabs() {
      document.querySelectorAll("[data-strategy-operation-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.strategyOperationTab === state.strategyOperationTab);
      });
      document.querySelectorAll("[data-strategy-operation-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.strategyOperationPanel !== state.strategyOperationTab);
      });
      document.querySelectorAll("[data-backtest-only]").forEach((panel) => {
        panel.classList.toggle("hidden", state.strategyOperationTab !== "backtest");
      });
      const paramsTitle = document.querySelector("#strategy-params-title");
      if (paramsTitle) {
        paramsTitle.textContent = state.strategyOperationTab === "backtest" ? "Strategy parameters" : "Chart parameters";
      }
    }

    function selectedStrategyOutput(outputs) {
      const selectedName = document.querySelector("#strategy-name").value;
      const selectedSymbol = document.querySelector("#strategy-symbol").value;
      const selectedTimeframe = document.querySelector("#strategy-timeframe").value;
      if (!state.selectedStrategyOutput || !outputs.includes(state.selectedStrategyOutput)) {
        return null;
      }
      const identity = strategyIdentity(state.selectedStrategyOutput);
      const matchesControls = (!selectedName || identity.name === selectedName)
        && (!selectedSymbol || identity.symbol === selectedSymbol)
        && (!selectedTimeframe || identity.timeframe === selectedTimeframe);
      if (matchesControls) return state.selectedStrategyOutput;
      return null;
    }

    function filteredStrategyOutputs(outputs) {
      const selectedName = document.querySelector("#strategy-name").value;
      const selectedSymbol = document.querySelector("#strategy-symbol").value;
      const selectedTimeframe = document.querySelector("#strategy-timeframe").value;
      return outputs.filter((item) => {
        const identity = strategyIdentity(item);
        return (!selectedName || identity.name === selectedName)
          && (!selectedSymbol || identity.symbol === selectedSymbol)
          && (!selectedTimeframe || identity.timeframe === selectedTimeframe);
      });
    }

    function strategyIdentity(item) {
      const vis = item?.visualization || {};
      const fields = item?.fields || {};
      const inputs = fields.inputs || {};
      return {
        name: vis.strategy_name || inputs.strategy_name || fields.strategy_name || item?.name || "",
        symbol: vis.symbol || inputs.symbol || fields.symbol || "",
        timeframe: vis.timeframe || inputs.timeframe || fields.timeframe || "",
      };
    }

    function syncStrategyControls(item) {
      const identity = strategyIdentity(item);
      if (!item) {
        return;
      }
      setSelectIfPresent("#strategy-name", identity.name);
      setSelectIfPresent("#strategy-symbol", identity.symbol);
      setSelectIfPresent("#strategy-timeframe", identity.timeframe);
    }

    function setSelectIfPresent(selector, value) {
      const node = document.querySelector(selector);
      if (!node || value === null || value === undefined) return;
      const raw = String(value);
      if (Array.from(node.options).some((option) => option.value === raw)) {
        node.value = raw;
      }
    }

    function strategyMetrics(item) {
      const fields = item?.fields || {};
      const metrics = fields.metrics || {};
      const strategy = metrics.strategy_metrics || fields.strategy_metrics || {};
      const trade = metrics.trade_summary || fields.trade_summary || {};
      return {
        totalReturn: metricPercent(strategy.net_return_pct ?? strategy.total_return_pct ?? item?.records?.summary?.net_return_pct),
        drawdown: metricPercent(strategy.max_drawdown_pct),
        sharpe: text(strategy.sharpe_ratio ?? strategy.sharpe),
        winRate: metricPercent(trade.win_rate_pct ?? trade.win_rate),
        profitFactor: text(strategy.profit_factor),
        trades: text(trade.trade_count ?? fields.metrics?.trade_summary?.trade_count),
        longTrades: text(trade.long_trade_count ?? trade.long_trades),
        shortTrades: text(trade.short_trade_count ?? trade.short_trades),
        bestTrade: metricPercent(trade.best_trade_pct ?? trade.best_trade_return_pct),
        worstTrade: metricPercent(trade.worst_trade_pct ?? trade.worst_trade_return_pct),
      };
    }

    function metricPercent(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "n/a";
      const sign = number > 0 ? "+" : "";
      return `${sign}${number.toFixed(2)}%`;
    }

    function backtestVisualization(item) {
      const vis = item?.visualization || {};
      if (Array.isArray(vis.bars) && vis.bars.length) return vis;
      const identity = strategyIdentity(item);
      return {
        status: item?.status || "missing",
        strategy_name: identity.name,
        symbol: identity.symbol,
        timeframe: identity.timeframe,
        bars: [],
        markers: [],
        equity_curve: [],
      };
    }

    function visibleStrategyVisualization(item) {
      return applyStrategyWindow(strategyVisualization(item), state.strategyWindow);
    }

    function strategyVisualization(item) {
      const dataVis = state.strategyDataVisualization;
      if (!item) {
        return dataVis || emptyStrategyVisualization();
      }
      const backtestVis = backtestVisualization(item);
      if (canOverlayBacktest(dataVis, backtestVis)) {
        return {
          ...dataVis,
          chart_type: "candlestick_backtest",
          status: backtestVis.status || item.status || dataVis.status,
          strategy_name: backtestVis.strategy_name,
          markers: Array.isArray(backtestVis.markers) ? backtestVis.markers : [],
          equity_curve: Array.isArray(backtestVis.equity_curve) ? backtestVis.equity_curve : [],
          warnings: [...(dataVis.warnings || []), ...(backtestVis.warnings || [])],
        };
      }
      return backtestVis;
    }

    function emptyStrategyVisualization() {
      return {
        chart_type: "candlestick_data_viewer",
        status: "missing",
        strategy_name: "",
        source: document.querySelector("#strategy-chart-source")?.value || defaultStrategySource(),
        symbol: document.querySelector("#strategy-chart-symbol")?.value || document.querySelector("#strategy-symbol")?.value || "",
        timeframe: document.querySelector("#strategy-chart-timeframe")?.value || document.querySelector("#strategy-timeframe")?.value || "",
        bars: [],
        markers: [],
        equity_curve: [],
      };
    }

    function canOverlayBacktest(dataVis, backtestVis) {
      if (!dataVis || !Array.isArray(dataVis.bars) || !dataVis.bars.length) return false;
      if (!backtestVis || !Array.isArray(backtestVis.markers)) return false;
      return String(dataVis.symbol || "") === String(backtestVis.symbol || "")
        && String(dataVis.timeframe || "") === String(backtestVis.timeframe || "");
    }

    function renderStrategyOhlcvPreview(payload, request, options = {}) {
      state.strategyDataVisualization = ohlcvPreviewVisualization(payload, request);
      if (options.clearBacktest !== false) {
        state.selectedStrategyOutput = null;
        setSelectIfPresent("#strategy-name", "");
      }
      strategyChart.resetCandlestickView("#backtest-chart");
      renderStrategies();
    }

    function ohlcvPreviewVisualization(payload, request) {
      const records = Array.isArray(payload?.records) ? payload.records : [];
      return {
        chart_type: "candlestick_data_viewer",
        status: payload?.status || "ok",
        strategy_name: "",
        source: payload?.source || request?.source || defaultStrategySource(),
        symbol: request?.symbol || payload?.identity?.symbol || "",
        timeframe: request?.timeframe || payload?.identity?.timeframe || "",
        bars: records.map((record) => ({
          time: record.open_time,
          open: record.open,
          high: record.high,
          low: record.low,
          close: record.close,
          volume: record.volume,
        })).filter((bar) => bar.time),
        markers: [],
        equity_curve: [],
        warnings: payload?.warnings || [],
        query: payload?.query || {},
      };
    }

    function visibleBacktestVisualization(item) {
      return applyStrategyWindow(backtestVisualization(item), state.strategyWindow);
    }

    function applyStrategyWindow(vis, windowValue) {
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      const limit = windowValue === "all" ? 0 : Number(windowValue);
      if (!Number.isInteger(limit) || limit <= 0 || bars.length <= limit) {
        return vis;
      }
      const visibleBars = bars.slice(-limit);
      const visibleTimes = new Set(visibleBars.map((bar) => bar.time));
      const markers = Array.isArray(vis.markers)
        ? vis.markers.filter((marker) => visibleTimes.has(marker.time))
        : [];
      const curve = Array.isArray(vis.equity_curve) ? vis.equity_curve.slice(-limit) : [];
      return {...vis, bars: visibleBars, markers, equity_curve: curve};
    }

    function setStrategyWindow(value) {
      state.strategyWindow = ["all", "180", "90", "30"].includes(String(value)) ? String(value) : "all";
      const range = document.querySelector("#strategy-range");
      if (range) range.value = state.strategyWindow;
      syncStrategyWindowControls();
      strategyChart.resetCandlestickView("#backtest-chart");
      renderStrategies();
    }

    function syncStrategyWindowControls() {
      document.querySelectorAll("[data-strategy-window]").forEach((button) => {
        button.classList.toggle("active", button.dataset.strategyWindow === state.strategyWindow);
      });
    }

    function strategyName(item) {
      return strategyIdentity(item).name || "No strategy selected";
    }

    function renderStrategyParams(item, vis) {
      const inputs = item?.fields?.inputs || {};
      const rows = item ? {
        "Momentum window": inputs.momentum_window,
        "Volume window": inputs.volume_window,
        "Symbol": vis.symbol || inputs.symbol,
        "Timeframe": vis.timeframe || inputs.timeframe,
        "Stoploss": inputs.stoploss,
        "Take profit": inputs.take_profit,
        "Stake per trade": inputs.stake_per_trade,
        "Time in force": inputs.time_in_force,
      } : {
        "Source": vis.source,
        "Symbol": vis.symbol,
        "Timeframe": vis.timeframe,
        "Candles": Array.isArray(vis.bars) ? vis.bars.length : 0,
        "First candle": vis.bars?.[0]?.time,
        "Latest candle": vis.bars?.[vis.bars.length - 1]?.time,
        "Backtest overlay": "none",
        "Status": vis.status,
      };
      document.querySelector("#strategy-params").innerHTML = Object.entries(rows).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(text(value))}</td></tr>`).join("");
    }

    function renderRecentTrades(vis) {
      const markers = (vis.markers || []).slice(-5).reverse();
      document.querySelector("#recent-trades").innerHTML = markers.length ? `<div class="trade-list">${markers.map((marker) => `<div class="trade-row"><span class="status-pill ${String(marker.kind || "").toLowerCase().includes("exit") ? "failed" : "available"}">${escapeHtml(marker.label || marker.kind)}</span><strong>${escapeHtml(formatNumber(marker.price || ""))}</strong><small>${escapeHtml(formatTimestamp(marker.time))}</small></div>`).join("")}</div>` : `<div class="message">No operations on the current chart.</div>`;
    }

    function renderBacktestRuns(outputs) {
      const filtered = filteredStrategyOutputs(outputs);
      const clearButton = `<button class="report-row ${state.selectedStrategyOutput ? "" : "active"}" type="button" data-backtest-clear="true">
          <span class="report-row-title">OHLCV only</span>
          <span class="report-row-meta">No backtest overlay</span>
        </button>`;
      document.querySelector("#backtest-runs").innerHTML = clearButton + (filtered.slice(0, 4).map((item, index) => `
        <button class="report-row ${item === state.selectedStrategyOutput ? "active" : ""}" type="button" data-backtest-index="${index}">
          <span class="report-row-title">${escapeHtml(strategyName(item))}</span>
          <span class="report-row-meta">${escapeHtml(item.fields?.created_at || item.status || "latest")}</span>
        </button>`).join("") || `<div class="message">No matching backtest runs.</div>`);
      document.querySelector("[data-backtest-clear]")?.addEventListener("click", () => {
        state.selectedStrategyOutput = null;
        setSelectIfPresent("#strategy-name", "");
        strategyChart.resetCandlestickView("#backtest-chart");
        queueStrategyChartRefresh({clearBacktest: true});
        renderStrategies();
      });
      document.querySelectorAll("[data-backtest-index]").forEach((button) => {
        button.addEventListener("click", () => {
          state.selectedStrategyOutput = filtered[Number(button.dataset.backtestIndex)];
          const identity = strategyIdentity(state.selectedStrategyOutput);
          setSelectIfPresent("#strategy-chart-symbol", identity.symbol);
          setSelectIfPresent("#strategy-chart-timeframe", identity.timeframe);
          setInputValue("#strategy-chart-source", defaultStrategySource(), false);
          strategyChart.resetCandlestickView("#backtest-chart");
          queueStrategyChartRefresh({clearBacktest: false});
          renderStrategies();
        });
      });
    }

    function renderStrategyTab(tab) {
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.classList.toggle("active", button.dataset.strategyTab === tab));
      const vis = visibleBacktestVisualization(state.selectedStrategyOutput);
      const metrics = strategyMetrics(state.selectedStrategyOutput);
      if (tab === "trades" || tab === "list") {
        document.querySelector("#strategy-tab-content").innerHTML = `<div class="summary-strip" style="grid-template-columns: repeat(6, minmax(0, 1fr));">
          ${metricCell("Total trades", metrics.trades, "")}
          ${metricCell("Long", metrics.longTrades, "")}
          ${metricCell("Short", metrics.shortTrades, "")}
          ${metricCell("Win rate", metrics.winRate, "")}
          ${metricCell("Best trade", metrics.bestTrade, "")}
          ${metricCell("Worst trade", metrics.worstTrade, "")}
        </div>`;
      } else if (tab === "equity") {
        const curve = Array.isArray(vis.equity_curve) ? vis.equity_curve : [];
        document.querySelector("#strategy-tab-content").innerHTML = curve.length
          ? `<svg viewBox="0 0 900 120" style="width:100%; height:120px;">${lineChartPath(curve.map((point) => point.net_equity ?? point.equity ?? point.value))}</svg>`
          : `<div class="message">No equity curve is available for the selected backtest.</div>`;
      } else {
        document.querySelector("#strategy-tab-content").innerHTML = renderStrategyDiagnostics();
      }
    }

    function renderStrategyDiagnostics() {
      const groups = strategyWarningGroups();
      if (!groups.length) {
        return `<div class="message">No grouped strategy warnings are recorded for the selected data.</div>`;
      }
      return `<table class="kv-table"><tbody>${groups.map((group) => `
        <tr>
          <td>${escapeHtml(group.message || "warning")}</td>
          <td>${escapeHtml(formatNumber(group.count || 0))} occurrence${Number(group.count) === 1 ? "" : "s"}</td>
          <td>${escapeHtml((group.sources || []).slice(0, 2).join("; ") || "source n/a")}</td>
        </tr>`).join("")}</tbody></table>`;
    }

    function strategyWarningGroups() {
      const groups = Array.isArray(state.strategies?.warning_groups) ? state.strategies.warning_groups : [];
      return groups.slice(0, 12);
    }

    function lineChartPath(rawValues) {
      const values = rawValues.map(Number).filter(Number.isFinite);
      if (!values.length) {
        return `<text x="450" y="64" text-anchor="middle" fill="#5d6675">No chart data available</text>`;
      }
      const min = Math.min(...values);
      const max = Math.max(...values);
      const points = values.map((value, index) => {
        const x = 24 + index * (850 / Math.max(1, values.length - 1));
        const y = 100 - ((value - min) / Math.max(1, max - min)) * 80;
        return `${x},${y}`;
      });
      return `<polyline points="${points.join(" ")}" fill="none" stroke="#008575" stroke-width="3"></polyline>`;
    }

    async function startBacktest() {
      const params = {
        strategy_name: document.querySelector("#strategy-name")?.value,
        symbol: document.querySelector("#strategy-symbol")?.value,
        timeframe: document.querySelector("#strategy-timeframe")?.value,
      };
      if (!params.strategy_name || !params.symbol || !params.timeframe) {
        showToast("Select a configured strategy, symbol, and timeframe first.");
        return;
      }
      state.strategyBacktestLogs = [];
      appendOperationLog("backtest", `Submitting ${params.strategy_name} on ${params.symbol} ${params.timeframe}.`);
      renderOperationProgress("backtest", {
        status: "running",
        percent: 6,
        headline: `Backtest ${params.symbol} ${params.timeframe}`,
        logs: state.strategyBacktestLogs,
      });
      try {
        const job = await postJob("backtest", params);
        appendOperationLog("backtest", `Job ${job.job_id || "pending"} ${job.status || "created"}.`);
        renderOperationProgress("backtest", {
          status: job.status || "queued",
          percent: jobStatusPercent(job.status),
          headline: `Backtest ${params.symbol} ${params.timeframe}`,
          logs: operationLogsWithJob("backtest", job),
        });
        if (job.job_id) {
          const completed = await pollBacktestJob(job.job_id, params);
          if (terminalJobStatus(completed.status)) {
            await refreshStrategies();
          }
        }
      } catch (error) {
        appendOperationLog("backtest", `Failed: ${error.message}`);
        renderOperationProgress("backtest", {
          status: "failed",
          percent: 100,
          headline: "Backtest failed",
          logs: state.strategyBacktestLogs,
        });
      }
    }

    async function pollBacktestJob(jobId, params) {
      let latest = {job_id: jobId, status: "queued"};
      let lastStatus = "";
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        latest = await fetchJob(jobId);
        const status = latest.status || "unknown";
        if (status !== lastStatus) {
          appendOperationLog("backtest", `Job ${jobId} ${status}.`);
          lastStatus = status;
        }
        renderOperationProgress("backtest", {
          status,
          percent: jobStatusPercent(status),
          headline: `Backtest ${params.symbol} ${params.timeframe}`,
          logs: operationLogsWithJob("backtest", latest),
        });
        if (terminalJobStatus(status)) {
          showToast(`Backtest job ${status}.`);
          return latest;
        }
      }
      appendOperationLog("backtest", "Backtest is still running. Refresh jobs to inspect it later.");
      renderOperationProgress("backtest", {
        status: "running",
        percent: 88,
        headline: `Backtest ${params.symbol} ${params.timeframe}`,
        logs: state.strategyBacktestLogs,
      });
      return latest;
    }

    function queueStrategyChartRefresh(options = {}) {
      window.clearTimeout(state.strategyChartPreviewTimer);
      state.strategyChartPreviewTimer = window.setTimeout(() => loadStrategyChartPreview({silent: true, ...options}), 220);
    }

    function strategyChartRequest({silent = false} = {}) {
      const source = String(document.querySelector("#strategy-chart-source")?.value || "").trim();
      const symbol = String(document.querySelector("#strategy-chart-symbol")?.value || "").trim();
      const timeframe = String(document.querySelector("#strategy-chart-timeframe")?.value || "").trim();
      const range = document.querySelector("#strategy-chart-range")?.value || "all";
      const dateRange = presetDateRange(range);
      if (!source || !symbol || !timeframe || !dateRange?.start || !dateRange?.end) {
        if (!silent) showToast("Chart requires source, symbol, timeframe, and a stored date range.");
        return null;
      }
      return {
        data_type: "ohlcv",
        source,
        symbol,
        timeframe,
        start: dateRange.start,
        end: dateRange.end,
      };
    }

    async function loadStrategyChartPreview(options = {}) {
      const request = strategyChartRequest(options);
      if (!request) return;
      const requestId = state.strategyChartPreviewRequest + 1;
      state.strategyChartPreviewRequest = requestId;
      const meta = document.querySelector("#strategy-chart-meta");
      if (meta && !options.silent) {
        meta.textContent = `Loading ${request.symbol} ${request.timeframe} candles.`;
      }
      try {
        const payload = await postJson(endpoints.dataViewerPreview, {...request, limit: 1000, sort_order: "asc"});
        if (requestId !== state.strategyChartPreviewRequest) return;
        state.dataViewerStrategyPreview = payload;
        const clearBacktest = options.clearBacktest ?? state.strategyOperationTab !== "backtest";
        renderStrategyOhlcvPreview(payload, request, {clearBacktest});
      } catch (error) {
        if (requestId !== state.strategyChartPreviewRequest) return;
        if (meta) {
          meta.textContent = `Chart load failed: ${error.message}`;
        }
        if (!options.silent) showToast(`Chart load failed: ${error.message}`);
      }
    }

    function strategyCollectTargets() {
      return state.strategyCollectTargets.filter((target) => target.symbol && target.timeframe);
    }

    function strategyCollectBaseRequest({silent = false} = {}) {
      const source = String(document.querySelector("#strategy-collect-source")?.value || "").trim();
      const start = String(document.querySelector("#strategy-collect-start")?.value || "").trim();
      const end = String(document.querySelector("#strategy-collect-end")?.value || "").trim();
      if (!source || !start || !end) {
        if (!silent) showToast("Collect requires source, start, and end.");
        return null;
      }
      return {
        data_type: "ohlcv",
        source,
        start,
        end,
        max_exact_windows: 3,
        merge_gap_threshold_seconds: 0,
        min_fetch_window_seconds: 0,
      };
    }

    function strategyCollectRequest(target, options = {}) {
      const base = strategyCollectBaseRequest(options);
      if (!base) return null;
      return {...base, symbol: target.symbol, timeframe: target.timeframe};
    }

    function queueStrategyCollectTimelineRefresh() {
      window.clearTimeout(state.strategyCollectTimelineTimer);
      state.strategyCollectTimelineTimer = window.setTimeout(refreshStrategyCollectTimeline, 220);
    }

    async function refreshStrategyCollectTimeline() {
      const panel = document.querySelector("#strategy-collect-timeline");
      if (!panel || state.strategyOperationTab !== "collect") return;
      const targets = strategyCollectTargets();
      const base = strategyCollectBaseRequest({silent: true});
      if (!targets.length) {
        panel.innerHTML = `<div class="message">Add at least one target to view collection coverage.</div>`;
        return;
      }
      if (!base) {
        panel.innerHTML = `<div class="message">Choose a source and time range to view collection coverage.</div>`;
        return;
      }
      const requestId = state.strategyCollectTimelineRequest + 1;
      state.strategyCollectTimelineRequest = requestId;
      panel.innerHTML = `<div class="message">Loading ${escapeHtml(formatNumber(targets.length))} coverage timeline${targets.length === 1 ? "" : "s"}.</div>`;
      const results = await Promise.all(targets.map(async (target) => {
        const request = {...base, symbol: target.symbol, timeframe: target.timeframe};
        try {
          const payload = await postJson(endpoints.dataViewerTimeline, request);
          return {target, request, payload};
        } catch (error) {
          return {target, request, payload: {status: "failed", intervals: [], errors: [error.message]}};
        }
      }));
      if (requestId !== state.strategyCollectTimelineRequest) return;
      panel.innerHTML = renderCollectTimelineResults(results, base);
    }

    function renderCollectTimelineResults(results, base) {
      return results.map((item) => {
        const intervals = Array.isArray(item.payload?.intervals) ? item.payload.intervals : [];
        const errors = Array.isArray(item.payload?.errors) ? item.payload.errors : [];
        const segments = intervals.length && !errors.length
          ? intervals.map((interval) => collectTimelineSegment(interval, base)).join("")
          : collectTimelineSegment({range_start: base.start, range_end: base.end, status: errors.length ? "failed" : "unknown"}, base);
        const meta = errors.length
          ? errors.slice(0, 2).join("; ")
          : intervals.length
          ? `${intervals.length} coverage interval${intervals.length === 1 ? "" : "s"}`
          : "coverage is unknown for this range";
        return `
          <div class="collect-timeline-row">
            <div class="collect-timeline-label"><strong>${escapeHtml(item.target.symbol)}</strong><span>${escapeHtml(item.target.timeframe)}</span></div>
            <div class="collect-timeline-track" aria-label="${escapeHtml(item.target.symbol)} ${escapeHtml(item.target.timeframe)} coverage">${segments}</div>
            <div class="collect-timeline-meta">${escapeHtml(meta)}</div>
          </div>`;
      }).join("");
    }

    function collectTimelineSegment(interval, base) {
      const startMs = Date.parse(base.start);
      const endMs = Date.parse(base.end);
      if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
        const status = String(interval.status || "unknown").toLowerCase();
        return `<span class="collect-timeline-segment ${escapeHtml(statusClass(status))} ${escapeHtml(status)}" style="left:0%;width:100%;" title="${escapeHtml(status)}"></span>`;
      }
      const rawIntervalStart = Date.parse(interval.range_start || base.start);
      const rawIntervalEnd = Date.parse(interval.range_end || base.end);
      const intervalStart = Math.max(startMs, Number.isFinite(rawIntervalStart) ? rawIntervalStart : startMs);
      const intervalEnd = Math.min(endMs, Number.isFinite(rawIntervalEnd) ? rawIntervalEnd : endMs);
      const total = Math.max(1, endMs - startMs);
      const left = Math.max(0, Math.min(100, (intervalStart - startMs) / total * 100));
      const width = Math.max(1, Math.min(100 - left, (intervalEnd - intervalStart) / total * 100));
      const status = String(interval.status || "unknown").toLowerCase();
      const title = `${status}: ${formatTimestamp(interval.range_start || base.start)} to ${formatTimestamp(interval.range_end || base.end)}`;
      return `<span class="collect-timeline-segment ${escapeHtml(statusClass(status))} ${escapeHtml(status)}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;" title="${escapeHtml(title)}"></span>`;
    }

    async function runStrategyCollectBatch() {
      const targets = strategyCollectTargets();
      if (!targets.length) {
        showToast("Add at least one collection target first.");
        return;
      }
      state.strategyCollectLogs = [];
      appendOperationLog("collect", `Starting collection for ${targets.length} target${targets.length === 1 ? "" : "s"}.`);
      let failed = false;
      for (let index = 0; index < targets.length; index += 1) {
        const target = targets[index];
        const request = strategyCollectRequest(target);
        if (!request) return;
        appendOperationLog("collect", `Submitting ${target.symbol} ${target.timeframe}.`);
        renderOperationProgress("collect", {
          status: "running",
          percent: Math.round(index / targets.length * 100),
          headline: `Collecting ${target.symbol} ${target.timeframe}`,
          logs: state.strategyCollectLogs,
        });
        try {
          const payload = await postJson(endpoints.dataViewerCollectJobs, request);
          const job = payload.job || payload;
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} job ${job.job_id || "pending"} ${job.status || "created"}.`);
          if (job.job_id) {
            const completed = await pollCollectJob(job.job_id, target, index, targets.length);
            failed = failed || statusClass(completed.status) === "failed";
          } else {
            failed = true;
          }
        } catch (error) {
          failed = true;
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} failed: ${error.message}`);
          renderOperationProgress("collect", {
            status: "failed",
            percent: Math.round((index + 1) / targets.length * 100),
            headline: `Collection failed for ${target.symbol} ${target.timeframe}`,
            logs: state.strategyCollectLogs,
          });
        }
      }
      await dataViewerWorkflow.loadDataViewerSummary();
      dataViewerWorkflow.renderStrategyViewer();
      queueStrategyCollectTimelineRefresh();
      renderOperationProgress("collect", {
        status: failed ? "failed" : "succeeded",
        percent: 100,
        headline: failed ? "Collection finished with errors" : "Collection complete",
        logs: state.strategyCollectLogs,
      });
    }

    async function pollCollectJob(jobId, target, index, total) {
      let latest = {job_id: jobId, status: "queued"};
      let lastStatus = "";
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        latest = await fetchJob(jobId);
        const status = latest.status || "unknown";
        if (status !== lastStatus) {
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} ${status}.`);
          lastStatus = status;
        }
        const percent = Math.round(((index + jobStatusFraction(status)) / total) * 100);
        renderOperationProgress("collect", {
          status,
          percent,
          headline: `Collecting ${target.symbol} ${target.timeframe}`,
          logs: operationLogsWithJob("collect", latest),
        });
        if (terminalJobStatus(status)) return latest;
      }
      appendOperationLog("collect", `${target.symbol} ${target.timeframe} is still running.`);
      return latest;
    }

    function strategyExportRequest() {
      const source = String(document.querySelector("#strategy-export-source")?.value || "").trim();
      const symbol = String(document.querySelector("#strategy-export-symbol")?.value || "").trim();
      const timeframe = String(document.querySelector("#strategy-export-timeframe")?.value || "").trim();
      const start = String(document.querySelector("#strategy-export-start")?.value || "").trim();
      const end = String(document.querySelector("#strategy-export-end")?.value || "").trim();
      const asOf = String(document.querySelector("#strategy-export-as-of")?.value || "").trim();
      const format = String(document.querySelector("#strategy-export-format")?.value || "csv").trim();
      if (!source || !symbol || !timeframe || !start || !end) {
        showToast("Export requires source, symbol, timeframe, start, and end.");
        return null;
      }
      return removeEmpty({
        data_type: "ohlcv",
        source,
        symbol,
        timeframe,
        start,
        end,
        as_of: asOf,
        format,
      });
    }

    async function runStrategyExport() {
      const request = strategyExportRequest();
      if (!request) return;
      state.strategyExportLogs = [];
      appendOperationLog("export", `Exporting ${request.symbol} ${request.timeframe} as ${String(request.format).toUpperCase()}.`);
      renderOperationProgress("export", {status: "running", percent: 18, headline: `Export ${request.symbol} ${request.timeframe}`, logs: state.strategyExportLogs});
      const panel = document.querySelector("#strategy-data-job-panel");
      panel.innerHTML = `<div class="message">Creating bounded export under data/exports.</div>`;
      try {
        const payload = await postJson(endpoints.dataViewerExport, request);
        state.dataViewerStrategyExport = payload;
        const result = payload.export || {};
        appendOperationLog("export", `Export ${payload.status || result.status || "ok"}: ${result.output_path || "output path n/a"}.`);
        panel.innerHTML = `
          <div class="message">
            <strong>Export ${escapeHtml(label(payload.status || result.status || "ok"))}</strong><br>
            Output: ${escapeHtml(result.output_path || "n/a")}<br>
            Records: ${escapeHtml(text(result.record_count, "0"))}${result.truncated ? " / truncated" : ""}
          </div>
          ${table(["Field", "Value"], [
            ["Format", result.format || result.output_format || request.format || "n/a"],
            ["Metadata", result.metadata_path || "embedded or n/a"],
            ["As of", result.query_parameters?.as_of || "latest stored view"],
            ["Coverage", result.coverage_diagnostics?.status || "n/a"],
          ])}`;
        renderOperationProgress("export", {status: payload.status || "succeeded", percent: 100, headline: "Export complete", logs: state.strategyExportLogs});
      } catch (error) {
        appendOperationLog("export", `Failed: ${error.message}`);
        panel.innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
        renderOperationProgress("export", {status: "failed", percent: 100, headline: "Export failed", logs: state.strategyExportLogs});
      }
    }

    function appendOperationLog(kind, message) {
      const key = kind === "backtest" ? "strategyBacktestLogs" : kind === "export" ? "strategyExportLogs" : "strategyCollectLogs";
      const timeText = new Date().toLocaleTimeString(undefined, {hour12: false});
      state[key].push(`${timeText} ${message}`);
    }

    function operationLogsWithJob(kind, job) {
      const key = kind === "backtest" ? "strategyBacktestLogs" : kind === "export" ? "strategyExportLogs" : "strategyCollectLogs";
      const logs = [...state[key]];
      const warnings = Array.isArray(job?.warnings) ? job.warnings : [];
      const errors = Array.isArray(job?.errors) ? job.errors : [];
      Object.entries(job?.result_refs || {}).forEach(([name, ref]) => logs.push(`${name}: ${ref}`));
      warnings.slice(0, 3).forEach((warning) => logs.push(`warning: ${warning}`));
      errors.slice(0, 3).forEach((error) => logs.push(`error: ${error}`));
      return logs;
    }

    function renderOperationProgress(kind, payload) {
      const node = document.querySelector(`#strategy-${kind}-progress`);
      if (!node) return;
      const status = payload.status || "running";
      const percent = Math.max(0, Math.min(100, Number(payload.percent) || 0));
      const logs = Array.isArray(payload.logs) ? payload.logs : [];
      const expanded = node.dataset.expanded === "true";
      const visibleLogs = logs.slice().reverse();
      node.className = `operation-progress ${expanded ? "expanded" : ""}`.trim();
      node.innerHTML = `
        <div class="operation-progress-top">
          <div><strong>${escapeHtml(payload.headline || label(status))}</strong><span>${escapeHtml(label(status))}</span></div>
          <span>${escapeHtml(`${Math.round(percent)}%`)}</span>
        </div>
        <div class="operation-progress-track"><span class="${escapeHtml(statusClass(status))}" style="width:${percent}%;"></span></div>
        <div class="operation-log-header">
          <span>${escapeHtml(visibleLogs[0] || "No log lines yet.")}</span>
          <button class="ghost-button" type="button" data-operation-log-toggle="${escapeHtml(kind)}">${expanded ? "Collapse" : "Expand logs"}</button>
        </div>
        <pre class="operation-log ${expanded ? "expanded" : ""}">${escapeHtml(visibleLogs.join("\n") || "No log lines yet.")}</pre>`;
      node.querySelector("[data-operation-log-toggle]")?.addEventListener("click", () => {
        node.dataset.expanded = expanded ? "false" : "true";
        renderOperationProgress(kind, payload);
      });
    }

    function jobStatusFraction(status) {
      const normalized = String(status || "").toLowerCase();
      if (terminalJobStatus(normalized)) return 1;
      if (normalized === "running") return 0.66;
      if (normalized === "queued" || normalized === "created" || normalized === "creating") return 0.18;
      if (normalized === "cancel_requested") return 0.85;
      return 0.35;
    }

    function jobStatusPercent(status) {
      return Math.round(jobStatusFraction(status) * 100);
    }

    function downloadSelectedOhlcv() {
      const selected = state.strategyOperationTab === "backtest" ? state.selectedStrategyOutput : null;
      const vis = visibleStrategyVisualization(selected);
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      if (!bars.length) {
        showToast("No OHLCV bars are available on the current chart.");
        return;
      }
      const columns = ["time", "open", "high", "low", "close", "volume"];
      const csv = [
        columns.join(","),
        ...bars.map((bar) => columns.map((column) => csvCell(bar[column])).join(",")),
      ].join("\n");
      const blob = new Blob([csv], {type: "text/csv"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${vis.symbol || "ohlcv"}-${vis.timeframe || "window"}-candles.csv`;
      link.click();
      URL.revokeObjectURL(url);
    }

    function csvCell(value) {
      const textValue = String(value ?? "");
      if (/[",\n\r]/.test(textValue)) {
        return `"${textValue.replace(/"/g, '""')}"`;
      }
      return textValue;
    }

    function removeEmpty(value) {
      return Object.fromEntries(Object.entries(value).filter((entry) => entry[1] !== null && entry[1] !== undefined && entry[1] !== ""));
    }

    async function refreshIntelligence() {
      try {
        const [textIntel] = await Promise.all([
          fetchJson(endpoints.textIntel),
          loadStores().catch(() => null),
          dataViewerWorkflow.loadDataViewerSummary().catch(() => null),
        ]);
        state.intelligence = textIntel;
      } catch (error) {
        state.intelligence = {status: "failed", warnings: [error.message], artifacts: []};
        await dataViewerWorkflow.loadDataViewerSummary();
      }
      renderIntelligence();
    }

    function renderIntelligence() {
      syncIntelTabs();
      const overview = state.selectedIntelTab === "overview";
      document.querySelector("#intel-overview-panel")?.classList.toggle("hidden", !overview);
      document.querySelector("#intel-data-viewer")?.classList.toggle("hidden", overview);
      if (overview) {
        renderIntelligenceOverview();
        return;
      }
      setSelectIfPresent("#intel-data-type", state.selectedIntelTab);
      state.selectedIntelPreviewIndex = 0;
      dataViewerWorkflow.renderIntelligenceViewer();
    }

    function syncIntelTabs() {
      const supportedTabs = ["overview", "text_event", "macro_calendar", "onchain_flow", "derivatives_market"];
      if (!supportedTabs.includes(state.selectedIntelTab)) {
        state.selectedIntelTab = "overview";
      }
      document.querySelectorAll("[data-intel-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.intelTab === state.selectedIntelTab);
      });
    }

    function renderIntelligenceOverview() {
      const items = intelligenceOverviewItems();
      const stores = intelligenceStoreSummaries();
      const healthyStores = stores.filter((store) => ["ok", "available"].includes(String(store.status || "").toLowerCase())).length;
      const warningCount = stores.reduce((sum, store) => sum + (store.warnings || []).length + (store.errors || []).length, 0)
        + items.filter((item) => item.severity === "Medium" || item.severity === "High").length;
      document.querySelector("#intel-overview-kpis").innerHTML = [
        metricCell("High-impact events", items.filter((item) => item.severity === "High").length, "from current intelligence artifacts"),
        metricCell("Source coverage", unique([...items.flatMap((item) => item.sources || []), ...stores.flatMap((store) => store.source_artifacts || [])]).length, "source refs"),
        metricCell("Warnings", warningCount, "warnings and errors"),
        metricCell("New topics", unique(items.map((item) => item.category || item.title)).length, "artifact categories"),
        metricCell("Data quality", `${healthyStores}/${stores.length || 0}`, "healthy shared stores"),
      ].join("");
      document.querySelector("#intel-overview-content").innerHTML = `
        <section class="panel panel-pad">
          <h2 class="panel-title">Shared store coverage</h2>
          <div class="intel-store-card-grid">${stores.map(renderIntelStoreCard).join("") || `<div class="empty-state">No intelligence shared-store summaries are available.</div>`}</div>
        </section>
        <section class="panel panel-pad">
          <h2 class="panel-title">Recent intelligence artifacts</h2>
          <div class="intel-overview-list">${items.slice(0, 8).map(renderIntelOverviewItem).join("") || `<div class="empty-state">No intelligence artifact summaries are available.</div>`}</div>
        </section>`;
    }

    function intelligenceStoreSummaries() {
      const stores = Array.isArray(state.dataViewerSummary?.stores) ? state.dataViewerSummary.stores : [];
      return stores.filter((store) => ["text_event", "macro_calendar", "onchain_flow", "derivatives_market"].includes(store.data_type));
    }

    function renderIntelStoreCard(store) {
      const coverage = store.coverage || {};
      const summary = store.summary || {};
      const records = summary.records ?? summary.record_count ?? coverage.record_count ?? 0;
      const statusCounts = Object.entries(coverage.status_counts || {})
        .filter((entry) => Number(entry[1]) > 0)
        .map(([status, count]) => `${status}: ${formatNumber(count)}`)
        .join(" / ");
      return `
        <article class="intel-store-card">
          <div class="intel-store-card-head">
            <strong>${escapeHtml(intelligenceTypeLabel(store.data_type))}</strong>
            ${statusPill(store.status || coverage.state_status || "unknown")}
          </div>
          <div class="intel-store-card-metric">${escapeHtml(formatNumber(records))}</div>
          <div class="muted">${escapeHtml(coverage.range_start && coverage.range_end ? `${formatTimestamp(coverage.range_start)} to ${formatTimestamp(coverage.range_end)}` : "No collected range")}</div>
          <div class="tag-row">${statusCounts ? statusCounts.split(" / ").map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") : `<span class="tag">coverage n/a</span>`}</div>
        </article>`;
    }

    function renderIntelOverviewItem(item) {
      return `
        <article class="intel-overview-row">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.summary || "No summary recorded.")}</span>
          </div>
          <div class="tag-row"><span class="status-pill ${item.severity === "High" ? "failed" : item.severity === "Medium" ? "warning" : "available"}">${escapeHtml(item.severity)}</span><span class="tag">${escapeHtml(item.category)}</span></div>
        </article>`;
    }

    function intelligenceOverviewItems() {
      const artifacts = Array.isArray(state.intelligence?.artifacts) ? state.intelligence.artifacts : [];
      return artifacts.map((artifact) => ({
        title: artifact.fields?.title || artifact.name || "Intelligence artifact",
        severity: artifact.errors?.length ? "High" : artifact.warnings?.length ? "Medium" : "Low",
        category: artifact.name || "artifact",
        time: artifact.fields?.updated_at || artifact.fields?.created_at,
        summary: [...(artifact.warnings || []), ...(artifact.errors || [])].join(" ") || `${label(artifact.status)} source-aware intelligence artifact.`,
        sources: artifact.source_artifacts || [],
        assets: intelligenceAssets(artifact),
      })).sort((left, right) => timestampMs(right.time) - timestampMs(left.time));
    }

    function intelligenceTypeLabel(dataType) {
      return {
        text_event: "Text events",
        macro_calendar: "Macro calendar",
        onchain_flow: "On-chain flow",
        derivatives_market: "Derivatives market",
      }[dataType] || label(dataType);
    }

    function timestampMs(value) {
      const time = value ? new Date(value).getTime() : NaN;
      return Number.isFinite(time) ? time : 0;
    }

    function intelligenceAssets(artifact) {
      const fields = artifact?.fields || {};
      const values = [
        fields.symbol,
        fields.asset,
        ...(Array.isArray(fields.symbols) ? fields.symbols : []),
        ...(Array.isArray(fields.assets) ? fields.assets : []),
      ];
      return unique(values).slice(0, 8);
    }

    async function refreshSettings() {
      await Promise.allSettled([loadHealth(), loadStores(), loadDeletionPlan(), loadConfigProfile()]);
      renderSettings();
    }

    async function loadConfigProfile() {
      state.settingsProfile = await fetchJson(endpoints.settings);
      return state.settingsProfile;
    }

    function renderSettings() {
      const sections = Array.isArray(state.settingsProfile?.sections) && state.settingsProfile.sections.length
        ? state.settingsProfile.sections
        : ["General", "Market data", "Strategy", "Reports", "Monitor", "Intelligence sources", "Storage", "Dashboard"];
      if (!sections.includes(state.settingsSection)) {
        state.settingsSection = sections[0] || "General";
      }
      document.querySelector("#settings-nav").innerHTML = sections.map((section) => `<button type="button" class="${section === state.settingsSection ? "active" : ""}" data-settings-section="${escapeHtml(section)}">${escapeHtml(section)}<span>&gt;</span></button>`).join("");
      document.querySelectorAll("[data-settings-section]").forEach((button) => button.addEventListener("click", () => {
        state.settingsSection = button.dataset.settingsSection;
        renderSettings();
      }));
      const profileStatus = state.settingsProfile?.status || "loading";
      setPill("#settings-valid-pill", profileStatus, profileStatus === "available" ? "Loaded" : profileStatus);
      document.querySelector("#settings-last-validated").textContent = state.validationJob ? `Last validation job: ${state.validationJob.status || "created"}` : "Last validated: not run";
      const loaded = state.settingsProfile?.config?.loaded !== false && state.settingsProfile?.status !== "unconfigured";
      document.querySelector("#config-profile").textContent = loaded ? (state.settingsProfile?.config?.ref || state.health?.config?.ref || "Current config") : "not configured";
      document.querySelector("#settings-section-title").textContent = state.settingsSection;
      document.querySelector("#settings-form").innerHTML = settingsForm(state.settingsSection);
      const backupButton = document.querySelector("#settings-backup");
      if (backupButton) backupButton.disabled = !loaded;
      document.querySelectorAll("[data-job-intent='validate']").forEach((button) => { button.disabled = !loaded; });
      renderChangeSummary();
      renderValidationResults();
      renderStorageMaintenance();
      wireSettingsControls();
      wireCleanupControls();
    }

    function settingsForm(section) {
      if (state.settingsProfile?.status === "unconfigured") {
        return `<div class="empty-state">No config is active. Load a config file to show editable settings.</div>`;
      }
      if (section === "Storage") {
        return storageMaintenanceMarkup();
      }
      const fields = settingsFields().filter((field) => field.section === section && settingFieldIsVisible(field));
      if (!fields.length) {
        return `<div class="message">No editable controls are available for this section yet.</div>`;
      }
      return fields.map(settingRow).join("");
    }

    function settingsFields() {
      return Array.isArray(state.settingsProfile?.fields) ? state.settingsProfile.fields : [];
    }

    function settingField(path) {
      return settingsFields().find((field) => field.path === path);
    }

    function settingValue(field) {
      if (Object.prototype.hasOwnProperty.call(state.settingsChanges, field.path)) {
        return state.settingsChanges[field.path];
      }
      return field.value;
    }

    function settingPathValue(path) {
      if (Object.prototype.hasOwnProperty.call(state.settingsChanges, path)) {
        return state.settingsChanges[path];
      }
      const field = settingField(path);
      return field ? field.value : undefined;
    }

    function settingPathEnabled(path) {
      return settingPathValue(path) === true;
    }

    function settingFieldIsVisible(field) {
      const path = String(field?.path || "");
      if (path === "market.enabled" || path === "text.enabled" || path === "macro_calendar.enabled" || path === "onchain_flow.enabled") {
        return true;
      }
      if (path.startsWith("market.derivatives.")) {
        return settingPathEnabled("market.enabled") && (path === "market.derivatives.enabled" || settingPathEnabled("market.derivatives.enabled"));
      }
      if (path.startsWith("market.")) {
        return settingPathEnabled("market.enabled");
      }
      if (path === "text.intelligence.enabled") {
        return settingPathEnabled("text.enabled");
      }
      if (path.startsWith("text.intelligence.")) {
        return settingPathEnabled("text.enabled") && settingPathEnabled("text.intelligence.enabled");
      }
      if (path.startsWith("text.")) {
        return settingPathEnabled("text.enabled");
      }
      if (path.startsWith("macro_calendar.")) {
        return path === "macro_calendar.enabled" || settingPathEnabled("macro_calendar.enabled");
      }
      if (path.startsWith("onchain_flow.")) {
        return path === "onchain_flow.enabled" || settingPathEnabled("onchain_flow.enabled");
      }
      return true;
    }

    function settingVisibilityChanges(path) {
      return [
        "market.enabled",
        "market.derivatives.enabled",
        "text.enabled",
        "text.intelligence.enabled",
        "macro_calendar.enabled",
        "onchain_flow.enabled",
      ].includes(path);
    }

    function pruneHiddenSettingChanges() {
      Object.keys(state.settingsChanges).forEach((path) => {
        const field = settingField(path);
        if (field && !settingFieldIsVisible(field)) {
          delete state.settingsChanges[path];
        }
      });
    }

    function settingRow(field) {
      return `
        <div class="form-row">
          <div>
            <strong>${escapeHtml(field.label)}</strong>
            ${field.description ? `<small class="muted">${escapeHtml(field.description)}</small>` : ""}
          </div>
          ${settingControl(field)}
        </div>`;
    }

    function settingControl(field) {
      const value = settingValue(field);
      const path = escapeHtml(field.path);
      if (field.control === "toggle") {
        const on = Boolean(value);
        return `<button class="toggle ${on ? "on" : ""}" type="button" role="switch" aria-checked="${on ? "true" : "false"}" aria-label="${escapeHtml(field.label)}" data-setting-path="${path}" data-setting-type="bool"></button>`;
      }
      if (field.control === "select") {
        const options = Array.isArray(field.options) && field.options.length ? field.options : [value];
        return `<select class="select-input" data-setting-path="${path}" data-setting-type="string">${options.map((option) => `<option value="${escapeHtml(option)}" ${String(option) === String(value) ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select>`;
      }
      if (field.control === "number") {
        const numberType = field.value_type === "unit_interval_number" ? "unit_interval_number" : "positive_int";
        const attrs = numberType === "unit_interval_number" ? 'min="0" max="1" step="0.01"' : 'min="1" step="1"';
        return `<input class="text-input" type="number" ${attrs} value="${escapeHtml(value)}" data-setting-path="${path}" data-setting-type="${numberType}">`;
      }
      if (field.control === "multi_select") {
        const values = Array.isArray(value) ? value.map(String) : [];
        const options = Array.isArray(field.options) ? field.options : values;
        return `<div class="chip-row">${options.map((option) => `<label class="chip"><input type="checkbox" ${values.includes(String(option)) ? "checked" : ""} data-setting-path="${path}" data-setting-type="multi_select" data-setting-option="${escapeHtml(option)}"> ${escapeHtml(option)}</label>`).join("")}</div>`;
      }
      if (field.control === "tags") {
        const values = Array.isArray(value) ? value.join(", ") : String(value || "");
        return `<input class="text-input" value="${escapeHtml(values)}" data-setting-path="${path}" data-setting-type="string_list" placeholder="BTCUSDT, ETHUSDT">`;
      }
      return `<input class="text-input" value="${escapeHtml(value)}" data-setting-path="${path}" data-setting-type="string">`;
    }

    function wireSettingsControls() {
      document.querySelectorAll("[data-setting-path]").forEach((node) => {
        if (node.dataset.settingType === "bool") {
          node.addEventListener("click", () => {
            const next = !node.classList.contains("on");
            node.classList.toggle("on", next);
            node.setAttribute("aria-checked", next ? "true" : "false");
            recordSettingChange(node.dataset.settingPath, next);
            if (settingVisibilityChanges(node.dataset.settingPath)) {
              pruneHiddenSettingChanges();
              renderSettings();
            }
          });
          return;
        }
        node.addEventListener("change", () => {
          const path = node.dataset.settingPath;
          if (node.dataset.settingType === "multi_select") {
            recordSettingChange(path, multiSelectValues(path));
          } else if (node.dataset.settingType === "positive_int") {
            recordSettingChange(path, Number(node.value));
          } else if (node.dataset.settingType === "unit_interval_number") {
            recordSettingChange(path, Number(node.value));
          } else if (node.dataset.settingType === "string_list") {
            recordSettingChange(path, node.value.split(",").map((item) => item.trim()).filter(Boolean));
          } else {
            recordSettingChange(path, node.value);
          }
        });
      });
    }

    function multiSelectValues(path) {
      return Array.from(document.querySelectorAll("[data-setting-path]"))
        .filter((node) => node.dataset.settingPath === path && node.dataset.settingOption && node.checked)
        .map((node) => node.dataset.settingOption);
    }

    function recordSettingChange(path, value) {
      const field = settingField(path);
      if (!field) {
        return;
      }
      if (valuesEqual(value, field.value)) {
        delete state.settingsChanges[path];
      } else {
        state.settingsChanges[path] = value;
      }
      renderChangeSummary();
    }

    function valuesEqual(left, right) {
      return JSON.stringify(left) === JSON.stringify(right);
    }

    function renderChangeSummary() {
      const paths = Object.keys(state.settingsChanges);
      setPill("#change-count", paths.length ? "warning" : "available", `${paths.length} changes`);
      const saveButton = document.querySelector("#settings-save");
      if (saveButton) {
        saveButton.disabled = !paths.length || state.settingsProfile?.status === "unconfigured";
      }
      document.querySelector("#change-summary").innerHTML = paths.length
        ? paths.map((path) => {
          const field = settingField(path);
          const labelText = field?.label || path;
          return `<li class="compact-row"><strong>${escapeHtml(labelText)}</strong><span>${escapeHtml(path)}</span></li>`;
        }).join("")
        : `<li class="message">No pending changes.</li>`;
    }

    function renderValidationResults() {
      if (state.validationJob) {
        renderValidationJob(state.validationJob);
        return;
      }
      document.querySelector("#validation-results").innerHTML = `<div class="message">Use Validate to run the local product validation command. Warnings are shown here without exposing private local values.</div>`;
    }

    function renderStorageMaintenance() {
      renderRunCleanupList();
      renderSharedCleanupList();
    }

    function storageMaintenanceMarkup() {
      return `
        <section class="storage-maintenance settings-storage-page">
          <div class="storage-maintenance-header">
            <h2 class="panel-title" style="margin-bottom: 4px;">Storage maintenance</h2>
            <div class="muted">Run artifacts affect one run. Shared stores may be reused by reports and future runs.</div>
          </div>
          <div class="cleanup-grid">
            <section class="cleanup-panel">
              <div class="cleanup-panel-head">
                <strong>Single-run artifacts</strong>
                <button class="danger-button" type="button" id="cleanup-run-artifacts">Delete selected</button>
              </div>
              <div id="run-cleanup-list" class="cleanup-list"></div>
            </section>
            <section class="cleanup-panel">
              <div class="cleanup-panel-head">
                <strong>Shared data stores</strong>
                <button class="danger-button" type="button" id="cleanup-shared-data">Delete selected</button>
              </div>
              <div id="shared-cleanup-list" class="cleanup-list"></div>
            </section>
          </div>
        </section>`;
    }

    function renderRunCleanupList() {
      const items = state.deletionPlan?.run_artifacts?.items || [];
      state.selectedRunArtifacts = state.selectedRunArtifacts.filter((id) => items.some((item) => item.run_id === id && item.deletable));
      const list = document.querySelector("#run-cleanup-list");
      if (!list) return;
      if (!items.length) {
        list.innerHTML = `<div class="message">No run artifacts are available for cleanup.</div>`;
        return;
      }
      list.innerHTML = items.slice(0, 80).map((item) => `
        <label class="cleanup-option">
          <input type="checkbox" data-run-cleanup="${escapeHtml(item.run_id)}" ${state.selectedRunArtifacts.includes(item.run_id) ? "checked" : ""} ${item.deletable ? "" : "disabled"}>
          <span>
            <strong>${escapeHtml(item.title || item.run_id)}</strong>
            <small>${escapeHtml(formatTimestamp(item.started_at))} / ${escapeHtml(item.run_dir || "")}${item.blocked_reason ? ` / ${escapeHtml(item.blocked_reason)}` : ""}</small>
          </span>
          ${statusPill(item.status || "unknown")}
        </label>`).join("");
    }

    function renderSharedCleanupList() {
      const items = state.deletionPlan?.shared_data?.items || [];
      state.selectedSharedStores = state.selectedSharedStores.filter((name) => items.some((item) => item.name === name && item.deletable));
      const list = document.querySelector("#shared-cleanup-list");
      if (!list) return;
      if (!items.length) {
        list.innerHTML = `<div class="message">No shared data stores are available for cleanup.</div>`;
        return;
      }
      list.innerHTML = items.map((item) => {
        const refs = Array.isArray(item.delete_refs) ? item.delete_refs.filter((ref) => ref.exists).length : 0;
        return `
          <label class="cleanup-option">
            <input type="checkbox" data-shared-cleanup="${escapeHtml(item.name)}" ${state.selectedSharedStores.includes(item.name) ? "checked" : ""} ${item.deletable ? "" : "disabled"}>
            <span>
              <strong>${escapeHtml(item.title || item.name)}</strong>
              <small>${escapeHtml(item.group || "shared")} / ${formatNumber(item.records || 0)} records / ${refs} refs${item.blocked_reason ? ` / ${escapeHtml(item.blocked_reason)}` : ""}</small>
            </span>
            ${statusPill(item.status || "unknown")}
          </label>`;
      }).join("");
    }

    function wireCleanupControls() {
      const runCleanupButton = document.querySelector("#cleanup-run-artifacts");
      if (runCleanupButton) {
        runCleanupButton.addEventListener("click", () => cleanup("runs"));
      }
      const sharedCleanupButton = document.querySelector("#cleanup-shared-data");
      if (sharedCleanupButton) {
        sharedCleanupButton.addEventListener("click", () => cleanup("shared"));
      }
      document.querySelectorAll("[data-run-cleanup]").forEach((node) => {
        node.addEventListener("change", () => {
          state.selectedRunArtifacts = selectedValues("[data-run-cleanup]", "runCleanup");
        });
      });
      document.querySelectorAll("[data-shared-cleanup]").forEach((node) => {
        node.addEventListener("change", () => {
          state.selectedSharedStores = selectedValues("[data-shared-cleanup]", "sharedCleanup");
        });
      });
    }

    function selectedValues(selector, datasetKey) {
      return Array.from(document.querySelectorAll(selector))
        .filter((node) => node.checked && !node.disabled)
        .map((node) => node.dataset[datasetKey])
        .filter(Boolean);
    }

    async function saveSettings() {
      if (state.settingsProfile?.status === "unconfigured") {
        showToast("Load a config file first.");
        return;
      }
      const paths = Object.keys(state.settingsChanges);
      if (!paths.length) {
        showToast("No settings changes to save.");
        return;
      }
      const ok = await dialogs.confirmAction({
        title: "Save settings",
        message: `Save ${paths.length} setting change(s)? A backup will be created before the config is updated.`,
        confirmLabel: "Save settings",
      });
      if (!ok) {
        showToast("Settings save cancelled.");
        return;
      }
      try {
        const result = await postJson(endpoints.settings, {confirm: true, changes: state.settingsChanges});
        if (result.status === "succeeded") {
          state.settingsProfile = result.profile;
          state.settingsChanges = {};
          renderSettings();
        }
        const errors = Array.isArray(result.errors) ? result.errors : [];
        document.querySelector("#validation-results").innerHTML = `<div class="message ${errors.length ? "error" : ""}"><strong>Config save ${escapeHtml(result.status)}</strong>${result.backup_ref ? `<br>Backup: ${escapeHtml(result.backup_ref)}` : ""}${errors.length ? `<br>${escapeHtml(errors.join("; "))}` : ""}</div>`;
        showToast(`Settings save ${result.status}.`);
      } catch (error) {
        document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function backupSettings() {
      if (state.settingsProfile?.status === "unconfigured") {
        showToast("Load a config file first.");
        return;
      }
      try {
        const result = await postJson(`${endpoints.settings}/backup`, {});
        document.querySelector("#validation-results").innerHTML = `<div class="message ${result.status === "succeeded" ? "" : "error"}"><strong>Config backup ${escapeHtml(result.status)}</strong>${result.backup_ref ? `<br>${escapeHtml(result.backup_ref)}` : ""}${Array.isArray(result.errors) && result.errors.length ? `<br>${escapeHtml(result.errors.join("; "))}` : ""}</div>`;
        showToast(`Config backup ${result.status}.`);
      } catch (error) {
        document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function loadSelectedConfig() {
      const input = document.querySelector("#config-path-input");
      const configPath = input ? input.value.trim() : "";
      if (!configPath) {
        showToast("Enter a config file path.");
        return;
      }
      try {
        const result = await postJson(endpoints.configSelect, {config_path: configPath});
        if (result.status === "succeeded") {
          state.settingsProfile = result.profile;
          state.settingsChanges = {};
          await loadHealth();
          document.querySelector("#validation-results").innerHTML = `<div class="message"><strong>Config loaded</strong><br>${escapeHtml(result.config?.ref || configPath)}</div>`;
          renderSettings();
        } else {
          const errors = Array.isArray(result.errors) ? result.errors : [];
          document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(errors.join("; ") || "Config load failed.")}</div>`;
        }
        showToast(`Config load ${result.status}.`);
      } catch (error) {
        document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function postJob(intent, params = {}) {
      const job = await postJson(endpoints.jobs, {intent, params});
      showToast(`${label(intent)} job ${job.status || "created"}.`);
      if (intent === "validate") {
        state.validationJob = job;
        renderValidationJob(job);
      }
      return job;
    }

    async function fetchJob(jobId) {
      return fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
    }

    function latestReportJob() {
      const jobs = Array.isArray(state.jobs) ? state.jobs : [];
      const reportJobs = jobs.filter((job) => job.intent === "run");
      return reportJobs.find((job) => reportJobIsActive(job)) || null;
    }

    function reportJobRefs(job) {
      return job?.result_refs && typeof job.result_refs === "object" ? job.result_refs : {};
    }

    function reportJobIsActive(job) {
      return ["created", "creating", "queued", "running"].includes(String(job?.status || "").toLowerCase());
    }

    function reportJobShouldRender(job) {
      if (!job) return false;
      const status = String(job.status || "").toLowerCase();
      const refs = reportJobRefs(job);
      if (reportJobIsActive(job)) return true;
      if (status === "succeeded" && refs.report) return false;
      return terminalJobStatus(status);
    }

    function renderReportJob(job) {
      const nodes = [
        document.querySelector("#overview-report-job-status"),
        document.querySelector("#reports-report-job-status"),
      ].filter(Boolean);
      if (!nodes.length) {
        return;
      }
      if (!reportJobShouldRender(job)) {
        nodes.forEach((node) => {
          node.classList.add("hidden");
          node.innerHTML = "";
        });
        setReportButtonsDisabled(false);
        return;
      }
      const refs = reportJobRefs(job);
      const status = job.status || "created";
      const runId = refs.run_id || state.generatedReportRunId || "";
      const reportRef = refs.report || "";
      const manifestRef = refs.run_manifest || refs.manifest || "";
      if (runId) {
        state.generatedReportRunId = runId;
      }
      const warnings = Array.isArray(job.warnings) ? job.warnings : [];
      const errors = Array.isArray(job.errors) ? job.errors : [];
      const detail = [
        `Job: ${job.job_id || "pending"}`,
        runId ? `Run: ${runId}` : "",
        reportRef ? `Report: ${reportRef}` : manifestRef ? `Manifest: ${manifestRef}` : "",
      ].filter(Boolean).join(" | ");
      const hint = terminalJobStatus(status)
        ? "No report artifact is recorded for this job yet."
        : "The job is still running; the report list will refresh after completion.";
      nodes.forEach((node) => {
        node.className = `message job-status ${errors.length || statusClass(status) === "failed" ? "error" : warnings.length ? "warning" : ""}`.trim();
        node.innerHTML = `
          <strong>Report job ${escapeHtml(label(status))}</strong><br>
          ${escapeHtml(detail)}
          <br>${escapeHtml(hint)}
          ${warnings.length ? `<br>Warnings: ${escapeHtml(warnings.slice(0, 2).join("; "))}` : ""}
          ${errors.length ? `<br>Errors: ${escapeHtml(errors.slice(0, 2).join("; "))}` : ""}
        `;
      });
      setReportButtonsDisabled(!terminalJobStatus(status));
    }

    function setReportButtonsDisabled(disabled) {
      document.querySelectorAll("[data-report-job]").forEach((button) => {
        button.disabled = Boolean(disabled);
      });
    }

    async function startReportJob() {
      const ok = await dialogs.confirmAction({
        title: "Generate report",
        message: "Generate a full Codex report now? This can take a while and will create a new run.",
        confirmLabel: "Generate report",
      });
      if (!ok) {
        showToast("Report generation cancelled.");
        return;
      }
      const pending = {
        job_id: "pending",
        intent: "run",
        kind: "product_run",
        status: "creating",
        created_at: new Date().toISOString(),
        result_refs: {},
        warnings: [],
        errors: [],
      };
      state.reportJob = pending;
      renderReportJob(pending);
      try {
        const job = await postJob("run", {confirm_codex: true});
        state.reportJob = job;
        renderReportJob(job);
        if (job.job_id) {
          pollReportJob(job.job_id);
        }
      } catch (error) {
        state.reportJob = {
          ...pending,
          status: "failed",
          errors: [error.message],
        };
        renderReportJob(state.reportJob);
        showToast(`Report generation failed: ${error.message}`);
      }
    }

    async function pollReportJob(jobId) {
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        try {
          const job = await fetchJob(jobId);
          state.reportJob = job;
          renderReportJob(job);
          if (terminalJobStatus(job.status)) {
            await Promise.allSettled([loadRuns(), loadJobs()]);
            renderReportJob(job);
            const runId = reportJobRefs(job).run_id;
            if (runId) {
              state.generatedReportRunId = runId;
              if (state.view === "reports") {
                await refreshReports();
                const report = reportRecords().find((item) => item.run_id === runId);
                if (report) {
                  await selectReport(runId);
                }
              } else if (state.view === "overview") {
                renderOverview();
              }
            }
            showToast(`Report job ${job.status || "completed"}.`);
            return;
          }
        } catch (error) {
          state.reportJob = {
            job_id: jobId,
            intent: "run",
            kind: "product_run",
            status: "failed",
            result_refs: {},
            errors: [error.message],
            warnings: [],
          };
          renderReportJob(state.reportJob);
          return;
        }
      }
      showToast("Report job is still running. Refresh the dashboard to check status.");
    }

    function wait(ms) {
      return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    function terminalJobStatus(status) {
      return ["succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"].includes(String(status || "").toLowerCase());
    }

    function renderValidationJob(job) {
      const status = job?.status || "created";
      const jobId = job?.job_id || "pending";
      const errors = Array.isArray(job?.errors) ? job.errors : [];
      const warnings = Array.isArray(job?.warnings) ? job.warnings : [];
      document.querySelector("#validation-results").innerHTML = `
        <div class="message">
          <strong>Validation job ${escapeHtml(status)}</strong><br>
          Job: ${escapeHtml(jobId)}
          ${warnings.length ? `<br>Warnings: ${escapeHtml(warnings.slice(0, 2).join("; "))}` : ""}
          ${errors.length ? `<br>Errors: ${escapeHtml(errors.slice(0, 2).join("; "))}` : ""}
        </div>`;
    }

    async function cleanup(kind) {
      await loadDeletionPlan();
      if (kind === "runs") {
        const selected = state.selectedRunArtifacts.slice();
        if (!selected.length) return showToast("Select at least one run artifact first.");
        const required = state.deletionPlan?.confirmations?.run_artifacts || "DELETE RUN DATA";
        const confirmed = await dialogs.typedConfirmation({
          title: "Delete single-run artifacts",
          message: `Delete ${selected.length} run artifact set(s). Shared stores are not deleted.`,
          requiredText: required,
          confirmLabel: "Delete selected",
          danger: true,
        });
        if (!confirmed) {
          showToast("Run artifact cleanup cancelled.");
          return;
        }
        const result = await postJson(endpoints.deletion, {kind: "run_artifacts", run_ids: selected, confirm: required});
        state.selectedRunArtifacts = [];
        await Promise.allSettled([loadRuns(), loadStores(), loadDeletionPlan()]);
        renderSettings();
        showToast(`Run artifact cleanup ${result.status}.`);
      } else {
        const selected = state.selectedSharedStores.slice();
        if (!selected.length) return showToast("Select at least one shared data store first.");
        const required = state.deletionPlan?.confirmations?.shared_data || "DELETE SHARED DATA";
        const confirmed = await dialogs.typedConfirmation({
          title: "Delete shared data stores",
          message: `Delete ${selected.length} shared store(s). These stores may be reused by reports and future runs.`,
          requiredText: required,
          confirmLabel: "Delete shared data",
          danger: true,
        });
        if (!confirmed) {
          showToast("Shared data cleanup cancelled.");
          return;
        }
        const result = await postJson(endpoints.deletion, {kind: "shared_data", store_names: selected, confirm: required});
        state.selectedSharedStores = [];
        await Promise.allSettled([loadStores(), loadDeletionPlan()]);
        renderSettings();
        showToast(`Shared data cleanup ${result.status}.`);
      }
    }

    function renderReportTrend(selector, reports) {
      const svg = document.querySelector(selector);
      const width = 260;
      const height = 118;
      const now = new Date();
      const start = new Date(now.getTime() - 13 * 24 * 3600 * 1000);
      const days = Array.from({length: 14}, (_, index) => {
        const day = new Date(start.getTime() + index * 24 * 3600 * 1000);
        return day.toISOString().slice(0, 10);
      });
      const counts = new Map(days.map((day) => [day, 0]));
      reports.forEach((run) => {
        const date = new Date(run.finished_at || run.started_at);
        if (Number.isNaN(date.getTime())) return;
        const key = date.toISOString().slice(0, 10);
        if (counts.has(key)) {
          counts.set(key, counts.get(key) + 1);
        }
      });
      const values = days.map((day) => counts.get(day) || 0);
      if (!values.some((value) => value > 0)) {
        svg.innerHTML = `<text x="16" y="16" fill="#111827" font-size="12" font-weight="700">Reports (last 14 days)</text><text x="130" y="64" fill="#5d6675" font-size="12" text-anchor="middle">No reports in this window</text>`;
        return;
      }
      const max = Math.max(...values, 1);
      const bars = values.map((value, index) => {
        const x = 18 + index * 15;
        const h = value / max * 70;
        return `<rect x="${x}" y="${92 - h}" width="9" height="${h}" rx="2" fill="#008575"></rect>`;
      }).join("");
      svg.innerHTML = `<line x1="16" x2="238" y1="92" y2="92" stroke="#dce2ea"></line>${bars}<text x="16" y="16" fill="#111827" font-size="12" font-weight="700">Reports (last 14 days)</text>`;
    }

    function table(headers, rows) {
      return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(text(cell))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }

    function unique(values) {
      return Array.from(new Set(values.filter(Boolean).map(String)));
    }

    function setHashView(view) {
      window.location.hash = view;
      setView(view);
    }

    function wireShortcutButtons() {
      document.querySelectorAll("[data-view-shortcut]").forEach((button) => {
        button.onclick = () => setHashView(button.dataset.viewShortcut);
      });
    }

    function wireGlobalEvents() {
      dialogs.wire();
      wireDateRangePickers();
      document.querySelectorAll("[data-view-target]").forEach((node) => node.addEventListener("click", (event) => {
        event.preventDefault();
        setHashView(node.dataset.viewTarget);
      }));
      document.querySelector("#global-refresh").addEventListener("click", refreshCurrentView);
      document.querySelector("#report-search").addEventListener("input", renderReportLibrary);
      document.querySelector("#report-reader-search").addEventListener("input", () => {
        state.reportSearchTerm = document.querySelector("#report-reader-search").value;
        if (state.selectedReportPreview && state.selectedReport) {
          renderReportPreview(state.selectedReportPreview, state.selectedReport);
        }
      });
      document.querySelector("#delete-report-button").addEventListener("click", deleteSelectedReport);
      document.querySelector("#download-report-button").addEventListener("click", downloadSelectedReport);
      document.querySelector("#run-backtest-button").addEventListener("click", startBacktest);
      document.querySelector("#download-ohlcv-button").addEventListener("click", downloadSelectedOhlcv);
      document.querySelectorAll("[data-strategy-operation-tab]").forEach((button) => {
        button.addEventListener("click", () => setStrategyOperationTab(button.dataset.strategyOperationTab));
      });
      document.querySelector("#strategy-collect-add-target").addEventListener("click", addStrategyCollectTarget);
      document.querySelector("#strategy-collect-refresh-timeline").addEventListener("click", refreshStrategyCollectTimeline);
      document.querySelector("#strategy-collect-run").addEventListener("click", runStrategyCollectBatch);
      document.querySelector("#strategy-export-run").addEventListener("click", runStrategyExport);
      document.querySelector("#strategy-chart-refresh").addEventListener("click", () => loadStrategyChartPreview({silent: false}));
      ["#strategy-chart-source", "#strategy-chart-symbol", "#strategy-chart-timeframe"].forEach((selector) => {
        document.querySelector(selector).addEventListener("change", () => {
          state.selectedStrategyOutput = null;
          setSelectIfPresent("#strategy-name", "");
          queueStrategyChartRefresh({clearBacktest: true});
        });
      });
      document.querySelector("#strategy-chart-range").addEventListener("change", () => {
        queueStrategyChartRefresh();
      });
      document.querySelector("#strategy-collect-range").addEventListener("change", () => {
        applyRangePreset("#strategy-collect-range", "#strategy-collect-start", "#strategy-collect-end", true);
        queueStrategyCollectTimelineRefresh();
      });
      document.querySelector("#strategy-export-range").addEventListener("change", () => {
        applyRangePreset("#strategy-export-range", "#strategy-export-start", "#strategy-export-end", true);
      });
      ["#strategy-collect-source", "#strategy-collect-start", "#strategy-collect-end"].forEach((selector) => {
        document.querySelector(selector).addEventListener("change", queueStrategyCollectTimelineRefresh);
      });
      ["#strategy-collect-symbol", "#strategy-collect-timeframe"].forEach((selector) => {
        document.querySelector(selector).addEventListener("change", () => {
          if (!state.strategyCollectTargets.length) addStrategyCollectTarget();
        });
      });
      document.querySelectorAll("[data-strategy-window]").forEach((button) => button.addEventListener("click", () => setStrategyWindow(button.dataset.strategyWindow)));
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.addEventListener("click", () => renderStrategyTab(button.dataset.strategyTab)));
      monitorWorkflow.wire();
      dataViewerWorkflow.wire();
      document.querySelectorAll("[data-report-job]").forEach((button) => button.addEventListener("click", startReportJob));
      document.querySelectorAll("[data-job-intent]").forEach((button) => button.addEventListener("click", () => postJob(button.dataset.jobIntent, {})));
      document.querySelectorAll("[data-intel-tab]").forEach((button) => button.addEventListener("click", () => {
        state.selectedIntelTab = button.dataset.intelTab;
        state.selectedIntelItem = null;
        state.selectedIntelPreviewIndex = 0;
        state.intelPreviewDisplayLimit = 30;
        state.intelPreviewFetchLimit = 100;
        state.intelPreviewLoadingMore = false;
        state.intelPreviewKeyword = "";
        state.intelPreviewCategory = "";
        state.intelDatePickerOpen = false;
        state.intelCalendarMonth = null;
        renderIntelligence();
      }));
      document.querySelector("#settings-save").addEventListener("click", saveSettings);
      document.querySelector("#settings-backup").addEventListener("click", backupSettings);
      document.querySelector("#settings-load-config").addEventListener("click", loadSelectedConfig);
      window.addEventListener("hashchange", () => setView(viewFromHash()));
      wireShortcutButtons();
    }

    wireGlobalEvents();
    loadHealth();
    setView(viewFromHash());
